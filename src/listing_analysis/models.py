"""Dependency-free domain models and JSON conversion."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class UpbitListing:
    ticker: str
    korean_name: str
    market: str
    notice_id: str
    notice_url: str
    notice_published_at: datetime
    trading_started_at: datetime


@dataclass(frozen=True)
class BinanceContract:
    symbol: str
    base_asset: str
    quote_asset: str
    contract_type: str
    status: str
    onboard_at: datetime
    contract_multiplier: Decimal = Decimal("1")


@dataclass(frozen=True)
class PriceObservation:
    target_offset_days: int
    target_date: str
    close_time: datetime | None
    close_price: Decimal | None
    status: str
    reason: str | None = None


@dataclass
class ListingAnalysis:
    upbit_listing: UpbitListing
    binance_contract: BinanceContract | None
    observations: dict[int, PriceObservation]
    returns: dict[int, Decimal | None]
    mapping_status: str = "AVAILABLE"
    warning: str | None = None


def json_value(value: Any) -> Any:
    """Convert models without destroying Decimal precision."""
    if hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value

