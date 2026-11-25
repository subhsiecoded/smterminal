from fastapi import APIRouter, Depends, Header, HTTPException, Request
from supabase import Client

from app.config import Settings, get_settings
from app.deps import (
    CurrentUser,
    get_current_user,
    get_service_supabase,
    get_user_scoped_supabase,
    verify_live_intent,
)
from app.models.schemas import OrderCreate, OrderOut
from app.rate_limit import limiter
from app.services import audit

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderOut)
@limiter.limit("20/minute")  # protects against runaway client retries/automation loops
async def place_order(
    request: Request,
    body: OrderCreate,
    user: CurrentUser = Depends(get_current_user),
    sb: Client = Depends(get_user_scoped_supabase),      # RLS-enforced
    sb_service: Client = Depends(get_service_supabase),  # audit log only
    settings: Settings = Depends(get_settings),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    live_intent_token: str | None = Header(default=None, alias="X-Live-Intent-Token"),
) -> OrderOut:
    if not body.is_paper:
        # Routing a LIVE order requires a separate, short-lived confirmation
        # obtained from POST /api/trading-mode/confirm-live - the request
        # body's is_paper flag alone is never enough. See that router for why.
        if not live_intent_token:
            raise HTTPException(
                status_code=403,
                detail="Live orders require a live-trading intent token - call POST /api/trading-mode/confirm-live first.",
            )
        verify_live_intent(live_intent_token, user.user_id, settings)
        raise HTTPException(
            status_code=501,
            detail="No broker is wired up in this build - everything is paper-trading only. This confirmation gate exists for when one is added.",
        )

    # Idempotency: a client retrying a dropped response (common over a
    # flaky mobile connection) must not double-fill. The unique index from
    # migration 0002 makes this race-safe even under concurrent retries -
    # we don't rely on the pre-check alone.
    if idempotency_key:
        existing = (
            sb.table("orders")
            .select("*")
            .eq("idempotency_key", idempotency_key)
            .execute()
        )
        if existing.data:
            return OrderOut(**existing.data[0])

    row = {
        "user_id": user.user_id,
        "instrument_id": body.instrument_id,
        "side": body.side,
        "qty": body.qty,
        "price": body.price,
        "order_type": body.order_type,
        "status": "FILLED",  # paper fills immediately at the submitted price
        "is_paper": True,
        "idempotency_key": idempotency_key,
    }
    try:
        result = sb.table("orders").insert(row).execute()
    except Exception as exc:
        # The unique index can legitimately reject a genuine race between
        # two near-simultaneous retries; treat it the same as the pre-check.
        if idempotency_key:
            existing = (
                sb.table("orders").select("*").eq("idempotency_key", idempotency_key).execute()
            )
            if existing.data:
                return OrderOut(**existing.data[0])
        raise HTTPException(status_code=500, detail="Order could not be placed") from exc

    order = result.data[0]
    audit.record(
        sb_service,
        user.user_id,
        "order.place",
        detail={"order_id": order["id"], "side": body.side, "qty": body.qty, "is_paper": True},
        request_id=getattr(request.state, "request_id", None),
    )
    return OrderOut(**order)


@router.get("", response_model=list[OrderOut])
async def list_orders(
    sb: Client = Depends(get_user_scoped_supabase),
) -> list[OrderOut]:
    # No .eq("user_id", ...) needed here, and intentionally so - RLS
    # already restricts every row this client can see to the caller.
    result = sb.table("orders").select("*").order("ts", desc=True).execute()
    return [OrderOut(**row) for row in result.data]


@router.delete("/{order_id}")
async def cancel_order(
    order_id: int,
    sb: Client = Depends(get_user_scoped_supabase),
) -> dict:
    sb.table("orders").update({"status": "CANCELLED"}).eq("id", order_id).execute()
    return {"ok": True}
