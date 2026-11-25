import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from app.config import Settings, get_settings
from app.deps import CurrentUser, bearer_scheme, get_current_user, issue_live_intent
from app.rate_limit import limiter

router = APIRouter(prefix="/api/trading-mode", tags=["trading-mode"])

# A session is "fresh" if the JWT itself was issued recently - a cheap
# approximation of step-up auth without building a full MFA/OTP flow.
# For anything beyond a personal, single-user build, replace this check
# with a real re-authentication (password or OTP) before issuing the
# live-trading intent token.
MAX_SESSION_AGE_FOR_LIVE_SECONDS = 300


@router.post("/confirm-live")
@limiter.limit("5/minute")  # a brute-force attempt against a short-lived token is still an attempt
async def confirm_live_trading(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Issues a short-lived (5 min) live-trading intent token. The orders
    router requires this token, separately from the request body's
    `is_paper` flag, before it will route anything to the real broker -
    so a leaked session JWT alone can never place a live order.
    """
    payload = jwt.decode(
        creds.credentials,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience="authenticated",
    )
    issued_at = payload.get("iat", 0)
    if time.time() - issued_at > MAX_SESSION_AGE_FOR_LIVE_SECONDS:
        raise HTTPException(
            status_code=403,
            detail="Session too old to confirm live trading - please sign in again, then retry.",
        )

    intent_token = issue_live_intent(user.user_id, settings)
    return {"live_intent_token": intent_token, "expires_in": settings.live_intent_ttl_seconds}
