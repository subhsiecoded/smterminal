from functools import lru_cache
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase - only needed once you re-enable login for watchlists/orders.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # App-issued short-lived tokens for the live-trading confirmation gate.
    app_secret_key: str = "dev-only-change-me"
    live_intent_ttl_seconds: int = 300

    database_url: str = ""

    # Market data providers.
    finnhub_api_key: str | None = None
    poll_interval_seconds: float = 3.0
    quote_cache_ttl_seconds: int = 5
    candle_cache_ttl_seconds: int = 30

    # Comma-separated exact browser origins are supported, for example:
    # https://smterminal-web.vercel.app,https://smterminal.example.com
    frontend_origin: str = "http://localhost:3000,https://smterminal-web.vercel.app"
    environment: str = "development"

    # Server-to-server protection for hosted deployments.
    terminal_backend_token: str | None = None
    terminal_ws_secret: str | None = None


def parse_frontend_origins(raw: str | None) -> list[str]:
    """Return normalized, exact HTTP(S) origins from FRONTEND_ORIGIN.

    Paths, credentials, queries and fragments are intentionally rejected:
    browser Origin headers contain only scheme + authority.
    """
    origins: list[str] = []
    for item in (raw or "").split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            parsed = urlsplit(candidate)
            if (
                parsed.scheme.lower() not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                continue
            origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            if origin not in origins:
                origins.append(origin)
        except ValueError:
            continue
    return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_frontend_origins(settings: Settings) -> list[str]:
    """Return the exact browser origins allowed by this deployment.

    Development may use localhost. Production is restricted to explicitly
    configured HTTPS origins; HTTP and localhost origins are filtered out.
    The default list includes the current Vercel production domain so a fresh
    backend deployment does not silently default to localhost only.
    """
    origins = parse_frontend_origins(settings.frontend_origin)
    # This project's production Vercel domain is an exact trusted origin. Keep
    # it present even when an older backend environment still explicitly sets
    # FRONTEND_ORIGIN to localhost only; deployments can add custom domains.
    production_origin = "https://smterminal-web.vercel.app"
    if production_origin not in origins:
        origins.append(production_origin)
    if settings.environment.lower() == "production":
        origins = [
            origin for origin in origins
            if origin.startswith("https://")
            and "localhost" not in origin
            and "127.0.0.1" not in origin
        ]
    return origins
