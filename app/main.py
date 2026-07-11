from __future__ import annotations

from .config import settings
from .grpc_server import serve


def _validate_security_config() -> None:
    if not settings.signature_secret:
        raise RuntimeError("INBOUND_SIGNATURE_SECRET is required")

    if settings.environment.lower() in {"staging", "production", "prod"}:
        if settings.signature_secret == settings.signature_dev_fallback:
            raise RuntimeError("INBOUND_SIGNATURE_SECRET cannot use the development fallback in staging/production")

    if settings.grpc_tls_enabled:
        if not settings.grpc_tls_server_cert_path or not settings.grpc_tls_server_key_path:
            raise RuntimeError("GRPC TLS requires GRPC_TLS_SERVER_CERT_PATH and GRPC_TLS_SERVER_KEY_PATH")
        if settings.grpc_tls_require_client_auth and not settings.grpc_tls_client_ca_cert_path:
            raise RuntimeError("GRPC mTLS inbound requires GRPC_TLS_CLIENT_CA_CERT_PATH when client auth is enabled")


if __name__ == "__main__":
    _validate_security_config()
    serve()
