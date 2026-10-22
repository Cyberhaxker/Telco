from __future__ import annotations

from functools import lru_cache

from telco_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "ingestion-api"
    ops_database_url: str = "mysql+pymysql://ops_app:ops_app@mysql:3306/telco_ops"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_enabled: bool = True
    run_migrations: bool = False

    max_batch_records: int = 500
    max_payload_bytes: int = 5 * 1024 * 1024
    max_csv_bytes: int = 10 * 1024 * 1024
    outbox_poll_seconds: float = 1.0
    outbox_batch_size: int = 500


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
