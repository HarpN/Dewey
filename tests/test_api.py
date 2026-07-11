from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import grpc
import pytest
from google.protobuf import empty_pb2, json_format, struct_pb2

os.environ["DEWEY_DB_PATH"] = "/tmp/dewey_test.db"
os.environ["INBOUND_SIGNATURE_HEADER"] = "X-Judy-Signature"
os.environ["INBOUND_SIGNATURE_SECRET"] = "dewey-test-secret"

from app.grpc_server import create_server
from app.signer import sign_payload

_db = Path("/tmp/dewey_test.db")
if _db.exists():
    _db.unlink()


@pytest.fixture(scope="module")
def channel() -> grpc.Channel:
    server = create_server(bind_address="127.0.0.1:0")
    server.start()

    grpc_channel = grpc.insecure_channel(f"127.0.0.1:{server.bound_port}")
    grpc.channel_ready_future(grpc_channel).result(timeout=5)

    yield grpc_channel

    grpc_channel.close()
    server.stop(None)


def _health_call(channel: grpc.Channel):
    return channel.unary_unary(
        "/dewey.ExecutionService/Health",
        request_serializer=empty_pb2.Empty.SerializeToString,
        response_deserializer=struct_pb2.Struct.FromString,
    )


def _execute_call(channel: grpc.Channel):
    return channel.unary_unary(
        "/dewey.ExecutionService/ExecuteMandate",
        request_serializer=struct_pb2.Struct.SerializeToString,
        response_deserializer=struct_pb2.Struct.FromString,
    )


def _as_struct(payload: dict) -> struct_pb2.Struct:
    message = struct_pb2.Struct()
    json_format.ParseDict(payload, message)
    return message


def _signed_metadata(payload: dict) -> tuple[tuple[str, str], ...]:
    normalized = json_format.MessageToDict(_as_struct(payload))
    signature = sign_payload("dewey-test-secret", normalized)
    return (("x-judy-signature", signature),)


def _mandate(*, nonce: str, expires_delta_minutes: int = 5, verdict: str = "APPROVED") -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "mandate_metadata": {
            "issuer_id": "judy-council",
            "key_id": "judy-k1",
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=expires_delta_minutes)).isoformat(),
            "nonce": nonce,
            "correlation_id": f"corr-{uuid4().hex[:8]}",
        },
        "council_verdict": verdict,
        "mandated_action": {
            "target_table": "local_backlog",
            "action_type": "UPDATE_STATUS",
            "entity_id": "game_105",
            "payload": {
                "status": "ACTIVE",
                "completion": 88,
                "notes": "Executed by Dewey tests",
            },
        },
        "rationale": "Mandate execution test",
    }


def test_health(channel: grpc.Channel) -> None:
    response = _health_call(channel)(empty_pb2.Empty())
    payload = json_format.MessageToDict(response)
    assert payload["status"] == "ok"


def test_execute_approved_mandate(channel: grpc.Channel) -> None:
    payload = _mandate(nonce=f"nonce-{uuid4().hex[:10]}")
    response = _execute_call(channel)(_as_struct(payload), metadata=_signed_metadata(payload))
    body = json_format.MessageToDict(response)

    assert body["committed"] is True
    assert body["entity"]["current_completion"] == 88.0


def test_rejects_replay_nonce(channel: grpc.Channel) -> None:
    nonce = f"nonce-{uuid4().hex[:10]}"
    payload = _mandate(nonce=nonce)
    _execute_call(channel)(_as_struct(payload), metadata=_signed_metadata(payload))

    with pytest.raises(grpc.RpcError) as exc:
        _execute_call(channel)(_as_struct(payload), metadata=_signed_metadata(payload))

    assert exc.value.code() == grpc.StatusCode.ALREADY_EXISTS


def test_rejects_expired_mandate(channel: grpc.Channel) -> None:
    payload = _mandate(nonce=f"nonce-{uuid4().hex[:10]}", expires_delta_minutes=-1)
    with pytest.raises(grpc.RpcError) as exc:
        _execute_call(channel)(_as_struct(payload), metadata=_signed_metadata(payload))

    assert exc.value.code() == grpc.StatusCode.FAILED_PRECONDITION


def test_rejects_invalid_signature(channel: grpc.Channel) -> None:
    payload = _mandate(nonce=f"nonce-{uuid4().hex[:10]}")

    with pytest.raises(grpc.RpcError) as exc:
        _execute_call(channel)(_as_struct(payload), metadata=(("x-judy-signature", "bad-signature"),))

    assert exc.value.code() == grpc.StatusCode.UNAUTHENTICATED
