import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from macro_history import MacroHistory


class FakeCollection:
    def __init__(self, aggregate_rows=None):
        self.aggregate_rows = aggregate_rows or []

    def aggregate(self, pipeline):
        return list(self.aggregate_rows)


class FakeDB:
    def __init__(self, history=None, decision_rows=None):
        self.is_connected = True
        self.history = history or []
        self.saved = []
        self.db = {"decision_cycles_v2": FakeCollection(decision_rows)}

    def get_list_strict(self, collection_name, sort_field=None):
        return list(self.history)

    def save_data(self, collection_name, data):
        self.saved.append((collection_name, list(data)))


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

    def test_history_recovers_from_mongo_after_local_restart(self):
        live_history = [
            {"timestamp": "2026-05-30T00:00:00Z", "fear_greed": 23},
            {"timestamp": "2026-06-04T00:00:00Z", "fear_greed": 12},
        ]
        with TemporaryDirectory() as temp_dir:
            history = MacroHistory(temp_dir, db_client=FakeDB(history=live_history))

            self.assertEqual(history.get_change_absolute("fear_greed", 12, days=5), -11)

    def test_empty_mongo_history_backfills_from_decision_cycles(self):
        decision_rows = [
            {
                "generated_at": "2026-06-04T00:00:00Z",
                "facts": {
                    "fear_greed_index": 12,
                    "fed_implied_rate": 3.622,
                    "global_stable_flow": -548_000_000,
                },
            },
            {
                "generated_at": "2026-05-30T00:00:00Z",
                "facts": {
                    "fear_greed_index": 23,
                    "fed_implied_rate": 3.61,
                    "global_stable_flow": -100_000_000,
                },
            },
        ]
        fake_db = FakeDB(decision_rows=decision_rows)

        with TemporaryDirectory() as temp_dir:
            history = MacroHistory(temp_dir, db_client=fake_db)

            self.assertEqual(history.get_change_absolute("fear_greed", 12, days=5), -11)
            self.assertEqual(fake_db.saved[0][0], "macro_history")

    def test_empty_live_history_ignores_stale_local_file(self):
        decision_rows = [
            {
                "generated_at": "2026-06-04T00:00:00Z",
                "facts": {"fear_greed_index": 12},
            },
            {
                "generated_at": "2026-05-30T00:00:00Z",
                "facts": {"fear_greed_index": 23},
            },
        ]
        with TemporaryDirectory() as temp_dir:
            Path(temp_dir, "macro_history.json").write_text(
                '[{"timestamp": "2026-04-01T00:00:00", "fear_greed": 99}]',
                encoding="utf-8",
            )

            history = MacroHistory(temp_dir, db_client=FakeDB(decision_rows=decision_rows))

            self.assertEqual(history.get_change_absolute("fear_greed", 12, days=5), -11)
            self.assertNotIn(99, [item.get("fear_greed") for item in history.history])


if __name__ == "__main__":
    unittest.main()
