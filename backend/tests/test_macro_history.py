import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from macro_history import MacroHistory


class MacroHistoryTests(unittest.TestCase):
    def test_stablecoin_fields_are_persisted_and_std_is_computed(self):
        with TemporaryDirectory() as temp_dir:
            history = MacroHistory(temp_dir)
            now = datetime.utcnow()
            history.history = [
                {
                    "timestamp": (now - timedelta(days=2)).isoformat(),
                    "global_stable_flow": 100_000_000,
                    "global_stable_market_cap": 200_000_000_000,
                },
                {
                    "timestamp": (now - timedelta(days=1)).isoformat(),
                    "global_stable_flow": 250_000_000,
                    "global_stable_market_cap": 201_000_000_000,
                },
                {
                    "timestamp": now.isoformat(),
                    "global_stable_flow": -50_000_000,
                    "global_stable_market_cap": 199_500_000_000,
                },
            ]

            std_value = history.get_std("global_stable_flow", days=30)
            recent_values = history.get_recent_values("global_stable_flow", days=30)

            self.assertEqual(recent_values, [100_000_000.0, 250_000_000.0, -50_000_000.0])
            self.assertIsNotNone(std_value)
            self.assertGreater(std_value, 0)

    def test_update_latest_snapshot_merges_stable_metrics(self):
        with TemporaryDirectory() as temp_dir:
            history = MacroHistory(temp_dir)
            history.add_snapshot(
                {"implied_rate": 4.5},
                {"price": 145.0},
                {"dxy": {"price": 106.0}, "vix": {"price": 19.0}, "us10y": {"price": 4.3}},
            )

            history.update_latest_snapshot({
                "global_stable_flow": 180_000_000,
                "global_stable_market_cap": 210_000_000_000,
            })

            self.assertEqual(history.history[-1]["global_stable_flow"], 180_000_000)
            self.assertEqual(history.history[-1]["global_stable_market_cap"], 210_000_000_000)


if __name__ == "__main__":
    unittest.main()
