from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from .analytics import TransactionCostAnalyzer
from .models import Execution, Order
from .visualization import render_flow_svg, render_overview_svg, write_reports


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _array(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _required(obj: dict[str, Any], key: str, context: str) -> Any:
    if key not in obj:
        raise ValueError(f"{context}.{key} is required")
    return obj[key]


def load_analyzer(path: Path) -> TransactionCostAnalyzer:
    with path.open(encoding="utf-8") as source:
        document = _object(json.load(source), "input")
    records = []
    for index, raw in enumerate(_array(_required(document, "orders", "input"), "orders")):
        context = f"orders[{index}]"
        order = _object(raw, context)
        executions = []
        for fill_index, raw_fill in enumerate(_array(order.get("executions", []), f"{context}.executions")):
            fill_context = f"{context}.executions[{fill_index}]"
            fill = _object(raw_fill, fill_context)
            executions.append(Execution(
                venue=_required(fill, "venue", fill_context),
                quantity=_number(_required(fill, "quantity", fill_context), f"{fill_context}.quantity"),
                price=_number(_required(fill, "price", fill_context), f"{fill_context}.price"),
                fee=_number(fill.get("fee", 0.0), f"{fill_context}.fee"),
                timestamp=_required(fill, "timestamp", fill_context),
            ))
        records.append(Order(
            order_id=_required(order, "order_id", context),
            instrument=_required(order, "instrument", context),
            side=_required(order, "side", context),
            quantity=_number(_required(order, "quantity", context), f"{context}.quantity"),
            decision_price=_number(_required(order, "decision_price", context), f"{context}.decision_price"),
            arrival_price=_number(_required(order, "arrival_price", context), f"{context}.arrival_price"),
            decision_time=_required(order, "decision_time", context),
            arrival_time=_required(order, "arrival_time", context),
            end_price=_number(_required(order, "end_price", context), f"{context}.end_price"),
            end_time=_required(order, "end_time", context),
            executions=tuple(executions),
        ))
    return TransactionCostAnalyzer(records, currency=document.get("currency", "USD"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure execution implementation shortfall against arrival price.")
    parser.add_argument("input", type=Path, help="JSON file with order and execution records")
    parser.add_argument("--format", choices=("text", "json", "svg"), default="text")
    parser.add_argument("--chart", choices=("overview", "flow"), default="overview", help="SVG chart selection")
    parser.add_argument("--write-reports", type=Path, metavar="DIR", help="write overview/flow SVG and PNG charts")
    args = parser.parse_args(argv)
    try:
        report = load_analyzer(args.input).analyze()
        if args.write_reports:
            write_reports(report, args.write_reports)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.format == "svg":
        print(render_flow_svg(report) if args.chart == "flow" else render_overview_svg(report))
    else:
        totals = report["totals"]
        print(f"Arrival-price implementation shortfall ({report['currency']})")
        print(f"{'Component':<22} {'Cost':>16}")
        for label, key in (
            ("Explicit fees", "explicit_cost"), ("Delay", "delay_cost"),
            ("Market impact", "market_impact"), ("Opportunity cost", "opportunity_cost"),
        ):
            print(f"{label:<22} {totals[key]:>16,.2f}")
        print(f"{'Total shortfall':<22} {totals['total_shortfall']:>16,.2f}")
        print(f"Shortfall bps: {totals['shortfall_bps']:.2f} | filled {totals['filled_quantity']:,.0f} / {totals['order_quantity']:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
