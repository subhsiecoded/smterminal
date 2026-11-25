"""In-process publish/subscribe, replacing Redis pub/sub. Each WS
connection owns ONE asyncio.Queue and subscribes it to however many
symbol channels it wants; publishing a tick just fans it out to every
queue currently subscribed to that channel. Correct for exactly the same
reason memory_store.py is: everything lives in one process.
"""

import asyncio
from collections import defaultdict


class PubSub:
    def __init__(self) -> None:
        self._channels: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, channel: str, queue: asyncio.Queue) -> None:
        self._channels[channel].add(queue)

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        subscribers = self._channels.get(channel)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._channels[channel]

    def unsubscribe_all(self, queue: asyncio.Queue, channels: set[str]) -> None:
        for channel in channels:
            self.unsubscribe(channel, queue)

    def publish(self, channel: str, message: str) -> None:
        for queue in self._channels.get(channel, ()):
            queue.put_nowait(message)


# One broker per process, shared by cache.py (publisher) and the WS
# gateway (subscriber).
broker = PubSub()
