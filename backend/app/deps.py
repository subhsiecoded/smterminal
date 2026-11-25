import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from supabase import Client, create_client

from app.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


# ──────────────────────────────────────────────────────────────────────────
# Supabase clients - only exercised by the (currently dormant, login-gated)
# orders/watchlists routers. Market data needs none of this.
# ──────────────────────────────────────────────────────────────────────────

def get_service_supabase(settings: Settings = Depends(get_settings)) -> Client:
    """Service-role client. Bypasses RLS entirely - use ONLY for jobs that
    genuinely need cross-user access (the audit log). Never use this for a
    user-scoped read or write; use get_user_scoped_supabase so RLS stays the
    enforcing layer, not just an app-level .eq("user_id", ...) filter.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_user_scoped_supabase(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Client:
    """A client built with the ANON key, authenticated as the calling user
    by forwarding their verified JWT to PostgREST, so RLS evaluates every
    query against THIS user's auth.uid().
    """
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(creds.credentials)
    return client


# ──────────────────────────────────────────────────────────────────────────
# User identity - verifies the Supabase-issued JWT. Only required by
# orders/watchlists/trading-mode right now; market data is public.
# ──────────────────────────────────────────────────────────────────────────

class CurrentUser:
    def __init__(self, user_id: str, email: str | None = None):
        self.user_id = user_id
        self.email = email


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = jwt.decode(
            creds.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject claim")
    return CurrentUser(user_id=user_id, email=payload.get("email"))


# ──────────────────────────────────────────────────────────────────────────
# Live-trading step-up confirmation - unrelated to login; this gates the
# (currently unreachable, no broker is wired up) live-order path in
# orders.py/trading_mode.py. Kept for when a real broker integration lands.
# ──────────────────────────────────────────────────────────────────────────

def issue_live_intent(user_id: str, settings: Settings) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": user_id, "scope": "live_trading", "iat": now, "exp": now + settings.live_intent_ttl_seconds},
        settings.app_secret_key,
        algorithm="HS256",
    )


def verify_live_intent(token: str, user_id: str, settings: Settings) -> None:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Live-trading confirmation expired or invalid") from exc
    if payload.get("scope") != "live_trading" or payload.get("sub") != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Live-trading confirmation does not match this user")
