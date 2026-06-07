import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import position_runtime as pr


class FakeDB:
    def __init__(self, store):
        self.store = deepcopy(store)

    def get_data(self, key, default=None):
        if default is None:
            default = []
        return deepcopy(self.store.get(key, default))

    def save_data(self, key, data):
        self.store[key] = deepcopy(data)


class FakeExecutor:
    def execute_trade(self, **kwargs):
        return "runtime_order_1"

    def stop_grid_bot(self, **kwargs):
        return "runtime_grid_stop_1"


class PositionRuntimeTests(unittest.TestCase):
    def test_grid_range_breakout_triggers_stop(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "g0",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "strategy_family": "GRID",
                        "final_intent": "GRID_NEUTRAL",
                        "max_holding_bars": 12,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_G1",
                            "reference_values": {
                                "range_lower_bound": 2320.0,
                                "range_upper_bound": 2480.0,
                                "grid_count": 8,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "START_GRID_BOT",
                        "exchange_algo_id": "grid_algo_1",
                        "order_status": "SUBMITTED",
                        "sync_status": "RUNNING",
                        "executed_at": "2026-04-13T00:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"strategy_family": "GRID", "selected_intent": "GRID_NEUTRAL"},
                }
            ],
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "market_snapshot": {"price": 2495.0},
                        "decision_ready_features": {
                            "macro_mode": "MIXED",
                            "p_flat_8h": 0.58,
                            "p_up_8h": 0.20,
                            "p_down_8h": 0.22,
                        },
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["actions"][0]["action"], "STOP_GRID_BOT")
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "exit_pending")
        self.assertEqual(record["execution"]["runtime_reason"], "grid_range_breakout")
        self.assertEqual(record["execution"]["last_runtime_order_id"], "runtime_grid_stop_1")
        self.assertTrue(any(event["type"] == "GRID_RUNTIME_EXIT_TRIGGERED" for event in record["execution"]["history"]))

    def test_grid_event_window_triggers_stop(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "g1",
                    "symbol": "BTC-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "BTC-USDT"},
                    "riskReview": {
                        "approved": True,
                        "strategy_family": "GRID",
                        "final_intent": "GRID_NEUTRAL",
                        "max_holding_bars": 12,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_G1",
                            "reference_values": {
                                "range_lower_bound": 68000.0,
                                "range_upper_bound": 70500.0,
                                "grid_count": 10,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "START_GRID_BOT",
                        "exchange_algo_id": "grid_algo_2",
                        "order_status": "SUBMITTED",
                        "sync_status": "RUNNING",
                        "executed_at": "2026-04-13T00:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"strategy_family": "GRID", "selected_intent": "GRID_NEUTRAL"},
                }
            ],
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "BTC-USDT",
                        "market_snapshot": {"price": 69200.0},
                        "decision_ready_features": {
                            "macro_mode": "EVENT_DRIVEN",
                            "p_flat_8h": 0.56,
                            "p_up_8h": 0.18,
                            "p_down_8h": 0.21,
                        },
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["runtime_reason"], "grid_event_window")
        self.assertEqual(record["positionState"], "exit_pending")

    def test_grid_macro_trend_gate_triggers_stop(self):
        record = {
            "riskReview": {
                "max_holding_bars": 12,
                "approved_candidate": {
                    "reference_values": {
                        "range_lower_bound": 2320.0,
                        "range_upper_bound": 2480.0,
                    }
                },
            },
            "execution": {"execution_action": "START_GRID_BOT"},
        }
        snapshot = {
            "market_snapshot": {"price": 2400.0},
            "decision_ready_features": {
                "macro_mode": "RISK_ON",
                "grid_macro_trend_ok": False,
                "grid_macro_block_reasons": ["bullish_liquidity_macro_cluster"],
                "p_flat_8h": 0.58,
                "p_up_8h": 0.20,
                "p_down_8h": 0.22,
            },
        }

        signal = pr._grid_runtime_signal(record, snapshot, held_bars=2)

        self.assertIsNotNone(signal)
        self.assertEqual(signal[1], "grid_macro_trend_blocked")
        self.assertEqual(signal[2]["macro_block_reasons"], ["bullish_liquidity_macro_cluster"])

    def test_grid_review_point_allows_extension_when_flat_regime_persists(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "g2",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "strategy_family": "GRID",
                        "final_intent": "GRID_NEUTRAL",
                        "max_holding_bars": 15,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_G1",
                            "reference_values": {
                                "range_lower_bound": 2320.0,
                                "range_upper_bound": 2480.0,
                                "grid_count": 8,
                                "review_after_hours": 36,
                                "extension_step_hours": 12,
                                "max_lifetime_hours": 60,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "START_GRID_BOT",
                        "exchange_algo_id": "grid_algo_3",
                        "order_status": "SUBMITTED",
                        "sync_status": "RUNNING",
                        "executed_at": "2026-04-13T00:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"strategy_family": "GRID", "selected_intent": "GRID_NEUTRAL"},
                }
            ],
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "market_snapshot": {"price": 2400.0},
                        "decision_ready_features": {
                            "macro_mode": "MIXED",
                            "p_flat_8h": 0.58,
                            "p_up_8h": 0.20,
                            "p_down_8h": 0.22,
                        },
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db), patch.object(pr, "_bars_since", return_value=9):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(fake_db.store["trade_decision_records"][0]["positionState"], "entered")

    def test_grid_review_point_stops_when_flat_regime_no_longer_dominates(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "g3",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "strategy_family": "GRID",
                        "final_intent": "GRID_NEUTRAL",
                        "max_holding_bars": 15,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_G1",
                            "reference_values": {
                                "range_lower_bound": 2320.0,
                                "range_upper_bound": 2480.0,
                                "grid_count": 8,
                                "review_after_hours": 36,
                                "extension_step_hours": 12,
                                "max_lifetime_hours": 60,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "START_GRID_BOT",
                        "exchange_algo_id": "grid_algo_4",
                        "order_status": "SUBMITTED",
                        "sync_status": "RUNNING",
                        "executed_at": "2026-04-13T00:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"strategy_family": "GRID", "selected_intent": "GRID_NEUTRAL"},
                }
            ],
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "market_snapshot": {"price": 2400.0},
                        "decision_ready_features": {
                            "macro_mode": "MIXED",
                            "p_flat_8h": 0.42,
                            "p_up_8h": 0.50,
                            "p_down_8h": 0.08,
                        },
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db), patch.object(pr, "_bars_since", return_value=9):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["runtime_reason"], "grid_extension_rejected")
        self.assertEqual(record["positionState"], "exit_pending")

    def test_missing_protection_triggers_repair(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d0",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "LONG",
                        "max_holding_bars": 3,
                    },
                    "execution": {
                        "execution_action": "OPEN_LONG",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "protection_status": "MISSING",
                        "proposed_sl_price": 2350.0,
                        "proposed_tp_price": 2500.0,
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "MEDIUM"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "long",
                        "entryPrice": 2400.0,
                        "currentPrice": 2420.0,
                        "amount": 1.0,
                        "margin": 100.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_BOTH",
                            "flow_support_long": True,
                            "flow_support_short": False,
                            "regime_1d": "BULL",
                        }
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["actions"][0]["action"], "REPAIR_PROTECTION")
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["runtime_action"], "REPAIR_PROTECTION")
        self.assertEqual(record["execution"]["runtime_reason"], "missing_protection_orders")
        self.assertEqual(record["execution"]["protection_status"], "PENDING_SYNC")
        self.assertEqual(record["execution"]["last_runtime_order_id"], "runtime_order_1")
        self.assertTrue(any(event["type"] == "PROTECTION_REPAIR_TRIGGERED" for event in record["execution"]["history"]))

    def test_low_initial_thesis_does_not_trigger_immediate_runtime_reduce(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d_low_entry",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-05-15T14:07:54Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 1,
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-05-15T14:08:04Z",
                        "add_allowed": True,
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "INITIAL", "thesis_strength": "LOW"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "short",
                        "entryPrice": 2210.79,
                        "currentPrice": 2214.0,
                        "amount": 0.029,
                        "margin": 32.06,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_SHORT",
                            "flow_support_long": False,
                            "flow_support_short": True,
                            "regime_1d": "BEAR",
                        },
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db), patch.object(pr, "_bars_since", return_value=0):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(result["actions"], [])
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "entered")
        self.assertNotEqual(record["execution"].get("runtime_action"), "REDUCE_25")
        self.assertFalse(any(event["type"] == "THESIS_WEAKENED_TRIGGERED" for event in record["execution"]["history"]))

    def test_max_holding_bars_triggers_review_extension_when_unprofitable_thesis_still_valid(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d1",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "LONG",
                        "max_holding_bars": 1,
                    },
                    "execution": {
                        "execution_action": "OPEN_LONG",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-04-13T00:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "MEDIUM"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "long",
                        "entryPrice": 2400.0,
                        "currentPrice": 2380.0,
                        "amount": 1.0,
                        "margin": 100.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_BOTH",
                            "flow_support_long": True,
                            "flow_support_short": False,
                            "regime_1d": "BULL",
                        }
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "entered")
        self.assertEqual(record["execution"]["runtime_action"], "EXTEND_HOLDING")
        self.assertEqual(record["execution"]["runtime_reason"], "max_holding_review_passed")
        self.assertEqual(record["riskReview"]["max_holding_bars"], 1)
        self.assertIsNotNone(record["execution"].get("holding_window_started_at"))
        self.assertTrue(any(event["type"] == "MAX_HOLDING_REVIEW_EXTENDED" for event in record["execution"]["history"]))

    def test_max_holding_bars_closes_profitable_position_before_extension_review(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d_profit",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "LONG",
                        "max_holding_bars": 1,
                    },
                    "execution": {
                        "execution_action": "OPEN_LONG",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-04-13T00:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "MEDIUM"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "long",
                        "entryPrice": 2400.0,
                        "currentPrice": 2420.0,
                        "amount": 1.0,
                        "margin": 100.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_BOTH",
                            "flow_support_long": True,
                            "flow_support_short": False,
                            "regime_1d": "BULL",
                        }
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["actions"][0]["action"], "CLOSE_POSITION")
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "exit_pending")
        self.assertEqual(record["execution"]["runtime_action"], "CLOSE_POSITION")
        self.assertEqual(record["execution"]["runtime_reason"], "max_holding_profit_take")
        self.assertTrue(any(event["type"] == "MAX_HOLDING_PROFIT_TAKE_TRIGGERED" for event in record["execution"]["history"]))
        self.assertFalse(any(event["type"] == "MAX_HOLDING_REVIEW_EXTENDED" for event in record["execution"]["history"]))

    def test_f1_overbought_momentum_reversal_triggers_close(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "f1",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "LONG",
                        "max_holding_bars": 3,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_F1",
                            "reference_values": {"structure_support_stop_long": 2350.0},
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_LONG",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "MEDIUM"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "long",
                        "entryPrice": 2400.0,
                        "currentPrice": 2480.0,
                        "amount": 1.0,
                        "margin": 100.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "market_snapshot": {
                            "rsi_4h": 73.0,
                            "macd_cross_down_4h": True,
                            "bearish_divergence_4h": False,
                            "sma50_4h": 2400.0,
                        },
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_BOTH",
                            "flow_support_long": True,
                            "flow_support_short": False,
                            "regime_1d": "BULL",
                        }
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "exit_pending")
        self.assertEqual(record["execution"]["runtime_reason"], "f_overbought_momentum_reversal")
        self.assertTrue(any(event["type"] == "F_RUNTIME_EXIT_TRIGGERED" for event in record["execution"]["history"]))

    def test_f2_structure_break_requires_sma50_confirmation(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "f2",
                    "symbol": "BTC-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "BTC-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 0,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_F2",
                            "reference_values": {"structure_resistance_stop_short": 70200.0},
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "MEDIUM"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "BTC",
                        "type": "short",
                        "entryPrice": 69000.0,
                        "currentPrice": 70300.0,
                        "amount": 1.0,
                        "margin": 100.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "BTC-USDT",
                        "market_snapshot": {
                            "rsi_4h": 55.0,
                            "macd_cross_up_4h": False,
                            "bullish_divergence_4h": False,
                            "sma50_4h": 70500.0,
                        },
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_BOTH",
                            "flow_support_long": False,
                            "flow_support_short": True,
                            "regime_1d": "BEAR",
                        }
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertNotEqual(record["execution"].get("runtime_reason"), "f_structure_resistance_broken")
        self.assertEqual(record["positionState"], "entered")

    def test_f2_max_holding_bars_triggers_review_extension_when_unprofitable_and_no_f_exit(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "f2_time",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 1,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_F2",
                            "reference_values": {"structure_resistance_stop_short": 2500.0},
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-04-13T00:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "MEDIUM"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "short",
                        "entryPrice": 2400.0,
                        "currentPrice": 2420.0,
                        "amount": 1.0,
                        "margin": 100.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "market_snapshot": {
                            "rsi_4h": 42.0,
                            "macd_cross_up_4h": False,
                            "bullish_divergence_4h": False,
                            "sma50_4h": 2450.0,
                        },
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_BOTH",
                            "flow_support_long": False,
                            "flow_support_short": True,
                            "regime_1d": "BEAR",
                        }
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "entered")
        self.assertEqual(record["execution"]["runtime_action"], "EXTEND_HOLDING")
        self.assertEqual(record["execution"]["runtime_reason"], "max_holding_review_passed")
        self.assertEqual(record["riskReview"]["max_holding_bars"], 1)
        self.assertTrue(any(event["type"] == "MAX_HOLDING_REVIEW_EXTENDED" for event in record["execution"]["history"]))

    def test_f_blueprint_skips_generic_invalidation_and_uses_f_runtime_rules(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "f3",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "LONG",
                        "max_holding_bars": 3,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_F1",
                            "reference_values": {"structure_support_stop_long": 2350.0},
                            "invalidation_conditions": {
                                "operator": "OR",
                                "rules": [
                                    {"field": "price", "op": "<=", "value_ref": "structure_support_stop_long"}
                                ],
                                "persistence": 1,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_LONG",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "MEDIUM"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "long",
                        "entryPrice": 2400.0,
                        "currentPrice": 2348.0,
                        "amount": 1.0,
                        "margin": 100.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "market_snapshot": {
                            "rsi_4h": 58.0,
                            "macd_cross_down_4h": False,
                            "bearish_divergence_4h": False,
                            "sma50_4h": 2405.0,
                            "structure_support_stop_long": 2350.0,
                        },
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_BOTH",
                            "flow_support_long": True,
                            "flow_support_short": False,
                            "regime_1d": "BULL",
                        }
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "exit_pending")
        self.assertEqual(record["execution"]["runtime_reason"], "f_structure_support_broken")
        self.assertFalse(any(event["type"] == "INVALIDATION_TRIGGERED" for event in record["execution"]["history"]))
        self.assertTrue(any(event["type"] == "F_RUNTIME_EXIT_TRIGGERED" for event in record["execution"]["history"]))

    def test_model_short_vwap_reclaim_waits_for_persistence_before_close(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "m_vwap",
                    "symbol": "BTC-USDT",
                    "created_at": "2026-05-15T16:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "BTC-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 999999,
                        "approved_candidate": {
                            "trigger_source": "ModelDecision_LLM",
                            "reference_values": {"model_stop_price": 81215.0},
                            "invalidation_conditions": {
                                "operator": "OR",
                                "rules": [
                                    {"field": "price", "op": ">=", "value_ref": "model_stop_price"},
                                    {"field": "price_vs_vwap_16h_pct", "op": ">=", "value": 0.0, "persistence": 2, "reason": "price reclaims VWAP_16h"},
                                ],
                                "persistence": 1,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-05-15T16:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "HIGH"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "BTC",
                        "type": "short",
                        "entryPrice": 79095.4,
                        "currentPrice": 79850.0,
                        "amount": 0.0016,
                        "margin": 63.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "BTC-USDT",
                        "market_snapshot": {"price_vs_vwap_16h_pct": 0.12},
                        "decision_ready_features": {"macro_permission": "ALLOW_SHORT"},
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["actions"], [])
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "entered")
        self.assertNotEqual(record["execution"].get("runtime_action"), "CLOSE_POSITION")
        state = record["execution"]["invalidation_state"]
        vwap_key = "price_vs_vwap_16h_pct|>=|value:0.0"
        self.assertEqual(state[vwap_key]["consecutive_hits"], 1)
        self.assertEqual(state[vwap_key]["required_hits"], 2)
        self.assertTrue(any(event["type"] == "INVALIDATION_PERSISTENCE_OBSERVED" for event in record["execution"]["history"]))
        self.assertFalse(any(event["type"] == "INVALIDATION_TRIGGERED" for event in record["execution"]["history"]))

    def test_model_short_vwap_reclaim_closes_after_required_persistence_hits(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "m_vwap",
                    "symbol": "BTC-USDT",
                    "created_at": "2026-05-15T16:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "BTC-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 3,
                        "approved_candidate": {
                            "trigger_source": "ModelDecision_LLM",
                            "reference_values": {"model_stop_price": 81215.0},
                            "invalidation_conditions": {
                                "operator": "OR",
                                "rules": [
                                    {"field": "price", "op": ">=", "value_ref": "model_stop_price"},
                                    {"field": "price_vs_vwap_16h_pct", "op": ">=", "value": 0.0, "persistence": 2, "reason": "price reclaims VWAP_16h"},
                                ],
                                "persistence": 1,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-05-15T16:00:00Z",
                        "invalidation_state": {
                            "price_vs_vwap_16h_pct|>=|value:0.0": {
                                "consecutive_hits": 1,
                                "required_hits": 2,
                                "first_matched_at": "2026-05-15T16:10:00Z",
                                "last_checked_at": "2026-05-15T16:10:00Z",
                                "last_matched_at": "2026-05-15T16:10:00Z",
                                "matched": True,
                            }
                        },
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "HIGH"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "BTC",
                        "type": "short",
                        "entryPrice": 79095.4,
                        "currentPrice": 79850.0,
                        "amount": 0.0016,
                        "margin": 63.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "BTC-USDT",
                        "market_snapshot": {"price_vs_vwap_16h_pct": 0.12},
                        "decision_ready_features": {"macro_permission": "ALLOW_SHORT"},
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["actions"][0]["action"], "CLOSE_POSITION")
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "exit_pending")
        self.assertEqual(record["execution"]["runtime_action"], "CLOSE_POSITION")
        self.assertEqual(record["execution"]["runtime_reason"], "candidate_invalidation")
        state = record["execution"]["invalidation_state"]
        self.assertEqual(state["price_vs_vwap_16h_pct|>=|value:0.0"]["consecutive_hits"], 2)
        event = next(event for event in record["execution"]["history"] if event["type"] == "INVALIDATION_TRIGGERED")
        self.assertEqual(event["payload"]["triggering_rules"][0]["rule_key"], "price_vs_vwap_16h_pct|>=|value:0.0")
        self.assertEqual(event["payload"]["triggering_rules"][0]["consecutive_hits"], 2)

    def test_model_short_sma20_reclaim_uses_live_price_and_latest_sma20(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "m_sma20",
                    "symbol": "BTC-USDT",
                    "created_at": "2026-05-15T16:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "BTC-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 3,
                        "approved_candidate": {
                            "trigger_source": "ModelDecision_LLM",
                            "reference_values": {"model_stop_price": 110.0},
                            "invalidation_conditions": {
                                "operator": "OR",
                                "rules": [
                                    {"field": "relative_sma20_pct", "op": ">=", "value": 0.0, "persistence": 2}
                                ],
                                "persistence": 1,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-05-15T16:00:00Z",
                        "holding_window_started_at": "2026-05-15T20:00:00Z",
                        "invalidation_state": {
                            "relative_sma20_pct|>=|value:0.0": {
                                "consecutive_hits": 1,
                                "required_hits": 2,
                                "matched": True,
                            }
                        },
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "HIGH"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "BTC",
                        "type": "short",
                        "entryPrice": 99.0,
                        "currentPrice": 101.0,
                        "amount": 1.0,
                        "margin": 50.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "BTC-USDT",
                        "market_snapshot": {"sma20_4h": 100.0},
                        "decision_ready_features": {"macro_permission": "ALLOW_SHORT"},
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["actions"][0]["action"], "CLOSE_POSITION")
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["runtime_reason"], "candidate_invalidation")
        state = record["execution"]["invalidation_state"]
        self.assertEqual(state["relative_sma20_pct|>=|value:0.0"]["consecutive_hits"], 2)

    def test_persisted_price_vs_relative_sma20_rule_is_normalized_at_runtime(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "m_bad_sma20_rule",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-05-15T16:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 3,
                        "approved_candidate": {
                            "trigger_source": "ModelDecision_LLM",
                            "reference_values": {"model_stop_price": 110.0},
                            "invalidation_conditions": {
                                "operator": "OR",
                                "rules": [
                                    {"field": "price", "op": ">=", "value_ref": "relative_sma20_pct", "persistence": 1}
                                ],
                                "persistence": 1,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-05-15T16:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "HIGH"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "short",
                        "entryPrice": 99.0,
                        "currentPrice": 101.0,
                        "amount": 1.0,
                        "margin": 50.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "market_snapshot": {"sma20_4h": 100.0},
                        "decision_ready_features": {"macro_permission": "ALLOW_SHORT"},
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["actions"][0]["action"], "CLOSE_POSITION")
        record = fake_db.store["trade_decision_records"][0]
        event = next(event for event in record["execution"]["history"] if event["type"] == "INVALIDATION_TRIGGERED")
        self.assertEqual(event["payload"]["triggering_rules"][0]["rule_key"], "relative_sma20_pct|>=|value:0.0")

    def test_expired_losing_short_reclaimed_sma20_rejects_extension(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "adopted_short",
                    "symbol": "BNB-USDT",
                    "created_at": "2026-05-15T16:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "BNB-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 1,
                        "approved_candidate": {
                            "trigger_source": "ADOPTED_LIVE_POSITION",
                            "reference_values": {},
                            "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-05-15T16:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "HIGH"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "BNB",
                        "type": "short",
                        "entryPrice": 99.0,
                        "currentPrice": 101.0,
                        "amount": 1.0,
                        "margin": 50.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "BNB-USDT",
                        "market_snapshot": {"sma20_4h": 100.0},
                        "decision_ready_features": {"macro_permission": "ALLOW_SHORT"},
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["actions"][0]["action"], "CLOSE_POSITION")
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["execution"]["runtime_reason"], "max_holding_review_rejected")
        event = next(event for event in record["execution"]["history"] if event["type"] == "MAX_HOLDING_REVIEW_REJECTED")
        self.assertEqual(event["payload"]["reason"], "expired_losing_short_reclaimed_sma20")

    def test_model_stop_price_invalidation_closes_without_extra_persistence(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "m_stop",
                    "symbol": "BTC-USDT",
                    "created_at": "2026-05-15T16:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "BTC-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "SHORT",
                        "max_holding_bars": 3,
                        "approved_candidate": {
                            "trigger_source": "ModelDecision_LLM",
                            "reference_values": {"model_stop_price": 81215.0},
                            "invalidation_conditions": {
                                "operator": "OR",
                                "rules": [
                                    {"field": "price", "op": ">=", "value_ref": "model_stop_price"},
                                    {"field": "price_vs_vwap_16h_pct", "op": ">=", "value": 0.0, "persistence": 2},
                                ],
                                "persistence": 1,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "executed_at": "2026-05-15T16:00:00Z",
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "HIGH"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "BTC",
                        "type": "short",
                        "entryPrice": 79095.4,
                        "currentPrice": 81220.0,
                        "amount": 0.0016,
                        "margin": 63.0,
                        "leverage": 2.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "BTC-USDT",
                        "market_snapshot": {"price_vs_vwap_16h_pct": -0.12},
                        "decision_ready_features": {"macro_permission": "ALLOW_SHORT"},
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=FakeExecutor())

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["actions"][0]["action"], "CLOSE_POSITION")
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "exit_pending")
        event = next(event for event in record["execution"]["history"] if event["type"] == "INVALIDATION_TRIGGERED")
        self.assertEqual(event["payload"]["triggering_rules"][0]["rule_key"], "price|>=|value_ref:model_stop_price")

    def test_profitable_position_without_invalidation_keeps_original_protection(self):
        class StrictExecutor:
            def execute_trade(self, **kwargs):
                raise AssertionError(f"runtime should not adjust profitable position: {kwargs}")

        store = {
            "trade_decision_records": [
                {
                    "decisionId": "profit_hold",
                    "symbol": "ETH-USDT",
                    "created_at": "2026-04-13T00:00:00Z",
                    "positionState": "entered",
                    "snapshot": {"symbol": "ETH-USDT"},
                    "riskReview": {
                        "approved": True,
                        "final_intent": "LONG",
                        "max_holding_bars": 0,
                        "approved_candidate": {
                            "trigger_source": "Blueprint_A1",
                            "invalidation_conditions": {
                                "operator": "OR",
                                "rules": [{"field": "price", "op": "<=", "value": 2350.0}],
                                "persistence": 1,
                            },
                        },
                    },
                    "execution": {
                        "execution_action": "OPEN_LONG",
                        "order_status": "FILLED",
                        "sync_status": "OPEN",
                        "protection_status": "OPEN",
                        "proposed_sl_price": 2350.0,
                        "proposed_tp_price": 2600.0,
                        "add_allowed": True,
                        "history": [],
                    },
                    "researchOutput": {"thesis_change": "UNCHANGED", "thesis_strength": "MEDIUM"},
                }
            ],
            "portfolio_state": {
                "positions": [
                    {
                        "symbol": "ETH",
                        "type": "long",
                        "entryPrice": 2400.0,
                        "currentPrice": 2520.0,
                        "pnlPercent": 4.2,
                        "amount": 1.0,
                        "margin": 100.0,
                        "leverage": 2.0,
                        "stopLoss": 2350.0,
                        "takeProfit": 2600.0,
                    }
                ]
            },
            "latest_decision_cycle_v2": {
                "snapshots": [
                    {
                        "symbol": "ETH-USDT",
                        "market_snapshot": {"price": 2520.0},
                        "decision_ready_features": {
                            "macro_permission": "ALLOW_BOTH",
                            "flow_support_long": True,
                            "flow_support_short": False,
                            "regime_1d": "BULL",
                        },
                    }
                ]
            },
        }
        fake_db = FakeDB(store)
        with patch.object(pr, "db", fake_db):
            result = pr.run_in_position_runtime(executor=StrictExecutor())

        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(result["actions"], [])
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "entered")
        self.assertNotIn("active_stop_loss", record["execution"])
        self.assertEqual(record["execution"]["proposed_sl_price"], 2350.0)
        self.assertEqual(record["execution"]["proposed_tp_price"], 2600.0)


if __name__ == "__main__":
    unittest.main()
