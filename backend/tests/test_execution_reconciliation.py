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


class FakeOrderHistoryExecutor:
    def __init__(self, orders):
        self.orders = orders

    def get_recent_filled_orders(self, inst_id=None, limit=100):
        if inst_id:
            return [order for order in self.orders if order.get("instId") == inst_id]
        return self.orders


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
        audit_event = fake_db.store["trade_audit_ledger"][0]
        self.assertEqual(audit_event["event_type"], "LIVE_POSITION_ADOPTED")
        self.assertEqual(audit_event["decisionId"], record["decisionId"])
        self.assertEqual(audit_event["riskReview"]["approved_candidate"]["trigger_source"], "ADOPTED_LIVE_POSITION")

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

    def test_matches_unmanaged_live_position_to_open_order_provenance(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "cycle_2026-05-12_1200_DOGE",
                    "cycleId": "cycle_2026-05-12_1200",
                    "symbol": "DOGE-USDT",
                    "created_at": "2026-05-12T12:22:01Z",
                    "positionState": "candidate",
                    "modelDecision": {
                        "action": "SELL",
                        "direction": "SHORT",
                        "reason_codes": ["QLIB_BEARISH"],
                    },
                    "riskReview": {
                        "approved": False,
                        "final_intent": "SHORT",
                        "approved_candidate": {"proposed_entry_price": 0.10934},
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "client_order_id": "ww2605121200DOGESabc123",
                        "order_status": "PENDING_SUBMIT",
                        "sync_status": "PENDING_SUBMIT",
                        "proposed_entry_price": 0.10934,
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "DOGE",
                        "instId": "DOGE-USDT-SWAP",
                        "type": "short",
                        "entryPrice": 0.10921,
                        "amount": 2550,
                        "leverage": 2,
                        "stopLoss": 0.1136,
                        "takeProfit": 0.10083,
                        "positionOpenedAt": "2026-05-12T12:23:10Z",
                    }
                ]
            },
            "trade_history": [],
        }
        orders = [
            {
                "instId": "DOGE-USDT-SWAP",
                "ordId": "okx-order-1",
                "clOrdId": "ww2605121200DOGESabc123",
                "tag": "WWV2",
                "side": "sell",
                "posSide": "short",
                "avgPx": "0.10921",
                "cTime": "1778588590000",
            }
        ]
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db), patch.object(er, "OKXExecutor", return_value=FakeOrderHistoryExecutor(orders)):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["record_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["decisionId"], "cycle_2026-05-12_1200_DOGE")
        self.assertEqual(record["positionState"], "entered")
        self.assertEqual(record["execution"]["exchange_order_id"], "okx-order-1")
        self.assertEqual(record["execution"]["client_order_id"], "ww2605121200DOGESabc123")
        self.assertEqual(record["execution"]["order_status"], "FILLED")
        self.assertEqual(record["execution"]["sync_status"], "OPEN")
        self.assertTrue(record["provenance"]["matched_open_order"])
        self.assertFalse(record["provenance"].get("adopted_live_position", False))
        self.assertTrue(any(event["type"] == "OPEN_ORDER_PROVENANCE_MATCHED" for event in record["execution"]["history"]))

    def test_fuzzy_matches_live_position_to_origin_record_when_order_history_missing(self):
        invalidation_conditions = {
            "operator": "OR",
            "rules": [{"field": "price", "op": ">=", "value_ref": "model_stop_price"}],
            "persistence": 1,
        }
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "cycle_2026-05-22_2000_SOL",
                    "cycleId": "cycle_2026-05-22_2000",
                    "symbol": "SOL-USDT",
                    "created_at": "2026-05-22T20:15:30Z",
                    "positionState": "candidate",
                    "riskReview": {
                        "approved": False,
                        "final_intent": "SHORT",
                        "approved_candidate": {
                            "proposed_entry_price": 84.92,
                            "proposed_sl_price": 87.69,
                            "proposed_tp_price": 79.07,
                            "reference_values": {"model_stop_price": 87.69},
                            "invalidation_basis": "programmatic_stop_and_approved_model_rules",
                            "invalidation_conditions": invalidation_conditions,
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "PENDING_SUBMIT",
                        "sync_status": "PENDING_SUBMIT",
                        "proposed_entry_price": 84.92,
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "SOL",
                        "instId": "SOL-USDT-SWAP",
                        "type": "short",
                        "entryPrice": 84.89,
                        "currentPrice": 84.28,
                        "amount": 1.21,
                        "leverage": 2,
                        "stopLoss": 87.69,
                        "takeProfit": 79.07,
                        "positionOpenedAt": "2026-05-22T20:16:13Z",
                    }
                ]
            },
            "trade_history": [],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db), patch.object(er, "OKXExecutor", return_value=FakeOrderHistoryExecutor([])):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(len(fake_db.store["trade_decision_records"]), 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["decisionId"], "cycle_2026-05-22_2000_SOL")
        self.assertEqual(record["positionState"], "entered")
        self.assertEqual(record["execution"]["order_status"], "FILLED")
        self.assertEqual(record["execution"]["sync_status"], "OPEN")
        self.assertEqual(record["execution"]["avg_fill_price"], 84.89)
        self.assertEqual(record["provenance"]["matched_live_position_source"], "portfolio_state_fuzzy_match")
        self.assertFalse(record["provenance"].get("adopted_live_position", False))
        self.assertEqual(
            invalidation_conditions,
            record["riskReview"]["approved_candidate"]["invalidation_conditions"],
        )
        self.assertEqual(
            invalidation_conditions,
            record["opening_thesis_snapshot"]["invalidation_conditions"],
        )
        self.assertEqual("portfolio_state_fuzzy_match", record["opening_thesis_snapshot"]["source"])
        self.assertTrue(any(event["type"] == "LIVE_POSITION_PROVENANCE_MATCHED" for event in record["execution"]["history"]))

    def test_existing_adopted_record_is_relinked_to_origin_record(self):
        invalidation_conditions = {
            "operator": "OR",
            "rules": [{"field": "price", "op": ">=", "value_ref": "model_stop_price"}],
            "persistence": 1,
        }
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "adopted_SOL_short_84_89_2026_05_22_201613",
                    "cycleId": "cycle_2026-05-22_2000",
                    "symbol": "SOL-USDT",
                    "created_at": "2026-05-22T20:16:13Z",
                    "positionState": "entered",
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "approved_candidate": {
                            "trigger_source": "ADOPTED_LIVE_POSITION",
                            "proposed_entry_price": 84.89,
                            "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "avg_fill_price": 84.89,
                        "executed_at": "2026-05-22T20:16:13Z",
                        "history": [],
                    },
                    "provenance": {"adopted_live_position": True},
                },
                {
                    "decisionId": "cycle_2026-05-22_2000_SOL",
                    "cycleId": "cycle_2026-05-22_2000",
                    "symbol": "SOL-USDT",
                    "created_at": "2026-05-22T20:15:30Z",
                    "positionState": "candidate",
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 3,
                        "approved_candidate": {
                            "proposed_entry_price": 84.92,
                            "proposed_sl_price": 87.69,
                            "proposed_tp_price": 79.07,
                            "reference_values": {"model_stop_price": 87.69},
                            "invalidation_basis": "programmatic_stop_and_approved_model_rules",
                            "invalidation_conditions": invalidation_conditions,
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "PENDING_SUBMIT",
                        "sync_status": "PENDING_SUBMIT",
                        "proposed_entry_price": 84.92,
                        "history": [],
                    },
                },
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "SOL",
                        "instId": "SOL-USDT-SWAP",
                        "type": "short",
                        "entryPrice": 84.89,
                        "currentPrice": 84.28,
                        "amount": 1.21,
                        "leverage": 2,
                        "stopLoss": 87.69,
                        "takeProfit": 79.07,
                        "positionOpenedAt": "2026-05-22T20:16:13Z",
                    }
                ]
            },
            "trade_history": [],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db), patch.object(er, "OKXExecutor", return_value=FakeOrderHistoryExecutor([])):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 1)
        records = fake_db.store["trade_decision_records"]
        adopted = next(record for record in records if record["decisionId"].startswith("adopted_SOL"))
        origin = next(record for record in records if record["decisionId"] == "cycle_2026-05-22_2000_SOL")
        self.assertEqual(adopted["positionState"], "superseded")
        self.assertEqual(adopted["execution"]["order_status"], "SUPERSEDED")
        self.assertEqual(adopted["execution"]["superseded_by_decision_id"], "cycle_2026-05-22_2000_SOL")
        self.assertEqual(origin["positionState"], "entered")
        self.assertEqual(origin["execution"]["order_status"], "FILLED")
        self.assertEqual(origin["provenance"]["matched_live_position_source"], "portfolio_state_fuzzy_match")
        self.assertEqual(invalidation_conditions, origin["riskReview"]["approved_candidate"]["invalidation_conditions"])
        self.assertEqual(invalidation_conditions, origin["opening_thesis_snapshot"]["invalidation_conditions"])
        audit_types = {event["event_type"] for event in fake_db.store["trade_audit_ledger"]}
        self.assertIn("TRADE_PROVENANCE_MATCHED", audit_types)
        self.assertIn("ADOPTED_POSITION_SUPERSEDED", audit_types)

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

    def test_new_same_side_live_position_does_not_reuse_closed_origin_record(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "cycle_2026-05-12_1200_SOL",
                    "cycleId": "cycle_2026-05-12_1200",
                    "symbol": "SOL-USDT",
                    "created_at": "2026-05-12T13:07:32Z",
                    "positionState": "defensive",
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 4,
                        "approved_candidate": {
                            "proposed_entry_price": 95.23,
                            "invalidation_conditions": {
                                "operator": "OR",
                                "rules": [{"field": "price", "op": ">=", "value_ref": "model_stop_price"}],
                            },
                            "reference_values": {"model_stop_price": 98.92714286},
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "avg_fill_price": 95.29,
                        "filled_size": 2.92,
                        "executed_at": "2026-05-12T13:08:42Z",
                        "runtime_action": "REDUCE_25",
                        "history": [],
                    },
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "SOL",
                        "instId": "SOL-USDT-SWAP",
                        "type": "short",
                        "entryPrice": 94.47,
                        "currentPrice": 94.49,
                        "amount": 2.95,
                        "leverage": 2,
                        "stopLoss": 98.05,
                        "takeProfit": 86.31,
                        "positionOpenedAt": "2026-05-12T17:20:16Z",
                    }
                ]
            },
            "trade_history": [
                {
                    "id": "3560230204500877312",
                    "symbol": "SOL",
                    "type": "short",
                    "entryPrice": 95.29,
                    "exitPrice": 94.06,
                    "amount": 2.19,
                    "leverage": 2,
                    "pnl": 2.69,
                    "pnlPercent": 2.58,
                    "entryTime": "2026-05-12 13:08:42",
                    "exitTime": "2026-05-12 17:05:28",
                    "reason": "OKX Real Trade",
                }
            ],
        }
        fake_db = FakeDB(store)
        with patch.object(er, "db", fake_db):
            result = er.run_execution_reconciliation()

        self.assertEqual(result["updated_count"], 2)
        records = fake_db.store["trade_decision_records"]
        adopted = records[0]
        old_record = next(record for record in records if record["decisionId"] == "cycle_2026-05-12_1200_SOL")
        self.assertTrue(adopted["provenance"]["adopted_live_position"])
        self.assertEqual(adopted["symbol"], "SOL-USDT")
        self.assertEqual(adopted["execution"]["avg_fill_price"], 94.47)
        self.assertEqual(adopted["execution"]["executed_at"], "2026-05-12T17:20:16Z")
        self.assertEqual(old_record["positionState"], "closed")
        self.assertEqual(old_record["execution"]["order_status"], "CLOSED")
        self.assertEqual(old_record["execution"]["closed_trade_id"], "3560230204500877312")

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
        audit_event = fake_db.store["trade_audit_ledger"][0]
        self.assertEqual(audit_event["event_type"], "UNMATCHED_CLOSED_TRADE_RECORDED")
        self.assertEqual(audit_event["execution"]["closed_trade_id"], "recent_t1")

    def test_audit_closed_trade_id_prevents_duplicate_unmatched_record(self):
        with patch.object(er, "_iso_now", return_value="2026-05-12T05:00:00Z"):
            store = {
                "trade_decision_records": [],
                "portfolio_state": {"positions": []},
                "trade_audit_ledger": [
                    {
                        "event_type": "TRADE_CLOSED_RECONCILED",
                        "payload": {"trade_id": "recent_t1"},
                        "execution": {"order_status": "CLOSED", "closed_trade_id": "recent_t1"},
                    }
                ],
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

        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(fake_db.store["trade_decision_records"], [])
        self.assertEqual(len(fake_db.store["trade_audit_ledger"]), 1)


if __name__ == "__main__":
    unittest.main()
