from __future__ import annotations

from functools import lru_cache

from telco_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "analytics-api"
    dw_dsn: str = "postgresql://dw_analytics:dw_analytics@dw-postgres:5432/telco_churn_dw"
    valkey_url: str | None = None
    cache_ttl_seconds: int = 60
    kafka_bootstrap_servers: str | None = None
    mlflow_tracking_uri: str | None = None
    ml_model_name: str = "telco_churn"
    ml_model_dir: str = "/models"
    ml_high_risk_threshold: float = 0.6
    ml_medium_risk_threshold: float = 0.3
    olap_max_rows: int = 5000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
