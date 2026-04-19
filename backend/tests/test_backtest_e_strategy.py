import unittest

from backend.backtest_e_strategy import run_backtest


class BacktestEStrategyTest(unittest.TestCase):
    def test_run_backtest_returns_expected_shape(self):
        result = run_backtest()
        self.assertIn("portfolio", result)
        self.assertIn("per_instrument", result)
        self.assertIn("all_trades", result)
        self.assertGreaterEqual(result["portfolio"]["total_trades"], 1)
        self.assertGreater(len(result["per_instrument"]), 0)


if __name__ == "__main__":
    unittest.main()
