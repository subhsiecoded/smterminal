import asyncio
import json
import time
from typing import Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

from . import config
from .storage import _clean_symbols

OnTick = Callable[[dict], Awaitable[None]]
OnStatus = Callable[[str], Awaitable[None]]


class TickStream:
    """Public WS connection (no auth - matches the backend's public
    /ws/ticks). Reconnects with exponential backoff on drop, and treats a
    missed server heartbeat (sent every 15s) as a dead connection even if
    the transport hasn't noticed yet - the same logic the web client used,
    just in asyncio instead of browser WebSocket callbacks.
    """

    def __init__(self, symbols: list[str] | None = None):
        self._wanted: set[str] = set(_clean_symbols(symbols or []))
        self._subscribed: set[str] = set()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._stopped = False
        self._last_heartbeat = 0.0

    def update_symbols(self, symbols: list[str]) -> None:
        self._wanted = set(_clean_symbols(symbols))
        if self._ws is not None:
            asyncio.create_task(self._sync_subscriptions())

    async def _sync_subscriptions(self) -> None:
        if self._ws is None:
            return
        to_sub = list(self._wanted - self._subscribed)
        to_unsub = list(self._subscribed - self._wanted)
        try:
            if to_sub:
                await self._ws.send(json.dumps({"subscribe": to_sub}))
                self._subscribed |= set(to_sub)
            if to_unsub:
                await self._ws.send(json.dumps({"unsubscribe": to_unsub}))
                self._subscribed -= set(to_unsub)
        except ConnectionClosed:
            pass  # the main run loop's reconnect handles this

    def stop(self) -> None:
        self._stopped = True

    async def run(self, on_tick: OnTick, on_status: OnStatus) -> None:
        backoff = 1.0
        while not self._stopped:
            await on_status("reconnecting" if backoff > 1.0 else "connecting")
            try:
                async with websockets.connect(f"{config.WS_BASE}/ws/ticks") as ws:
                    self._ws = ws
                    self._subscribed = set()
                    backoff = 1.0
                    await self._sync_subscriptions()
                    await on_status("live")
                    self._last_heartbeat = time.time()

                    while not self._stopped:
                        timeout = config.HEARTBEAT_TIMEOUT_SECONDS - (time.time() - self._last_heartbeat)
                        if timeout <= 0:
                            await on_status("stale")
                            break  # force a reconnect
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        except asyncio.TimeoutError:
                            continue  # loop back and re-check the heartbeat deadline
                        msg = json.loads(raw)
                        if msg.get("type") == "heartbeat":
                            self._last_heartbeat = time.time()
                        else:
                            await on_tick(msg)
            except (ConnectionClosed, OSError) as exc:
                await on_status("reconnecting")
                _ = exc  # transient - just retry
            finally:
                self._ws = None

            if self._stopped:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, config.RECONNECT_MAX_BACKOFF_SECONDS)

        await on_status("closed")
