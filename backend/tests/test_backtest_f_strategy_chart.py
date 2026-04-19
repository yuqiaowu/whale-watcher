import unittest

from backend.backtest_f_strategy_chart import run_backtest


class BacktestFStrategyChartTest(unittest.TestCase):
    def test_run_backtest_returns_portfolio_and_trades(self) -> None:
        result = run_backtest()
        self.assertIn("portfolio", result)
        self.assertIn("per_instrument", result)
        self.assertIn("all_trades", result)
        self.assertGreater(result["dataset"]["rows"], 0)


if __name__ == "__main__":
    unittest.main()
