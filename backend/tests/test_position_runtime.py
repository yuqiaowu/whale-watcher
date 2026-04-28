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

    def test_max_holding_bars_triggers_close(self):
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
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["positionState"], "exit_pending")
        self.assertEqual(record["execution"]["runtime_reason"], "max_holding_bars_exceeded")
        self.assertEqual(record["execution"]["last_runtime_order_id"], "runtime_order_1")
        self.assertTrue(any(event["type"] == "MAX_HOLDING_BARS_TRIGGERED" for event in record["execution"]["history"]))

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
                        "max_holding_bars": 3,
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


if __name__ == "__main__":
    unittest.main()
