from pathlib import Path


def test_banner_source_keeps_status_line_but_not_ascii_logo():
    tui_root = Path(__file__).parents[1]
    banner_source = (tui_root / "app" / "widgets" / "banner.py").read_text(encoding="utf-8")
    stylesheet = (tui_root / "app" / "terminal.tcss").read_text(encoding="utf-8")

    assert "_LOGO" not in banner_source
    assert "UTC" in banner_source
    assert "_STATUS_DOTS" in banner_source
    assert "#banner {\n    height: 2;" in stylesheet
