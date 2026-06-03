import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import run_loop


class FakeDB:
    def __init__(self, latest_cycle=None, claim_result=True):
        self.latest_cycle = latest_cycle or {}
        self.claim_result = claim_result
        self.claim_calls = []

    def get_singleton_strict(self, collection_name):
        if collection_name != "latest_decision_cycle_v2":
            raise AssertionError(collection_name)
        return self.latest_cycle

    def claim_once(self, collection_name, claim_id, payload=None):
        self.claim_calls.append((collection_name, claim_id, payload))
        return self.claim_result


class LiveDecisionCycleClaimTests(unittest.TestCase):
    def test_persisted_cycle_is_skipped_without_claiming(self):
        fake_db = FakeDB({"cycleId": "cycle_2026-06-03_2000"})

        with patch.object(run_loop, "db", fake_db):
            result = run_loop._claim_live_decision_cycle("cycle_2026-06-03_2000")

        self.assertFalse(result["claimed"])
        self.assertEqual(result["reason"], "duplicate_cycle_already_persisted")
        self.assertEqual(fake_db.claim_calls, [])

    def test_only_one_instance_can_claim_new_cycle(self):
        fake_db = FakeDB({"cycleId": "cycle_2026-06-03_1600"}, claim_result=False)

        with patch.object(run_loop, "db", fake_db):
            result = run_loop._claim_live_decision_cycle("cycle_2026-06-03_2000")

        self.assertFalse(result["claimed"])
        self.assertEqual(result["reason"], "duplicate_cycle_lock_exists")
        self.assertEqual(fake_db.claim_calls[0][1], "cycle_2026-06-03_2000")

    def test_new_cycle_is_claimed_before_execution(self):
        fake_db = FakeDB({"cycleId": "cycle_2026-06-03_1600"}, claim_result=True)

        with patch.object(run_loop, "db", fake_db):
            result = run_loop._claim_live_decision_cycle("cycle_2026-06-03_2000")

        self.assertTrue(result["claimed"])
        self.assertEqual(result["reason"], "claimed")
        self.assertEqual(fake_db.claim_calls[0][0], "decision_cycle_execution_locks")


if __name__ == "__main__":
    unittest.main()
