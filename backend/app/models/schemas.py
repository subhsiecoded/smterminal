from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Quote(BaseModel):
    symbol: str
    ltp: float
    change: float = 0.0
    change_pct: float = 0.0
    # Equity feeds normally report integer shares; aggregated crypto feeds can
    # report fractional quote-currency notional. Keep the numeric value intact.
    volume: int | float | None = None
    volume_unit: str | None = None
    # Top-of-book only, and only present when the upstream feed has it
    # (mostly US tickers via Yahoo's free quote data) - never fabricated.
    bid: float | None = None
    ask: float | None = None
    bid_size: int | None = None
    ask_size: int | None = None
    currency: str | None = None
    exchange: str | None = None
    source: Literal["poll", "stream"] = "poll"
    ts: datetime


class Candle(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class OrderCreate(BaseModel):
    instrument_id: int
    side: Literal["BUY", "SELL"]
    qty: float = Field(gt=0, description="Must be a positive quantity")
    order_type: Literal["MARKET", "LIMIT", "SL", "SL-M"] = "MARKET"
    price: float | None = Field(default=None, gt=0)
    is_paper: bool = True

    @model_validator(mode="after")
    def price_required_for_limit_orders(self) -> "OrderCreate":
        if self.order_type in ("LIMIT", "SL") and self.price is None:
            raise ValueError(f"{self.order_type} orders require a price")
        return self


class OrderOut(BaseModel):
    id: int
    instrument_id: int
    side: str
    qty: float
    price: float | None
    order_type: str
    status: str
    is_paper: bool
    ts: datetime


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class WatchlistItemCreate(BaseModel):
    instrument_id: int


class AlertCondition(BaseModel):
    op: Literal["gte", "lte", "gt", "lt", "eq"]
    field: Literal["ltp", "volume", "change_pct"]
    value: float


class AlertCreate(BaseModel):
    instrument_id: int
    condition: AlertCondition
