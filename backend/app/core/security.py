"""Supabase JWT verification.

This module performs *cryptographic* verification of Supabase-issued access
tokens. It never merely decodes a token: the signature, expiration (``exp``),
issuer (``iss``), and audience (``aud``) are all validated.

Two signing strategies are supported, matching the two kinds of Supabase
projects:

* **HS256 (legacy shared secret).** If ``BREADCRUMBS_SUPABASE_JWT_SECRET`` is
  configured, tokens are verified with that symmetric secret.
* **Asymmetric (RS256/ES256).** Otherwise the verifier fetches the project's
  public keys from the JWKS endpoint and verifies against the key identified by
  the token ``kid`` header. Keys are cached by ``PyJWKClient``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.core.config import Settings, get_settings

# Algorithms we are willing to accept per strategy. Restricting the algorithm
# list is important: it prevents "alg" confusion / downgrade attacks.
_HS_ALGORITHMS = ["HS256"]
_ASYMMETRIC_ALGORITHMS = ["RS256", "ES256"]


class AuthError(Exception):
    """Raised when a token cannot be verified. Mapped to HTTP 401 by callers."""


@dataclass
class TokenClaims:
    """Validated claims we care about from a Supabase access token."""

    subject: str
    email: str | None
    raw: dict


class JWTVerifier:
    """Verifies Supabase JWTs according to the configured strategy."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client: PyJWKClient | None = None

    @property
    def _uses_shared_secret(self) -> bool:
        return bool(self._settings.supabase_jwt_secret)

    def _get_jwks_client(self) -> PyJWKClient:
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(self._settings.supabase_jwks_url)
        return self._jwks_client

    def _resolve_key(self, token: str) -> tuple[object, list[str]]:
        if self._uses_shared_secret:
            return self._settings.supabase_jwt_secret, _HS_ALGORITHMS
        signing_key = self._get_jwks_client().get_signing_key_from_jwt(token)
        return signing_key.key, _ASYMMETRIC_ALGORITHMS

    def verify(self, token: str) -> TokenClaims:
        if not self._settings.supabase_url:
            raise AuthError("Supabase auth is not configured on the server.")

        try:
            key, algorithms = self._resolve_key(token)
        except AuthError:
            raise
        except Exception as exc:  # JWKS fetch / kid resolution failures
            raise AuthError(f"Unable to resolve signing key: {exc}") from exc

        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=self._settings.supabase_jwt_audience,
                issuer=self._settings.supabase_issuer,
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except jwt.PyJWTError as exc:
            raise AuthError(str(exc)) from exc

        subject = payload.get("sub")
        if not subject:
            raise AuthError("Token is missing the subject (sub) claim.")

        return TokenClaims(
            subject=subject,
            email=payload.get("email"),
            raw=payload,
        )


@lru_cache
def get_verifier() -> JWTVerifier:
    """Return a cached verifier built from application settings."""
    return JWTVerifier(get_settings())
