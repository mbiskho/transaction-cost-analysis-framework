from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from .models import Order


def _finite(value: float, context: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"cost calculation overflow for {context}")
    return value


def _sum(values: Iterable[float], context: str) -> float:
    try:
        return _finite(math.fsum(values), context)
    except OverflowError as error:
        raise ValueError(f"cost calculation overflow for {context}") from error


class TransactionCostAnalyzer:
    """Arrival-price implementation shortfall with signed costs (positive is adverse)."""

    def __init__(self, orders: Iterable[Order], currency: str = "USD") -> None:
        self.orders = tuple(orders)
        if not self.orders:
            raise ValueError("at least one order is required")
        if any(not isinstance(order, Order) for order in self.orders):
            raise ValueError("orders must contain Order records")
        if len({order.order_id for order in self.orders}) != len(self.orders):
            raise ValueError("order IDs must be unique")
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError("currency must be a non-empty string")
        self.currency = currency.strip()

    def analyze(self) -> dict[str, Any]:
        rows = [self._order_result(order) for order in self.orders]
        total_quantity = _sum((order.quantity for order in self.orders), "order quantity")
        denominator = _sum((order.quantity * order.arrival_price for order in self.orders), "arrival notional")
        totals = {
            key: round(_sum((row[key] for row in rows), key), 10)
            for key in ("explicit_cost", "delay_cost", "market_impact", "opportunity_cost", "total_shortfall")
        }
        totals["notional"] = denominator
        totals["order_quantity"] = total_quantity
        totals["filled_quantity"] = _sum((order.filled_quantity for order in self.orders), "filled quantity")
        totals["unfilled_quantity"] = _sum((order.unfilled_quantity for order in self.orders), "unfilled quantity")
        totals["shortfall_bps"] = round(_finite(10_000 * totals["total_shortfall"] / denominator, "shortfall bps"), 8)

        by_instrument = self._group(rows, "instrument")
        venue_map: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for row in rows:
            for execution in row["executions"]:
                direction = 1 if row["side"] == "buy" else -1
                impact = direction * execution["quantity"] * (execution["price"] - row["arrival_price"])
                venue_map[execution["venue"]].append((row, {
                    "quantity": execution["quantity"],
                    "explicit_cost": execution["fee"],
                    "market_impact": impact,
                    "arrival_price": row["arrival_price"],
                }))
        by_venue: dict[str, dict[str, float]] = {}
        for venue, items in sorted(venue_map.items()):
            executions = [item for _, item in items]
            qty = _sum((item["quantity"] for item in executions), f"{venue} filled quantity")
            explicit = _sum((item["explicit_cost"] for item in executions), f"{venue} explicit cost")
            impact = _sum((item["market_impact"] for item in executions), f"{venue} market impact")
            notion = _sum((item["quantity"] * item["arrival_price"] for item in executions), f"{venue} notional")
            by_venue[venue] = {
                "filled_quantity": qty,
                "explicit_cost": round(explicit, 10),
                "market_impact": round(impact, 10),
                "execution_shortfall": round(_finite(explicit + impact, f"{venue} execution shortfall"), 10),
                "shortfall_bps": round(_finite(10_000 * (explicit + impact) / notion, f"{venue} shortfall bps"), 8) if notion else 0.0,
            }
        return {
            "currency": self.currency,
            "benchmark": "arrival_price",
            "cost_convention": "positive values are adverse; negative values are favorable",
            "totals": totals,
            "orders": rows,
            "by_instrument": by_instrument,
            "by_venue": by_venue,
        }

    def _order_result(self, order: Order) -> dict[str, Any]:
        direction = 1 if order.side == "buy" else -1
        explicit = _sum((execution.fee for execution in order.executions), f"{order.order_id} explicit cost")
        delay = _finite(direction * order.quantity * (order.arrival_price - order.decision_price), f"{order.order_id} delay cost")
        impact = _sum((
            direction * execution.quantity * (execution.price - order.arrival_price)
            for execution in order.executions
        ), f"{order.order_id} market impact")
        opportunity = _finite(direction * order.unfilled_quantity * (order.end_price - order.arrival_price), f"{order.order_id} opportunity cost")
        total = _sum((explicit, delay, impact, opportunity), order.order_id)
        notional = _finite(order.quantity * order.arrival_price, f"{order.order_id} notional")
        return {
            "order_id": order.order_id,
            "instrument": order.instrument,
            "side": order.side,
            "order_quantity": order.quantity,
            "filled_quantity": order.filled_quantity,
            "unfilled_quantity": order.unfilled_quantity,
            "decision_price": order.decision_price,
            "arrival_price": order.arrival_price,
            "vwap": (
                _sum((execution.quantity * execution.price for execution in order.executions), f"{order.order_id} execution notional")
                / order.filled_quantity if order.filled_quantity else None
            ),
            "end_price": order.end_price,
            "explicit_cost": round(explicit, 10),
            "delay_cost": round(delay, 10),
            "market_impact": round(impact, 10),
            "opportunity_cost": round(opportunity, 10),
            "total_shortfall": round(total, 10),
            "shortfall_bps": round(_finite(10_000 * total / notional, f"{order.order_id} shortfall bps"), 8),
            "executions": [
                {"venue": item.venue, "quantity": item.quantity, "price": item.price, "fee": item.fee}
                for item in order.executions
            ],
        }

    def _group(self, rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, float]]:
        keys = ("explicit_cost", "delay_cost", "market_impact", "opportunity_cost", "total_shortfall")
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row[field]].append(row)
        result = {}
        for group, items in sorted(grouped.items()):
            combined = {key: round(_sum((item[key] for item in items), f"{group} {key}"), 10) for key in keys}
            notional = _sum((item["order_quantity"] * item["arrival_price"] for item in items), f"{group} notional")
            combined["order_quantity"] = _sum((item["order_quantity"] for item in items), f"{group} order quantity")
            combined["filled_quantity"] = _sum((item["filled_quantity"] for item in items), f"{group} filled quantity")
            combined["unfilled_quantity"] = _sum((item["unfilled_quantity"] for item in items), f"{group} unfilled quantity")
            combined["shortfall_bps"] = round(_finite(10_000 * combined["total_shortfall"] / notional, f"{group} shortfall bps"), 8) if notional else 0.0
            result[group] = combined
        return result
