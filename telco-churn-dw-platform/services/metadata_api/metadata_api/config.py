from __future__ import annotations

from functools import lru_cache

from telco_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "metadata-api"
    dw_dsn: str = "postgresql://dw_meta:dw_meta@dw-postgres:5432/telco_churn_dw"
    dbt_manifest_path: str = "/dbt_artifacts/target/manifest.json"
    airflow_api_url: str | None = None
    airflow_username: str | None = None
    airflow_password: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
