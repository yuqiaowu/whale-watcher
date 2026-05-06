import sys
import unittest
from pathlib import Path

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from news_fetcher import _liquidity_change_from_history


class NewsFetcherTests(unittest.TestCase):
    def test_liquidity_change_uses_five_full_sessions_back(self):
        dates = pd.date_range("2026-04-27", periods=8, freq="B", tz="America/New_York")
        hist = pd.DataFrame(
            {"Close": [20.0, 18.0, 17.0, 16.0, 15.0, 14.0, 13.0, 12.0]},
            index=dates,
        )

        result = _liquidity_change_from_history(hist, lookback_sessions=5)

        self.assertEqual(12.0, result["latest"])
        self.assertEqual(17.0, result["reference"])
        self.assertEqual(5, result["lookback_sessions"])
        self.assertAlmostEqual(-29.4118, result["change_pct"], places=4)

    def test_liquidity_change_falls_back_when_history_is_short(self):
        dates = pd.date_range("2026-05-04", periods=3, freq="B", tz="America/New_York")
        hist = pd.DataFrame({"Close": [16.0, 18.0, 17.0]}, index=dates)

        result = _liquidity_change_from_history(hist, lookback_sessions=5)

        self.assertEqual(17.0, result["latest"])
        self.assertEqual(16.0, result["reference"])
        self.assertEqual(2, result["lookback_sessions"])
        self.assertAlmostEqual(6.25, result["change_pct"], places=4)


if __name__ == "__main__":
    unittest.main()
