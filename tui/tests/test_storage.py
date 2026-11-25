import json

from app import storage


def test_load_watchlist_removes_command_labels_and_persists_clean_copy(tmp_path, monkeypatch):
    watch_file = tmp_path / "watchlist.json"
    watch_file.write_text(json.dumps([
        "RELIANCE.NS", "INDIA-MOVERS", "TCS.NS", "SCREENER", "RELIANCE.NS"
    ]))
    monkeypatch.setattr(storage.config, "WATCHLIST_FILE", watch_file)
    monkeypatch.setattr(storage.config, "STATE_DIR", tmp_path)

    result = storage.load_watchlist()

    assert result == ["RELIANCE.NS", "TCS.NS"]
    assert json.loads(watch_file.read_text()) == ["RELIANCE.NS", "TCS.NS"]


def test_save_watchlist_never_persists_reserved_commands(tmp_path, monkeypatch):
    watch_file = tmp_path / "watchlist.json"
    monkeypatch.setattr(storage.config, "WATCHLIST_FILE", watch_file)
    monkeypatch.setattr(storage.config, "STATE_DIR", tmp_path)

    storage.save_watchlist(["INDIA-MOVERS", "INFY.NS", "NSE"])

    assert json.loads(watch_file.read_text()) == ["INFY.NS"]
