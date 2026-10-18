from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _number(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    if positive and result <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return result


def _time(value: object, field: str) -> datetime:
    text = _text(value, field)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return result


@dataclass(frozen=True)
class Execution:
    venue: str
    quantity: float
    price: float
    fee: float
    timestamp: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "venue", _text(self.venue, "execution.venue"))
        object.__setattr__(self, "quantity", _number(self.quantity, "execution.quantity", positive=True))
        object.__setattr__(self, "price", _number(self.price, "execution.price", positive=True))
        object.__setattr__(self, "fee", _number(self.fee, "execution.fee"))
        timestamp = _time(self.timestamp, "execution.timestamp")
        object.__setattr__(self, "timestamp", timestamp.isoformat())


@dataclass(frozen=True)
class Order:
    order_id: str
    instrument: str
    side: Literal["buy", "sell"]
    quantity: float
    decision_price: float
    arrival_price: float
    decision_time: str
    arrival_time: str
    end_price: float
    end_time: str
    executions: tuple[Execution, ...]

    def __post_init__(self) -> None:
        for name in ("order_id", "instrument"):
            object.__setattr__(self, name, _text(getattr(self, name), f"order.{name}"))
        if self.side not in ("buy", "sell"):
            raise ValueError("order.side must be 'buy' or 'sell'")
        for name in ("quantity", "decision_price", "arrival_price", "end_price"):
            object.__setattr__(self, name, _number(getattr(self, name), f"order.{name}", positive=True))
        times = [
            _time(self.decision_time, "order.decision_time"),
            _time(self.arrival_time, "order.arrival_time"),
            _time(self.end_time, "order.end_time"),
        ]
        if not times[0] <= times[1] <= times[2]:
            raise ValueError("order timestamps must satisfy decision_time <= arrival_time <= end_time")
        object.__setattr__(self, "decision_time", times[0].isoformat())
        object.__setattr__(self, "arrival_time", times[1].isoformat())
        object.__setattr__(self, "end_time", times[2].isoformat())
        executions = tuple(self.executions)
        if any(not isinstance(item, Execution) for item in executions):
            raise ValueError("order.executions must contain Execution records")
        total_filled = math.fsum(item.quantity for item in executions)
        if total_filled > self.quantity + max(1e-9, self.quantity * 1e-12):
            raise ValueError(f"order {self.order_id!r} executions exceed order quantity")
        arrival = _time(self.arrival_time, "order.arrival_time")
        end = _time(self.end_time, "order.end_time")
        for execution in executions:
            executed_at = _time(execution.timestamp, "execution.timestamp")
            if not arrival <= executed_at <= end:
                raise ValueError(f"execution timestamp for order {self.order_id!r} must be between arrival and end")
        object.__setattr__(self, "executions", executions)

    @property
    def filled_quantity(self) -> float:
        return math.fsum(execution.quantity for execution in self.executions)

    @property
    def unfilled_quantity(self) -> float:
        return max(0.0, self.quantity - self.filled_quantity)
