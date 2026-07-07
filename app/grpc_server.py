from __future__ import annotations

from concurrent import futures
from datetime import datetime, timezone
from typing import Any

import grpc
from google.protobuf import empty_pb2, json_format, struct_pb2

from .config import settings
from .database import (
    append_execution_log,
    execution_count,
    get_entity,
    init_db,
    nonce_exists,
    register_nonce,
    update_entity,
)
from .models import ExecutionMandate
from .signer import verify_signature

_ALLOWED_ACTIONS = {"UPDATE_STATUS", "SYNC_RECONCILE"}

metrics: dict[str, int] = {
    "requests_total": 0,
    "executed_total": 0,
    "rejected_total": 0,
    "replay_rejected_total": 0,
}


def _dict_to_struct(payload: dict[str, Any]) -> struct_pb2.Struct:
    message = struct_pb2.Struct()
    json_format.ParseDict(payload, message)
    return message


def _struct_to_dict(message: struct_pb2.Struct) -> dict[str, Any]:
    return json_format.MessageToDict(message)


def _metadata_dict(context: grpc.ServicerContext) -> dict[str, str]:
    return {item.key.lower(): item.value for item in context.invocation_metadata()}


def _parse_utc(value: str) -> datetime:
    # Normalize both Z and offset forms to timezone-aware UTC datetime.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def _validate_temporal_window(issued_at: str, expires_at: str) -> tuple[bool, str]:
    try:
        issued = _parse_utc(issued_at)
        expires = _parse_utc(expires_at)
    except ValueError:
        return False, "issued_at/expires_at must be valid ISO-8601 timestamps"

    now = datetime.now(timezone.utc)
    skew = settings.max_clock_skew_seconds

    if issued > now.replace(microsecond=0) and (issued - now).total_seconds() > skew:
        return False, "issued_at exceeds allowed clock skew"

    if expires <= now:
        return False, "mandate is expired"

    if expires <= issued:
        return False, "expires_at must be later than issued_at"

    return True, ""


def _verify_signature(context: grpc.ServicerContext, payload: dict[str, Any]) -> bool:
    metadata = _metadata_dict(context)
    signature = metadata.get(settings.signature_header.lower())
    if not signature:
        context.set_code(grpc.StatusCode.UNAUTHENTICATED)
        context.set_details("Missing signature metadata")
        return False

    if not verify_signature(settings.signature_secret, payload, signature):
        context.set_code(grpc.StatusCode.UNAUTHENTICATED)
        context.set_details("Invalid signature")
        return False

    return True


def _health(_: empty_pb2.Empty, context: grpc.ServicerContext) -> struct_pb2.Struct:
    del context
    return _dict_to_struct(
        {
            "status": "ok",
            "service": settings.service_name,
            "transport": "grpc",
            "db_path": settings.db_path,
        }
    )


def _get_metrics(_: empty_pb2.Empty, context: grpc.ServicerContext) -> struct_pb2.Struct:
    del context
    payload = dict(metrics)
    payload["execution_log_count"] = execution_count()
    return _dict_to_struct(payload)


def _execute_mandate(request_message: struct_pb2.Struct, context: grpc.ServicerContext) -> struct_pb2.Struct:
    metrics["requests_total"] += 1
    raw_payload = _struct_to_dict(request_message)

    if not _verify_signature(context, raw_payload):
        metrics["rejected_total"] += 1
        return struct_pb2.Struct()

    try:
        mandate = ExecutionMandate.model_validate(raw_payload)
    except Exception as exc:
        metrics["rejected_total"] += 1
        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
        context.set_details(f"Invalid mandate shape: {exc}")
        return struct_pb2.Struct()

    metadata = mandate.mandate_metadata
    action = mandate.mandated_action

    if mandate.council_verdict.upper() != "APPROVED":
        metrics["rejected_total"] += 1
        append_execution_log(
            correlation_id=metadata.correlation_id,
            issuer_id=metadata.issuer_id,
            nonce=metadata.nonce,
            action_type=action.action_type,
            target_table=action.target_table,
            entity_id=action.entity_id,
            result="REJECTED",
            details="council_verdict must be APPROVED",
        )
        context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
        context.set_details("Mandate verdict is not APPROVED")
        return struct_pb2.Struct()

    temporal_ok, temporal_error = _validate_temporal_window(metadata.issued_at, metadata.expires_at)
    if not temporal_ok:
        metrics["rejected_total"] += 1
        append_execution_log(
            correlation_id=metadata.correlation_id,
            issuer_id=metadata.issuer_id,
            nonce=metadata.nonce,
            action_type=action.action_type,
            target_table=action.target_table,
            entity_id=action.entity_id,
            result="REJECTED",
            details=temporal_error,
        )
        context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
        context.set_details(temporal_error)
        return struct_pb2.Struct()

    if nonce_exists(metadata.nonce):
        metrics["rejected_total"] += 1
        metrics["replay_rejected_total"] += 1
        context.set_code(grpc.StatusCode.ALREADY_EXISTS)
        context.set_details("Nonce replay detected")
        return struct_pb2.Struct()

    if action.target_table != settings.allowed_table:
        metrics["rejected_total"] += 1
        context.set_code(grpc.StatusCode.PERMISSION_DENIED)
        context.set_details("Target table is not allowed")
        return struct_pb2.Struct()

    if action.action_type not in _ALLOWED_ACTIONS:
        metrics["rejected_total"] += 1
        context.set_code(grpc.StatusCode.PERMISSION_DENIED)
        context.set_details("Action type is not allowed")
        return struct_pb2.Struct()

    entity = get_entity(action.entity_id)
    if entity is None:
        metrics["rejected_total"] += 1
        context.set_code(grpc.StatusCode.NOT_FOUND)
        context.set_details("Target entity was not found")
        return struct_pb2.Struct()

    updated = update_entity(action.entity_id, action.payload)
    register_nonce(metadata.nonce, metadata.correlation_id, metadata.issuer_id)
    append_execution_log(
        correlation_id=metadata.correlation_id,
        issuer_id=metadata.issuer_id,
        nonce=metadata.nonce,
        action_type=action.action_type,
        target_table=action.target_table,
        entity_id=action.entity_id,
        result="COMMITTED",
        details="Mandate executed successfully",
    )

    metrics["executed_total"] += 1
    return _dict_to_struct(
        {
            "committed": True,
            "correlation_id": metadata.correlation_id,
            "entity": updated,
            "execution_result": "COMMITTED",
        }
    )


def create_server(bind_address: str | None = None) -> grpc.Server:
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))

    handlers = {
        "Health": grpc.unary_unary_rpc_method_handler(
            _health,
            request_deserializer=empty_pb2.Empty.FromString,
            response_serializer=struct_pb2.Struct.SerializeToString,
        ),
        "GetMetrics": grpc.unary_unary_rpc_method_handler(
            _get_metrics,
            request_deserializer=empty_pb2.Empty.FromString,
            response_serializer=struct_pb2.Struct.SerializeToString,
        ),
        "ExecuteMandate": grpc.unary_unary_rpc_method_handler(
            _execute_mandate,
            request_deserializer=struct_pb2.Struct.FromString,
            response_serializer=struct_pb2.Struct.SerializeToString,
        ),
    }

    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("dewey.ExecutionService", handlers),))

    listen_address = bind_address or f"{settings.host}:{settings.grpc_port}"
    server.add_insecure_port(listen_address)
    return server


def serve() -> None:
    server = create_server()
    server.start()
    server.wait_for_termination()
