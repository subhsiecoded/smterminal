import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from app.config import get_settings, parse_frontend_origins

from app.services.pubsub import broker
from app.services.watch_registry import registry
from app.services.symbols import normalize_symbol

router = APIRouter()
logger = logging.getLogger("market_terminal.ws")

HEARTBEAT_INTERVAL_SECONDS = 15
MAX_SYMBOLS_PER_CONNECTION = 50
MAX_CONNECTIONS_PER_IP = 20

_connections_per_ip: dict[str, int] = {}


@router.websocket("/ws/ticks")
async def ticks_ws(websocket: WebSocket) -> None:
    """Public live tick stream in local development. Hosted deployments can
    require a short-lived ticket issued by the authenticated Next.js server.
    Market data is a shared global feed, with per-IP and per-socket caps.

    Subscriptions are JSON control messages after connecting -
    {"subscribe": ["AAPL", "TSLA"]} / {"unsubscribe": ["TSLA"]} - so the
    client can change what it's watching without reconnecting.

    Fanout is in-process (see services/pubsub.py) - each connection owns
    one asyncio.Queue, subscribed to however many symbol channels it
    wants; publishing a tick just drops it into every subscribed queue.

    Rejections always accept() first and then close() with a real code
    and reason, instead of closing pre-accept. Closing before accept is
    interpreted inconsistently across ASGI runtimes (some turn it into a
    bare HTTP 403 during the upgrade, others just drop the socket) - on
    the wire that is indistinguishable from a network failure, which is
    exactly the bare "WebSocket connection failed" a browser shows with
    no code, no reason, and nothing to go on. Accepting first guarantees
    a real, inspectable RFC6455 close handshake on every platform. Every
    rejection is also logged with its reason - check the deployment's
    logs first when a client can't connect at all.
    """
    settings = get_settings()
    client_ip = websocket.client.host if websocket.client else "unknown"

    async def reject(reason: str, code: int = status.WS_1008_POLICY_VIOLATION) -> None:
        logger.warning(json.dumps({"event": "ws_reject", "reason": reason, "client_ip": client_ip}))
        try:
            await websocket.accept()
            await websocket.close(code=code, reason=reason[:120])
        except Exception:
            pass

    try:
        if settings.terminal_ws_secret:
            # FRONTEND_ORIGIN may list several allowed origins, comma-separated
            # (e.g. a production domain plus Vercel preview URLs) - matched
            # exactly (scheme + host + port), trailing slash ignored.
            allowed_origins = set(parse_frontend_origins(settings.frontend_origin))
            origin_header = websocket.headers.get("origin", "")
            normalized_origin = parse_frontend_origins(origin_header)
            origin = normalized_origin[0] if normalized_origin else ""
            if not origin or origin not in allowed_origins:
                await reject(f"origin_mismatch got={origin or '(none)'} allowed={sorted(allowed_origins)}")
                return

            ticket = websocket.query_params.get("ticket", "")
            try:
                payload = jwt.decode(ticket, settings.terminal_ws_secret, algorithms=["HS256"])
                if payload.get("scope") != "market_ticks":
                    raise JWTError("wrong scope")
            except JWTError as exc:
                await reject(f"ticket_invalid {exc}")
                return

        if _connections_per_ip.get(client_ip, 0) >= MAX_CONNECTIONS_PER_IP:
            await reject("per_ip_connection_limit", code=status.WS_1013_TRY_AGAIN_LATER)
            return
    except Exception as exc:  # noqa: BLE001 - never let a validation bug surface as a dropped socket
        logger.error(json.dumps({"event": "ws_reject", "reason": "unexpected_error", "error": str(exc)}))
        try:
            await websocket.accept()
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
        return

    await websocket.accept()
    _connections_per_ip[client_ip] = _connections_per_ip.get(client_ip, 0) + 1
    logger.info(json.dumps({"event": "ws_connect", "client_ip": client_ip}))

    queue: asyncio.Queue[str] = asyncio.Queue()
    subscribed: set[str] = set()

    async def relay_ticks() -> None:
        while True:
            message = await queue.get()
            await websocket.send_text(message)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            await websocket.send_text(json.dumps({"type": "heartbeat", "ts": time.time()}))

    async def handle_client_messages() -> None:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            subscribe = msg.get("subscribe", [])
            unsubscribe = msg.get("unsubscribe", [])
            if not isinstance(subscribe, list):
                subscribe = []
            if not isinstance(unsubscribe, list):
                unsubscribe = []
            for raw_sym in subscribe:
                if not isinstance(raw_sym, str):
                    continue
                sym = normalize_symbol(raw_sym)
                if sym and sym not in subscribed and len(subscribed) < MAX_SYMBOLS_PER_CONNECTION:
                    broker.subscribe(f"ticks:{sym}", queue)
                    subscribed.add(sym)
                    registry.add_ws_interest(sym)
            for raw_sym in unsubscribe:
                if not isinstance(raw_sym, str):
                    continue
                sym = normalize_symbol(raw_sym)
                if sym and sym in subscribed:
                    broker.unsubscribe(f"ticks:{sym}", queue)
                    subscribed.discard(sym)
                    registry.remove_ws_interest(sym)

    tasks = [
        asyncio.create_task(relay_ticks()),
        asyncio.create_task(heartbeat()),
        asyncio.create_task(handle_client_messages()),
    ]
    try:
        # Stop the connection as soon as either the client disconnects or a
        # sender/heartbeat task fails. A bare gather() can leave sibling tasks
        # running after a send failure and generate noisy unhandled errors.
        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                task.result()
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001 - isolate socket teardown
                logger.debug("ws_task_ended client_ip=%s error=%s", client_ip, type(exc).__name__)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for sym in subscribed:
            registry.remove_ws_interest(sym)
        broker.unsubscribe_all(queue, {f"ticks:{s}" for s in subscribed})
        _connections_per_ip[client_ip] = max(0, _connections_per_ip.get(client_ip, 1) - 1)
