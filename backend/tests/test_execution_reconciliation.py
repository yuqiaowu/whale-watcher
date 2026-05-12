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


class FakeGridExecutor:
    def __init__(self, state="running"):
        self.state = state

    def get_grid_bot_details(self, algo_id, algo_ord_type="contract_grid"):
        return {
            "code": "0",
            "data": [{
                "algoId": algo_id,
                "algoOrdType": algo_ord_type,
                "state": self.state,
                "avgPx": "2450",
                "sz": "500",
            }],
        }


class ExecutionReconciliationTests(unittest.TestCase):
    def test_adopts_unmanaged_live_position_into_v2_ledger(self):
        store = {
            "trade_decision_records": [],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "BNB",
                        "type": "short",
                        "entryPrice": 615.16,
                        "currentPrice": 616.0,
                        "amount": 1.38,
                        "leverage": 2,
                        "stopLoss": 628.4,
                        "takeProfit": 583.8,
                        "timestamp": "2026-04-30T10:00:00Z",
                    }
                ]
            },
            "trade_history": [],
            "latest_decision_cycle_v2": {
                "cycleId": "cycle_2026-04-30_0800",
                "snapshots": [
                    {
                        "symbol": "BNB-USDT",
                        "cycleId": "cycle_2026-04-30_0800",
                        "timeframe": "4h",
                        "market_snapshot": {"price": 616.0},
                        "decision_ready_features": {},
                    }
                ],
            },
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertTrue(record["provenance"]["adopted_live_position"])
        self.assertEqual(record["symbol"], "BNB-USDT")
        self.assertEqual(record["positionState"], "entered")
        self.assertEqual(record["riskReview"]["approved"], True)
        self.assertEqual(record["riskReview"]["final_intent"], "SHORT")
        self.assertEqual(record["execution"]["execution_action"], "OPEN_SHORT")
        self.assertEqual(record["execution"]["order_status"], "FILLED")
        self.assertEqual(record["execution"]["sync_status"], "OPEN")
        self.assertEqual(record["execution"]["executed_at"], "2026-04-30T10:00:00Z")
        self.assertEqual(record["provenance"]["position_open_time_source"], "timestamp")
        self.assertTrue(any(event["type"] == "LIVE_POSITION_ADOPTED" for event in record["execution"]["history"]))

    def test_adopts_live_position_using_raw_exchange_created_time(self):
        store = {
            "trade_decision_records": [],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "short",
                        "entryPrice": 2333.38,
                        "currentPrice": 2311.68,
                        "amount": 0.119,
                        "leverage": 2,
                        "rawPositionCreatedTime": "1778496000000",
                    }
                ]
            },
            "trade_history": [],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db):
            er.run_execution_reconciliation()

        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["executed_at"], "2026-05-11T10:40:00Z")
        self.assertEqual(record["created_at"], "2026-05-11T10:40:00Z")
        self.assertEqual(record["provenance"]["position_open_time_source"], "rawPositionCreatedTime")

    def test_does_not_adopt_live_position_already_managed_by_open_record(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d1",
                    "cycleId": "cycle_1",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T12:00:00Z",
                    "positionState": "entered",
                    "riskReview": {"approved": True, "final_intent": "LONG"},
                    "execution": {
                        "execution_action": "OPEN_LONG",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
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

        self.assertEqual(result["record_count"], 1)
        self.assertEqual(len(fake_db.store["trade_decision_records"]), 1)
        self.assertEqual(fake_db.store["trade_decision_records"][0]["decisionId"], "d1")

    def test_backfills_existing_adopted_record_open_time_from_live_position(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "adopted_eth",
                    "cycleId": "cycle_1",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-05-12T04:23:44Z",
                    "positionState": "entered",
                    "riskReview": {"approved": True, "final_intent": "SHORT"},
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-05-12T04:23:44Z",
                        "live_position_detected_at": "2026-05-12T04:23:44Z",
                        "history": [],
                    },
                    "provenance": {"adopted_live_position": True},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "short",
                        "entryPrice": 2333.38,
                        "amount": 0.119,
                        "rawPositionCreatedTime": "1778496000000",
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
        self.assertEqual(record["created_at"], "2026-05-11T10:40:00Z")
        self.assertEqual(record["execution"]["executed_at"], "2026-05-11T10:40:00Z")
        self.assertEqual(record["provenance"]["position_open_time_source"], "rawPositionCreatedTime")
        self.assertTrue(any(event["type"] == "POSITION_OPEN_TIME_BACKFILLED" for event in record["execution"]["history"]))

    def test_marks_grid_bot_as_running(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "g1",
                    "cycleId": "cycle_1",
                    "symbol": "ETH-USDT",
                    "positionState": "entered",
                    "riskReview": {"approved": True, "final_intent": "GRID_NEUTRAL"},
                    "execution": {
                        "execution_action": "START_GRID_BOT",
                        "exchange_algo_id": "grid_1",
                        "order_status": "SUBMITTED",
                        "sync_status": "SUBMITTED",
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {"positions": []},
            "trade_history": [],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db), patch.object(er, "OKXExecutor", return_value=FakeGridExecutor("running")):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["order_status"], "FILLED")
        self.assertEqual(record["execution"]["sync_status"], "RUNNING")
        self.assertEqual(record["execution"]["grid_state"], "running")
        self.assertEqual(record["execution"]["filled_size"], 500.0)

    def test_marks_grid_bot_as_closed(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "g2",
                    "cycleId": "cycle_1",
                    "symbol": "BTC-USDT",
                    "positionState": "exit_pending",
                    "riskReview": {"approved": True, "final_intent": "GRID_NEUTRAL"},
                    "execution": {
                        "execution_action": "START_GRID_BOT",
                        "exchange_algo_id": "grid_2",
                        "order_status": "FILLED",
                        "sync_status": "STOP_REQUESTED",
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {"positions": []},
            "trade_history": [],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db), patch.object(er, "OKXExecutor", return_value=FakeGridExecutor("stopped")):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["order_status"], "CLOSED")
        self.assertEqual(record["execution"]["sync_status"], "CLOSED")
        self.assertEqual(record["positionState"], "closed")

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

    def test_closed_record_is_not_reopened_and_live_position_is_adopted(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "old_btc",
                    "cycleId": "cycle_1",
                    "symbol": "BTC-USDT",
                    "created_at": "2026-04-27T00:00:00Z",
                    "positionState": "closed",
                    "riskReview": {"approved": True, "final_intent": "SHORT"},
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "CLOSED",
                        "sync_status": "CLOSED",
                        "closed_trade_id": "old_trade",
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "BTC",
                        "type": "short",
                        "entryPrice": 79000,
                        "amount": 0.0036,
                        "stopLoss": 79500,
                        "takeProfit": 77500,
                    }
                ]
            },
            "trade_history": [],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(len(fake_db.store["trade_decision_records"]), 2)
        adopted = fake_db.store["trade_decision_records"][0]
        old_record = fake_db.store["trade_decision_records"][1]
        self.assertTrue(adopted["provenance"]["adopted_live_position"])
        self.assertEqual(adopted["symbol"], "BTC-USDT")
        self.assertEqual(adopted["riskReview"]["final_intent"], "SHORT")
        self.assertEqual(old_record["positionState"], "closed")
        self.assertEqual(old_record["execution"]["order_status"], "CLOSED")
        self.assertEqual(old_record["execution"]["history"], [])

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
        self.assertEqual(record["execution"]["close_reason"], "exchange_or_external_close")
        self.assertEqual(record["execution"]["close_reason_source"], "trade_history_reconciliation")
        self.assertEqual(record["execution"]["history"][-1]["payload"]["reason"], "exchange_or_external_close")
        self.assertEqual(record["positionState"], "closed")

    def test_closed_trade_reconciliation_preserves_runtime_reason(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d3",
                    "cycleId": "cycle_1",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T08:00:00Z",
                    "riskReview": {"approved": True, "final_intent": "SHORT"},
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "runtime_action": "CLOSE_POSITION",
                        "runtime_reason": "max_holding_profit_take",
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {"positions": []},
            "trade_history": [
                {
                    "id": "t2",
                    "symbol": "ETH",
                    "type": "short",
                    "pnl": 10.0,
                    "pnlPercent": 1.0,
                    "exitPrice": 2300.0,
                    "exitTime": "2026-04-13 12:00:00",
                    "reason": "OKX Real Trade",
                }
            ],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db):
            er.run_execution_reconciliation()

        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["close_reason"], "max_holding_profit_take")
        self.assertEqual(record["execution"]["close_reason_source"], "position_runtime")
        self.assertEqual(record["execution"]["history"][-1]["payload"]["okx_reason"], "OKX Real Trade")

    def test_recent_unmatched_closed_trade_gets_audit_record(self):
        with patch.object(er, "_iso_now", return_value="2026-05-12T05:00:00Z"):
            store = {
                "trade_decision_records": [],
                "portfolio_state": {"positions": []},
                "trade_history": [
                    {
                        "id": "recent_t1",
                        "symbol": "DOGE",
                        "type": "short",
                        "entryPrice": 0.11,
                        "exitPrice": 0.1099,
                        "amount": 2500,
                        "leverage": 2,
                        "pnl": 3.25,
                        "pnlPercent": 2.34,
                        "entryTime": "2026-05-11 16:08:17",
                        "exitTime": "2026-05-12 04:11:23",
                        "reason": "OKX Real Trade",
                    }
                ],
            }
            fake_db = FakeDB(store)
            with patch.object(er, "db", fake_db):
                result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["decisionId"], "unmatched_closed_DOGE_short_recent_t1")
        self.assertEqual(record["positionState"], "closed")
        self.assertEqual(record["execution"]["closed_trade_id"], "recent_t1")
        self.assertEqual(record["execution"]["close_reason"], "unmatched_okx_closed_trade")
        self.assertTrue(record["provenance"]["unmatched_closed_trade"])


if __name__ == "__main__":
    unittest.main()
