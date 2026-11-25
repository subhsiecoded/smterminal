from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, Static


def parse_command(raw: str) -> tuple[str, list[str]]:
    """Pure parser: 'add AAPL' -> ('add', ['AAPL']). A bare symbol with no
    verb ('AAPL') is treated as 'select AAPL' - typing a ticker and
    hitting enter should just jump to it, no verb required.
    """
    parts = raw.strip().split()
    if not parts:
        return "", []
    verb, *args = parts
    verb = verb.lower()
    known_verbs = {
        "add", "watch", "rm", "remove", "unwatch", "select", "sel",
        "search", "find", "india", "movers", "india-movers", "screener", "nse", "news", "interval", "int",
        "quit", "exit", "help", "?",
    }
    if verb not in known_verbs:
        # No recognized verb - treat the whole first token as a symbol.
        return "select", [parts[0].upper()]
    # search/find/india take free-text queries (company names, etc.) -
    # don't force-uppercase those the way a ticker symbol argument needs.
    return verb, [a.upper() if verb not in ("search", "find", "india") else a for a in args]


class CommandBar(Vertical):
    class CommandSubmitted(Message):
        def __init__(self, verb: str, args: list[str]) -> None:
            self.verb = verb
            self.args = args
            super().__init__()

    def compose(self):
        with Horizontal(id="command-row"):
            yield Static(">", id="command-prompt")
            yield Input(placeholder="add AAPL · select TSLA · movers gainers · news · help", id="command-input")
        yield Static("", id="command-output")

    def set_feedback(self, text: str) -> None:
        # Wrapped in a plain Text object, NOT passed as a raw string:
        # Static.update(str) runs the string through Rich's markup parser,
        # which silently eats anything that looks like a tag - and every
        # feedback message in this app is prefixed with a bracketed label
        # like "[chart] ...". A raw string here would quietly strip that
        # prefix (and any brackets an upstream API error happens to
        # contain) with no visible sign anything was wrong. Text() renders
        # literally, markup included.
        self.query_one("#command-output", Static).update(Text(text))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value
        event.input.value = ""
        if not raw.strip():
            return
        verb, args = parse_command(raw)
        self.post_message(self.CommandSubmitted(verb, args))
