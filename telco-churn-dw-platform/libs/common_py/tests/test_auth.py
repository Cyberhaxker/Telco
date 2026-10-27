from __future__ import annotations

import time

import jwt
import pytest

from telco_common.auth import TokenVerifier
from telco_common.problems import ProblemError
from telco_common.settings import ServiceSettings

SECRET = "x" * 40


def _token(secret: str = SECRET, **over: object) -> str:
    now = int(time.time())
    claims = {"sub": "1", "preferred_username": "ann", "roles": ["analyst", "bogus"], "iss": "telco-web",
              "aud": "telco-api", "iat": now, "exp": now + 60, **over}
    return jwt.encode(claims, secret, algorithm="HS256")


def _verifier() -> TokenVerifier:
    return TokenVerifier(ServiceSettings(jwt_secret=SECRET))


def test_valid_token_yields_principal_with_known_roles():
    p = _verifier().verify(_token())
    assert p.username == "ann"
    assert p.roles == frozenset({"analyst"})


@pytest.mark.parametrize("token", [_token("y" * 40), _token(exp=int(time.time()) - 300), _token(iss="other"), _token(aud="x")])
def test_bad_tokens_are_rejected(token):
    with pytest.raises(ProblemError) as err:
        _verifier().verify(token)
    assert err.value.status == 401
