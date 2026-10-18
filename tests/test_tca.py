from __future__ import annotations

import contextlib
import io
import shutil
import unittest
from pathlib import Path

from transaction_cost_analysis import Execution, Order, TransactionCostAnalyzer
from transaction_cost_analysis.cli import load_analyzer, main
from transaction_cost_analysis.visualization import render_flow_svg, render_overview_svg, write_reports


def order(**overrides):
    fields = dict(
        order_id="o1", instrument="XYZ", side="buy", quantity=100,
        decision_price=9.9, arrival_price=10.0, decision_time="2026-01-01T10:00:00Z",
        arrival_time="2026-01-01T10:01:00Z", end_price=10.5,
        end_time="2026-01-01T10:10:00Z",
        executions=(Execution("X", 60, 10.2, 1.5, "2026-01-01T10:03:00Z"),),
    )
    fields.update(overrides)
    return Order(**fields)


class TransactionCostTests(unittest.TestCase):
    def test_components_and_signed_convention_reconcile(self):
        report = TransactionCostAnalyzer([order()]).analyze()
        row, totals = report["orders"][0], report["totals"]
        self.assertAlmostEqual(row["explicit_cost"], 1.5)
        self.assertAlmostEqual(row["delay_cost"], 10.0)
        self.assertAlmostEqual(row["market_impact"], 12.0)
        self.assertAlmostEqual(row["opportunity_cost"], 20.0)
        self.assertAlmostEqual(row["total_shortfall"], 43.5)
        self.assertAlmostEqual(totals["shortfall_bps"], 435.0)
        self.assertAlmostEqual(totals["total_shortfall"], sum(totals[k] for k in (
            "explicit_cost", "delay_cost", "market_impact", "opportunity_cost"
        )))

    def test_sell_side_sign_and_venue_aggregation(self):
        sell = order(side="sell", executions=(Execution("X", 100, 9.8, 0.5, "2026-01-01T10:03:00Z"),))
        result = TransactionCostAnalyzer([sell]).analyze()
        self.assertAlmostEqual(result["orders"][0]["market_impact"], 20)
        self.assertAlmostEqual(result["by_venue"]["X"]["execution_shortfall"], 20.5)
        self.assertEqual(result["by_venue"]["X"]["filled_quantity"], 100)

    def test_all_unfilled_order_has_opportunity_cost(self):
        result = TransactionCostAnalyzer([order(executions=())]).analyze()
        self.assertEqual(result["orders"][0]["market_impact"], 0)
        self.assertAlmostEqual(result["orders"][0]["opportunity_cost"], 50)

    def test_rejects_quantity_overfill_and_timestamp_order(self):
        with self.assertRaisesRegex(ValueError, "exceed order quantity"):
            order(executions=(Execution("X", 101, 10, 0, "2026-01-01T10:03:00Z"),))
        with self.assertRaisesRegex(ValueError, "between arrival and end"):
            order(executions=(Execution("X", 10, 10, 0, "2026-01-01T10:00:30Z"),))

    def test_rejects_naive_timestamp_bad_side_duplicate_id(self):
        with self.assertRaisesRegex(ValueError, "include a timezone"):
            order(decision_time="2026-01-01T10:00:00")
        with self.assertRaisesRegex(ValueError, "side"):
            order(side="hold")
        with self.assertRaisesRegex(ValueError, "unique"):
            TransactionCostAnalyzer([order(), order()])

    def test_reports_are_data_driven_svg_and_valid_png(self):
        report = TransactionCostAnalyzer([order()]).analyze()
        self.assertIn("43.50", render_overview_svg(report))
        self.assertIn("X", render_flow_svg(report))
        directory = Path(__file__).parents[1] / "reports" / ".test-output"
        try:
            write_reports(report, directory)
            for name in ("overview", "flow"):
                content = (directory / f"{name}.png").read_bytes()
                self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertGreater(len(content), 1000)
                self.assertTrue((directory / f"{name}.svg").exists())
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_loads_sample_and_cli_json(self):
        sample = Path(__file__).parents[1] / "examples" / "orders.json"
        report = load_analyzer(sample).analyze()
        self.assertEqual(len(report["orders"]), 3)
        self.assertEqual(report["by_venue"]["BATS"]["filled_quantity"], 650)
        self.assertEqual(set(report["by_instrument"]), {"AAPL", "MSFT"})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(sample), "--format", "json"]), 0)


if __name__ == "__main__":
    unittest.main()
