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
