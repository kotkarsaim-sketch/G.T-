"""Admin authentication (api-spec §2.7).

Three modes; the first configured wins:

1. OIDC (production): `oidc_issuer` set - bearer JWTs are validated against
   the issuer's JWKS (municipal IdP). Tokens must carry a `civic-admin`
   role, via a `roles` claim or a boolean `civic-admin` claim.
2. Static token: `admin_token` set - exact bearer match. For bootstrap and
   automation accounts.
3. Dev fallback: nothing configured and environment == dev - open, with a
   startup warning. Production with nothing configured fails closed.
"""

import logging

import jwt
from fastapi import HTTPException, Request

from civic.settings import Settings, get_settings

log = logging.getLogger(__name__)

_jwks_client = None


def authorize(token: str | None, settings: Settings) -> tuple[bool, str]:
    if settings.oidc_issuer:
        if not token:
            return False, "missing bearer token"
        try:
            return _oidc_check(token, settings), "oidc"
        except Exception as exc:  # noqa: BLE001 - any JWKS/signature failure denies
            log.warning("OIDC validation failed: %s", exc)
            return False, "invalid token"

    if settings.admin_token:
        if token is not None and token == settings.admin_token:
            return True, "static-token"
        return False, "invalid admin token"

    if settings.civic_environment == "dev":
        return True, "dev-open"
    return False, "admin auth not configured"


def _oidc_check(token: str, settings: Settings) -> bool:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            f"{settings.oidc_issuer.rstrip('/')}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=300,
        )
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=settings.oidc_audience or None,
        options={"require": ["exp"]},
    )
    roles = claims.get("roles") or []
    return "civic-admin" in roles or claims.get("civic-admin") is True


async def require_admin(request: Request) -> None:
    settings = get_settings()
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    ok, reason = authorize(token, settings)
    if not ok:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "detail": reason},
            headers={"WWW-Authenticate": "Bearer"},
        )
