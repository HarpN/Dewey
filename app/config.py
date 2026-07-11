from __future__ import annotations

import os


class Settings:
    environment: str = os.getenv("ENVIRONMENT", "dev")
    service_name: str = os.getenv("SERVICE_NAME", "dewey-execution")
    service_version: str = os.getenv("SERVICE_VERSION", "0.1.0")
    host: str = os.getenv("HOST", "0.0.0.0")
    grpc_port: int = int(os.getenv("GRPC_PORT", "50053"))
    grpc_max_workers: int = int(os.getenv("GRPC_MAX_WORKERS", "32"))

    grpc_tls_enabled: bool = os.getenv("GRPC_TLS_ENABLED", "false").lower() == "true"
    grpc_tls_server_cert_path: str = os.getenv("GRPC_TLS_SERVER_CERT_PATH", "")
    grpc_tls_server_key_path: str = os.getenv("GRPC_TLS_SERVER_KEY_PATH", "")
    grpc_tls_client_ca_cert_path: str = os.getenv("GRPC_TLS_CLIENT_CA_CERT_PATH", "")
    grpc_tls_require_client_auth: bool = os.getenv("GRPC_TLS_REQUIRE_CLIENT_AUTH", "false").lower() == "true"

    db_path: str = os.getenv("DEWEY_DB_PATH", "/data/dewey.db")
    allowed_table: str = os.getenv("DEWEY_ALLOWED_TABLE", "local_backlog")

    signature_header: str = os.getenv("INBOUND_SIGNATURE_HEADER", "X-Judy-Signature")
    signature_secret: str = os.getenv("INBOUND_SIGNATURE_SECRET", "")
    signature_dev_fallback: str = "dewey-dev-secret"

    max_clock_skew_seconds: int = int(os.getenv("MAX_CLOCK_SKEW_SECONDS", "120"))
    replay_ttl_seconds: int = int(os.getenv("REPLAY_TTL_SECONDS", "300"))


settings = Settings()
