import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from grid_backtest import GridBacktestConfig, run_grid_backtest, scan_grid_parameters


class GridBacktestTests(unittest.TestCase):
    def test_range_rotation_produces_fills_and_positive_capture(self):
        prices = [100, 98, 96, 98, 100, 102, 100, 98, 100]
        config = GridBacktestConfig(
            lower_bound=95,
            upper_bound=105,
            grid_count=5,
            fee_rate=0.0001,
            slippage_rate=0.0001,
            per_grid_notional=100,
            take_profit_pct=None,
        )

        result = run_grid_backtest(prices, config)

        self.assertTrue(result["implemented"])
        self.assertTrue(result["valid"])
        self.assertGreater(result["summary"]["fill_count"], 0)
        self.assertGreater(result["metrics"]["fees_paid"], 0)
        self.assertGreater(result["metrics"]["range_capture_efficiency"], 0)
        self.assertIsNotNone(result["metrics"]["avg_profit_per_fill"])
        self.assertGreaterEqual(result["metrics"]["fee_drag_ratio"], 0)
        self.assertGreaterEqual(result["summary"]["buy_fills"], 1)
        self.assertGreaterEqual(result["summary"]["sell_fills"], 1)

    def test_breakout_forces_shutdown_and_inventory_flatten(self):
        prices = [100, 99, 98, 101, 104, 107]
        config = GridBacktestConfig(
            lower_bound=95,
            upper_bound=105,
            grid_count=5,
            fee_rate=0.0001,
            slippage_rate=0.0001,
            per_grid_notional=100,
            take_profit_pct=None,
        )

        result = run_grid_backtest(prices, config)

        self.assertEqual(result["summary"]["breakout_exit"], "upper_breakout")
        self.assertGreaterEqual(result["summary"]["forced_exit_qty"], 0)
        self.assertAlmostEqual(result["metrics"]["floating_inventory_pnl"], 0.0, places=6)

    def test_take_profit_exits_before_late_breakout_when_profit_target_is_hit(self):
        prices = [100, 99, 98, 101, 104, 107]
        config = GridBacktestConfig(
            lower_bound=95,
            upper_bound=105,
            grid_count=5,
            fee_rate=0.0001,
            slippage_rate=0.0001,
            per_grid_notional=100,
            take_profit_pct=0.04,
            stop_loss_pct=None,
        )

        result = run_grid_backtest(prices, config)

        self.assertEqual(result["summary"]["breakout_exit"], "take_profit")
        self.assertEqual(result["summary"]["exit_reason"], "TP_REACHED")
        self.assertAlmostEqual(result["metrics"]["floating_inventory_pnl"], 0.0, places=6)

    def test_ohlc_intrabar_crosses_and_funding_are_accounted_for(self):
        bars = [
            {"open": 100, "high": 100, "low": 100, "close": 100},
            {"open": 100, "high": 101, "low": 97, "close": 98},
            {"open": 98, "high": 103, "low": 98, "close": 102},
        ]
        config = GridBacktestConfig(
            lower_bound=95,
            upper_bound=105,
            grid_count=5,
            fee_rate=0.0001,
            slippage_rate=0.0001,
            per_grid_notional=100,
            funding_rate_per_bar=0.0002,
            take_profit_pct=None,
            stop_loss_pct=None,
        )

        result = run_grid_backtest(bars, config)

        self.assertGreater(result["summary"]["fill_count"], 0)
        self.assertGreater(result["metrics"]["funding_paid"], 0)
        self.assertIn("return_on_margin_pct", result["metrics"])
        self.assertIn("max_drawdown_pct", result["metrics"])

    def test_scan_grid_parameters_returns_ranked_candidates(self):
        prices = [100, 98, 96, 98, 100, 102, 100, 98, 100]
        result = scan_grid_parameters(
            prices,
            lower_bound=95,
            upper_bound=105,
            grid_counts=[4, 6],
            fee_rates=[0.0001],
            slippage_rates=[0.0001],
            per_grid_notionals=[50.0, 100.0],
            leverage_values=[3.0],
            top_k=3,
        )

        self.assertEqual(result["strategy_family"], "GRID")
        self.assertEqual(result["tested"], 4)
        self.assertEqual(len(result["top_results"]), 3)
        self.assertIn("config", result["top_results"][0])
        self.assertIn("metrics", result["top_results"][0])
        self.assertIn("score", result["top_results"][0])


if __name__ == "__main__":
    unittest.main()
