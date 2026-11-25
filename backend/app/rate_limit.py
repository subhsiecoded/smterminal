from slowapi import Limiter
from slowapi.util import get_remote_address

# In-memory storage (slowapi's default - no storage_uri passed). Correct
# for a single-process deployment, which is what this app is: everything
# (poller, WS gateway, Finnhub overlay, HTTP routes) runs in one Python
# process, so there's no second instance for an in-memory rate limiter to
# disagree with. A multi-process/multi-replica deployment would need a
# shared backend (Redis, memcached) here instead - see the note in
# services/memory_store.py, which has the same single-process caveat.
limiter = Limiter(key_func=get_remote_address)
