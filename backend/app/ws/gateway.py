import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from app.config import get_settings

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
    """
    settings = get_settings()
    if settings.terminal_ws_secret:
        origin = websocket.headers.get("origin", "").rstrip("/")
        expected_origin = settings.frontend_origin.rstrip("/")
        if not origin or origin != expected_origin:
            logger.warning(
                "websocket_rejected reason=origin_mismatch received_origin=%r expected_origin=%r",
                origin,
                expected_origin,
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        ticket = websocket.query_params.get("ticket", "")
        try:
            payload = jwt.decode(ticket, settings.terminal_ws_secret, algorithms=["HS256"])
            if payload.get("scope") != "market_ticks":
                raise JWTError("wrong scope")
        except JWTError as exc:
            # Log the validation class, never the ticket or signing secret.
            logger.warning("websocket_rejected reason=invalid_ticket error=%s", type(exc).__name__)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    client_ip = websocket.client.host if websocket.client else "unknown"
    if _connections_per_ip.get(client_ip, 0) >= MAX_CONNECTIONS_PER_IP:
        logger.warning("websocket_rejected reason=connection_limit client_ip=%s", client_ip)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    _connections_per_ip[client_ip] = _connections_per_ip.get(client_ip, 0) + 1

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
            for raw_sym in msg.get("subscribe", []):
                sym = normalize_symbol(raw_sym)
                if sym and sym not in subscribed and len(subscribed) < MAX_SYMBOLS_PER_CONNECTION:
                    broker.subscribe(f"ticks:{sym}", queue)
                    subscribed.add(sym)
                    registry.add_ws_interest(sym)
            for raw_sym in msg.get("unsubscribe", []):
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
        await asyncio.gather(*tasks)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        for sym in subscribed:
            registry.remove_ws_interest(sym)
        broker.unsubscribe_all(queue, {f"ticks:{s}" for s in subscribed})
        _connections_per_ip[client_ip] = max(0, _connections_per_ip.get(client_ip, 1) - 1)
