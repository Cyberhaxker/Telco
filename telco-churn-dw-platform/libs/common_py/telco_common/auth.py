"""JWT validation (defence in depth behind the gateway) and role guards.

Tokens are issued by the web app's login (bcrypt-checked users, HS256 JWT signed
with the shared JWT_SECRET). Without JWT_SECRET the services fall back to validating
RS256 tokens from an OIDC provider's JWKS. Every service validates the token
(signature, issuer, audience, expiry) and enforces roles with dependency-injected guards.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient

from .logging import user_ctx
from .problems import ProblemError
from .settings import ServiceSettings

log = logging.getLogger(__name__)

ROLES = ("admin", "data_steward", "data_entry", "analyst", "viewer")


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    roles: frozenset[str] = field(default_factory=frozenset)
    claims: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def has_any(self, *roles: str) -> bool:
        return "admin" in self.roles or any(r in self.roles for r in roles)


class TokenVerifier:
    def __init__(self, settings: ServiceSettings) -> None:
        self.settings = settings
        self._jwks = PyJWKClient(settings.oidc_jwks_url, cache_keys=True, lifespan=600, timeout=5)

    def _decode(self, token: str) -> dict[str, Any]:
        s = self.settings
        if s.jwt_secret:
            return jwt.decode(
                token,
                s.jwt_secret,
                algorithms=["HS256"],
                audience=s.oidc_audience,
                issuer=s.jwt_issuer,
                options={"require": ["exp", "iat", "iss", "sub"]},
                leeway=30,
            )
        signing_key = self._jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "RS384", "RS512", "PS256"],
            audience=s.oidc_audience,
            issuer=s.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
            leeway=30,
        )

    def verify(self, token: str) -> Principal:
        try:
            claims = self._decode(token)
        except jwt.ExpiredSignatureError as exc:
            raise _unauthorized("Token expired") from exc
        except jwt.PyJWKClientError as exc:
            log.warning("JWKS lookup failed: %s", exc)
            raise _unauthorized("Unable to verify token signature") from exc
        except jwt.InvalidTokenError as exc:
            raise _unauthorized(f"Invalid token: {exc}") from exc
        raw_roles = claims.get("roles") or claims.get("realm_access", {}).get("roles", [])
        roles = frozenset(r for r in raw_roles if r in ROLES)
        return Principal(
            subject=claims["sub"],
            username=claims.get("preferred_username", claims["sub"]),
            roles=roles,
            claims=claims,
        )


def _unauthorized(detail: str) -> ProblemError:
    return ProblemError(401, "Unauthorized", detail, headers={"WWW-Authenticate": 'Bearer realm="telco"'})


_DEV_PRINCIPAL = Principal("dev-user", "dev", frozenset(ROLES))


def get_principal(request: Request) -> Principal:
    settings: ServiceSettings = request.app.state.settings
    if settings.auth_disabled and not settings.is_production:
        user_ctx.set(_DEV_PRINCIPAL.username)
        return _DEV_PRINCIPAL
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Missing bearer token")
    verifier: TokenVerifier = request.app.state.token_verifier
    principal = verifier.verify(token)
    user_ctx.set(principal.username)
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    """Dependency factory: allow admins and any of ``roles``; otherwise 403."""

    def guard(principal: CurrentPrincipal) -> Principal:
        if not principal.has_any(*roles):
            raise ProblemError(
                403,
                "Forbidden",
                f"Requires one of the roles: {', '.join(roles)}",
                required_roles=list(roles),
            )
        return principal

    return guard
