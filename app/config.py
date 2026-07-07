from __future__ import annotations

import os


class Settings:
    service_name: str = os.getenv("SERVICE_NAME", "dewey-execution")
    service_version: str = os.getenv("SERVICE_VERSION", "0.1.0")
    host: str = os.getenv("HOST", "0.0.0.0")
    grpc_port: int = int(os.getenv("GRPC_PORT", "50053"))

    db_path: str = os.getenv("DEWEY_DB_PATH", "/data/dewey.db")
    allowed_table: str = os.getenv("DEWEY_ALLOWED_TABLE", "local_backlog")

    signature_header: str = os.getenv("INBOUND_SIGNATURE_HEADER", "X-Judy-Signature")
    signature_secret: str = os.getenv("INBOUND_SIGNATURE_SECRET", "dewey-dev-secret")

    max_clock_skew_seconds: int = int(os.getenv("MAX_CLOCK_SKEW_SECONDS", "120"))


settings = Settings()
