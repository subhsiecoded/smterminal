from fastapi import APIRouter, Depends
from supabase import Client

from app.deps import CurrentUser, get_current_user, get_user_scoped_supabase
from app.models.schemas import WatchlistCreate, WatchlistItemCreate

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


@router.get("")
async def list_watchlists(sb: Client = Depends(get_user_scoped_supabase)) -> list[dict]:
    # RLS restricts this to the caller's own rows - no manual user_id filter.
    result = sb.table("watchlists").select("*, watchlist_items(instrument_id, sort_order)").execute()
    return result.data


@router.post("")
async def create_watchlist(
    body: WatchlistCreate,
    user: CurrentUser = Depends(get_current_user),
    sb: Client = Depends(get_user_scoped_supabase),
) -> dict:
    # user_id must still be set explicitly on insert - RLS's WITH CHECK
    # verifies it matches auth.uid(), it doesn't fill it in for you. (A
    # `default auth.uid()` column default is the alternative if you'd
    # rather not pass it from every router - either is fine as long as
    # exactly one of them is actually in place.)
    result = sb.table("watchlists").insert({"user_id": user.user_id, "name": body.name}).execute()
    return result.data[0]


@router.post("/{watchlist_id}/items")
async def add_item(
    watchlist_id: int,
    body: WatchlistItemCreate,
    sb: Client = Depends(get_user_scoped_supabase),
) -> dict:
    # RLS on watchlist_items checks the parent watchlist's user_id, so an
    # id belonging to another user is rejected at the database layer, not
    # just by an app-level check that could be forgotten on some new route.
    result = sb.table("watchlist_items").insert(
        {"watchlist_id": watchlist_id, "instrument_id": body.instrument_id}
    ).execute()
    return result.data[0]


@router.delete("/{watchlist_id}/items/{instrument_id}")
async def remove_item(
    watchlist_id: int,
    instrument_id: int,
    sb: Client = Depends(get_user_scoped_supabase),
) -> dict:
    sb.table("watchlist_items").delete().eq("watchlist_id", watchlist_id).eq(
        "instrument_id", instrument_id
    ).execute()
    return {"ok": True}
