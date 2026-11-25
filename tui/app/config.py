import os
from pathlib import Path

API_BASE = os.environ.get("MARKET_TERMINAL_API_BASE", "http://localhost:8000")
WS_BASE = os.environ.get("MARKET_TERMINAL_WS_BASE", "ws://localhost:8000")

STATE_DIR = Path(os.environ.get("MARKET_TERMINAL_STATE_DIR", Path.home() / ".market-terminal"))
WATCHLIST_FILE = STATE_DIR / "watchlist.json"

DEFAULT_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "^NSEI", "^NSEBANK", "BTC-USD", "AAPL"]

HEARTBEAT_TIMEOUT_SECONDS = 30  # two missed 15s server heartbeats = treat the socket as dead
RECONNECT_MAX_BACKOFF_SECONDS = 15
