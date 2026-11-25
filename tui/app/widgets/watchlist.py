from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, Static


class WatchlistPanel(Vertical):
    """A live-updating DataTable of symbol / last price / %change. Column
    keys are assigned explicitly ("sym"/"last"/"chg") because DataTable's
    auto-generated keys from add_columns() are opaque objects, not the
    label text - verified directly against the installed Textual version
    rather than assumed from the docs, since that assumption would have
    made every update_cell call silently fail.
    """

    class SymbolSelected(Message):
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            super().__init__()

    def __init__(self, symbols: list[str], **kwargs):
        super().__init__(id="watchlist-panel", **kwargs)
        self._symbols = [s.upper() for s in symbols]

    def compose(self):
        yield Static("WATCHLIST", id="watchlist-title")
        yield DataTable(id="watchlist-table", cursor_type="row", zebra_stripes=False)

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("SYM", key="sym", width=12)
        table.add_column("LAST", key="last", width=10)
        table.add_column("CHG%", key="chg", width=8)
        for symbol in self._symbols:
            table.add_row(symbol, "-", "-", key=symbol)

    def set_symbols(self, symbols: list[str]) -> None:
        table = self.query_one(DataTable)
        new_set = {s.upper() for s in symbols}
        old_set = set(self._symbols)
        for symbol in old_set - new_set:
            if symbol in table.rows:
                table.remove_row(symbol)
        for symbol in new_set - old_set:
            table.add_row(symbol, "-", "-", key=symbol)
        self._symbols = list(new_set)

    def update_quote(self, symbol: str, last: str, change_text: Text) -> None:
        table = self.query_one(DataTable)
        symbol = symbol.upper()
        if symbol not in table.rows:
            return
        table.update_cell(symbol, "last", last)
        table.update_cell(symbol, "chg", change_text)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value is not None:
            self.post_message(self.SymbolSelected(str(event.row_key.value)))
