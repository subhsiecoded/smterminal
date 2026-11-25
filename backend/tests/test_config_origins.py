from app.config import parse_frontend_origins


def test_parse_frontend_origins_normalizes_and_deduplicates():
    assert parse_frontend_origins(
        " https://SMTerminal-Web.vercel.app/ , https://smterminal-web.vercel.app, http://localhost:3000 "
    ) == [
        "https://smterminal-web.vercel.app",
        "http://localhost:3000",
    ]


def test_parse_frontend_origins_rejects_non_origins():
    assert parse_frontend_origins(
        "https://example.com/path,https://user:pass@example.com,ftp://example.com,not-a-url"
    ) == []


def test_parse_frontend_origins_accepts_multiple_explicit_hosts():
    assert parse_frontend_origins(
        "https://smterminal-web.vercel.app,https://terminal.example.com"
    ) == [
        "https://smterminal-web.vercel.app",
        "https://terminal.example.com",
    ]


def test_production_frontend_origins_adds_exact_vercel_origin_and_filters_localhost():
    from app.config import Settings, get_frontend_origins

    settings = Settings(
        environment="production",
        frontend_origin="http://localhost:3000",
    )
    assert get_frontend_origins(settings) == ["https://smterminal-web.vercel.app"]


def test_development_frontend_origins_keep_localhost_and_vercel():
    from app.config import Settings, get_frontend_origins

    settings = Settings(
        environment="development",
        frontend_origin="http://localhost:3000",
    )
    assert get_frontend_origins(settings) == [
        "http://localhost:3000",
        "https://smterminal-web.vercel.app",
    ]
