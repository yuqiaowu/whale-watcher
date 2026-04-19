import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import execution_reconciliation as er


class FakeDB:
    def __init__(self, store):
        self.store = store

    def get_data(self, key, default=None):
        if default is None:
            default = []
        return deepcopy(self.store.get(key, default))

    def save_data(self, key, data):
        self.store[key] = deepcopy(data)


class ExecutionReconciliationTests(unittest.TestCase):
    def test_marks_open_position_as_filled(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d1",
                    "cycleId": "cycle_1",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T12:00:00Z",
                    "riskReview": {"approved": True, "final_intent": "LONG"},
                    "execution": {
                        "execution_action": "OPEN_LONG",
                        "order_status": "SUBMITTED",
                        "sync_status": "SUBMITTED",
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "long",
                        "entryPrice": 2500.0,
                        "amount": 1.2,
                        "stopLoss": 2450.0,
                        "takeProfit": 2600.0,
                    }
                ]
            },
            "trade_history": [],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["order_status"], "FILLED")
        self.assertEqual(record["execution"]["sync_status"], "FILLED")
        self.assertEqual(record["execution"]["avg_fill_price"], 2500.0)
        self.assertEqual(record["execution"]["protection_status"], "OPEN")
        self.assertEqual(record["execution"]["filled_stop_loss"], 2450.0)
        self.assertEqual(record["execution"]["filled_take_profit"], 2600.0)

    def test_marks_closed_trade_as_closed(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d2",
                    "cycleId": "cycle_1",
                    "symbol": "BTC-USDT",
                    "created_at": "2026-04-13T08:00:00Z",
                    "riskReview": {"approved": True, "final_intent": "SHORT"},
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {"positions": []},
            "trade_history": [
                {
                    "id": "t1",
                    "symbol": "BTC",
                    "type": "short",
                    "pnl": 125.0,
                    "pnlPercent": 4.2,
                    "exitPrice": 81000.0,
                    "exitTime": "2026-04-13 12:00:00",
                }
            ],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["order_status"], "CLOSED")
        self.assertEqual(record["execution"]["sync_status"], "CLOSED")
        self.assertEqual(record["execution"]["closed_trade_id"], "t1")
        self.assertEqual(record["execution"]["realized_pnl"], 125.0)
        self.assertEqual(record["positionState"], "closed")


if __name__ == "__main__":
    unittest.main()
