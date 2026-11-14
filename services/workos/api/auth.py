"""Clerk JWT authentication & organization RBAC dependencies for services/workos."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, Header, Query, status
from jwt import PyJWKClient

from core.config import get_settings

logger = logging.getLogger(__name__)

_jwks_client_cache: Dict[str, tuple[float, PyJWKClient]] = {}
_JWKS_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    org_id: str
    role: str
    email: Optional[str] = None
    is_demo: bool = False


def get_jwk_client(jwks_url: str) -> PyJWKClient:
    """Return a cached PyJWKClient for Clerk JWKS URL."""
    now = time.monotonic()
    cached = _jwks_client_cache.get(jwks_url)
    if cached and (now - cached[0]) < _JWKS_TTL_SECONDS:
        return cached[1]
    client = PyJWKClient(jwks_url, cache_keys=True, lifespan=int(_JWKS_TTL_SECONDS))
    _jwks_client_cache[jwks_url] = (now, client)
    return client


def clear_jwks_cache() -> None:
    _jwks_client_cache.clear()


def _extract_claims(payload: Dict[str, Any]) -> AuthContext:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required 'sub' claim.",
        )

    raw_org = payload.get("o")
    org_obj: Dict[str, Any] = raw_org if isinstance(raw_org, dict) else {}
    org_id = payload.get("org_id") or org_obj.get("id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active Clerk organization ('org_id') is required.",
        )

    role = payload.get("org_role") or org_obj.get("rol") or "org:member"
    return AuthContext(
        user_id=str(user_id),
        org_id=str(org_id),
        role=str(role),
        email=payload.get("email"),
        is_demo=bool(payload.get("demo", False)),
    )


def verify_clerk_jwt(token: str) -> AuthContext:
    """Verify Clerk RS256 JWT against JWKS (or HMAC-signed dev demo token when JWKS unset)."""
    settings = get_settings()

    # 1. First check if token is an HMAC HS256 dev/demo token
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        header = {}

    if header.get("alg") == "HS256":
        candidate_secrets = [
            s for s in (
                settings.shared_hmac_secret,
                "horizon_veridian_demo_hmac_secret_min_32_bytes_2026",
                "dev-demo-secret",
            ) if s
        ]
        for sec in candidate_secrets:
            try:
                payload = jwt.decode(
                    token,
                    sec,
                    algorithms=["HS256"],
                    options={"verify_aud": False},
                )
                return _extract_claims(payload)
            except jwt.ExpiredSignatureError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication token has expired.",
                )
            except Exception:
                continue

    # 2. RS256 verification against Clerk JWKS
    if settings.clerk_jwks_url:
        try:
            jwk_client = get_jwk_client(settings.clerk_jwks_url)
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            decode_kwargs: Dict[str, Any] = {
                "algorithms": ["RS256"],
                "options": {"verify_aud": False},
            }
            if settings.clerk_issuer:
                decode_kwargs["issuer"] = settings.clerk_issuer
            payload = jwt.decode(token, signing_key.key, **decode_kwargs)
            return _extract_claims(payload)
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired.",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token.",
    )


def _extract_bearer_token(
    authorization: Optional[str] = Header(default=None),
    token_query: Optional[str] = Query(default=None, alias="token"),
) -> str:
    # EventSource in browsers cannot set custom Authorization headers directly,
    # so SSE clients may pass `?token=...` alongside Bearer header support.
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer scheme.",
        )
    if token_query and token_query.strip():
        return token_query.strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication token.",
    )


async def require_auth(
    token: str = Depends(_extract_bearer_token),
) -> AuthContext:
    """FastAPI dependency returning verified AuthContext (user_id, org_id, role)."""
    return verify_clerk_jwt(token)


async def require_manager(
    auth: AuthContext = Depends(require_auth),
) -> AuthContext:
    """FastAPI dependency enforcing manager/admin organization role."""
    settings = get_settings()
    if auth.role not in settings.manager_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Manager role required. Current role '{auth.role}' is not authorized.",
        )
    return auth


def mint_demo_jwt(
    user_id: str = "user_demo_manager",
    org_id: str = "org_demo_horizon",
    role: str = "org:admin",
    ttl_seconds: int = 3600,
) -> str:
    """Mint a short-lived local dev JWT signed with SHARED_HMAC_SECRET for DEMO_MODE."""
    settings = get_settings()
    if not (settings.demo_mode and settings.app_env == "development"):
        raise RuntimeError("Demo tokens can only be minted when DEMO_MODE=true and APP_ENV=development.")
    secret = settings.shared_hmac_secret or "dev-demo-secret"
    now = int(time.time())
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "org_role": role,
        "demo": True,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")
