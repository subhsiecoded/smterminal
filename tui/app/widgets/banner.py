from datetime import datetime, timezone

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

_STATUS_DOTS = {
    "connecting": ("●", "#aaaaaa", "CONNECTING"),
    "live": ("●", "#00ff41", "LIVE"),
    "reconnecting": ("●", "#ffb000", "RECONNECTING"),
    "stale": ("●", "#ff3b3b", "STALE"),
    "closed": ("●", "#ff3b3b", "DISCONNECTED"),
}


class Banner(Static):
    status = reactive("connecting")

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def render(self) -> Text:
        dot, color, label = _STATUS_DOTS.get(self.status, _STATUS_DOTS["connecting"])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        # Keep the useful connection/time indicator, but leave the large
        # ASCII-art brand banner out of the dashboard to maximize chart space.
        text = Text(f"  {now}   ", style="#006622")
        text.append(dot, style=color)
        text.append(f" {label}", style=color)
        return text
