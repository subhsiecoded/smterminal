from supabase import Client


def record(
    sb_service: Client,
    user_id: str,
    action: str,
    detail: dict | None = None,
    request_id: str | None = None,
) -> None:
    """Fire-and-forget audit entry. Uses the service-role client because
    the audit_log RLS policy only grants SELECT to the user-scoped client -
    a compromised session token can read its own history but never write
    or tamper with it. Never raises: a logging failure must not block the
    action it's recording.
    """
    try:
        sb_service.table("audit_log").insert(
            {
                "user_id": user_id,
                "action": action,
                "detail": detail or {},
                "request_id": request_id,
            }
        ).execute()
    except Exception:  # noqa: BLE001 - audit logging is best-effort by design
        pass
