from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase - only needed once you re-enable login for watchlists/orders.
    # Market data (quotes, candles, search, live ticks) needs none of this.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # App-issued short-lived tokens for the live-trading confirmation gate
    # (orders/trading_mode routers) - unrelated to market data.
    app_secret_key: str = "dev-only-change-me"
    live_intent_ttl_seconds: int = 300

    database_url: str = ""

    # Market data - zero-config by default (Yahoo Finance's public,
    # unauthenticated endpoints cover global search/quotes/candles; no key,
    # no signup, no login). Set FINNHUB_API_KEY to additionally overlay
    # genuine sub-second real-time ticks for US-listed symbols - see
    # app/services/finnhub_client.py and README for why it's optional.
    finnhub_api_key: str | None = None
    poll_interval_seconds: float = 3.0
    quote_cache_ttl_seconds: int = 5
    candle_cache_ttl_seconds: int = 30

    frontend_origin: str = "http://localhost:3000"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
