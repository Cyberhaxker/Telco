from __future__ import annotations

from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Settings every HTTP service shares. Values come from environment variables."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    service_name: str = "telco-service"
    environment: str = "dev"
    log_level: str = "INFO"

    oidc_issuer: str = "http://localhost:8081/realms/telco"
    oidc_jwks_url: str = "http://keycloak:8080/realms/telco/protocol/openid-connect/certs"
    oidc_audience: str = "telco-api"
    # Tokens issued by the web app's own login (HS256). When jwt_secret is set it replaces the OIDC/JWKS check.
    jwt_secret: str = ""
    jwt_issuer: str = "telco-web"
    # Disabling auth is only possible outside production and is used by unit tests.
    auth_disabled: bool = False

    cors_origins: str = Field(default="http://localhost:3000")

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}
