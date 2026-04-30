import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import post_trade_review as ptr


class FakeDB:
    def __init__(self, store):
        self.store = deepcopy(store)

    def get_data(self, key, default=None):
        if default is None:
            default = []
        return deepcopy(self.store.get(key, default))

    def save_data(self, key, data):
        self.store[key] = deepcopy(data)


class PostTradeReviewTests(unittest.TestCase):
    def test_needs_llm_review_for_conflicted_loss(self):
        replay_context = {
            "researchOutput": {"conflict_state": "macro_vs_technical"},
            "ruleEvaluation": {"approved_candidates": [{"a": 1}, {"b": 2}]},
            "execution": {"protection_status": "OPEN"},
        }
        base = {"result_label": "LOSS"}
        self.assertTrue(ptr._needs_llm_review(replay_context, base))

    def test_evaluation_agent_merges_llm_refinement(self):
        replay_context = {
            "strategy_family": "DIRECTIONAL",
            "snapshot": {"symbol": "ETH-USDT"},
            "candidate": {"candidate_proposals": [{"trigger_source": "Blueprint_A1"}, {"trigger_source": "Blueprint_A2"}]},
            "ruleEvaluation": {
                "approved_candidates": [{"trigger_source": "Blueprint_A1"}, {"trigger_source": "Blueprint_A2"}],
                "candidate_structure": {"overall_state": "directional_conflict"},
            },
            "researchOutput": {
                "conflict_state": "macro_vs_technical",
                "selected_trigger_sources": ["Blueprint_A2"],
                "selected_intent": "WAIT_FOR_CONFIRMATION",
                "thesis_strength": "MEDIUM",
            },
            "riskReview": {"review_note": "research requested no trade or wait for confirmation", "execution_action": "DO_NOTHING"},
            "execution": {"protection_status": "MISSING"},
            "matched_trade": {"id": "trade_1", "exitTime": "2026-04-13T10:00:00Z"},
        }
        base = {
            "result_label": "LOSS",
            "primary_cause": "CANDIDATE_OR_MARKET_MISS",
            "improvement_targets": ["candidate"],
            "improvement_note": "base note",
        }
        llm_result = {
            "result_label": "LOSS",
            "primary_cause": "EXECUTION_SLIPPAGE_OR_SYNC",
            "improvement_targets": ["execution", "research", "bad_target"],
            "improvement_note": "execution sync likely distorted the final outcome",
        }
        with patch.object(ptr, "call_llm_json_with_audit", return_value=(llm_result, {"provider": "test"})):
            result = ptr.evaluation_agent(replay_context, base)

        self.assertEqual(result["primary_cause"], "EXECUTION_SLIPPAGE_OR_SYNC")
        self.assertEqual(result["improvement_targets"], ["execution", "research"])
        self.assertEqual(result["matched_trade_id"], "trade_1")
        self.assertEqual(result["feedback_packets"][0]["target_layer"], "execution")
        self.assertEqual(result["traceability"]["candidate_structure"]["overall_state"], "directional_conflict")
        self.assertEqual(result["traceability"]["selected_trigger_sources"], ["Blueprint_A2"])
        self.assertEqual(result["traceability"]["proposed_trigger_sources"], ["Blueprint_A1", "Blueprint_A2"])

    def test_grid_open_monitoring_note_uses_grid_language(self):
        replay_context = {
            "strategy_family": "GRID",
            "ruleEvaluation": {"passed": True, "approved_candidates": [{"trigger_source": "Blueprint_G1"}]},
            "researchOutput": {"selected_intent": "GRID_NEUTRAL", "strategy_family": "GRID"},
            "riskReview": {"approved": True, "strategy_family": "GRID"},
            "execution": {"order_status": "SUBMITTED", "exchange_algo_id": "grid_1"},
        }

        result = ptr.attribution_rules(replay_context)

        self.assertEqual(result["result_label"], "OPEN_MONITORING")
        self.assertIn("grid", result["improvement_note"].lower())

    def test_closed_execution_record_matches_trade_history_for_review(self):
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "d_closed",
                    "symbol": "BTC-USDT",
                    "cycleId": "cycle_1",
                    "created_at": "2026-04-13T08:00:00Z",
                    "positionState": "closed",
                    "ruleEvaluation": {
                        "passed": True,
                        "approved_candidates": [{"trigger_source": "Blueprint_E2", "decision_intent": "SHORT"}],
                    },
                    "researchOutput": {
                        "selected_intent": "SHORT",
                        "selected_trigger_sources": ["Blueprint_E2"],
                        "thesis_strength": "MEDIUM",
                    },
                    "riskReview": {"approved": True, "final_intent": "SHORT", "strategy_family": "DIRECTIONAL"},
                    "execution": {
                        "execution_action": "OPEN_SHORT",
                        "order_status": "CLOSED",
                        "sync_status": "CLOSED",
                        "closed_trade_id": "t1",
                        "history": [],
                    },
                }
            ],
            "trade_history": [
                {
                    "id": "t1",
                    "symbol": "BTC",
                    "type": "short",
                    "pnl": 125.0,
                    "pnlPercent": 4.2,
                    "exitTime": "2026-04-13 12:00:00",
                }
            ],
        }
        fake_db = FakeDB(store)
        with patch.object(ptr, "db", fake_db):
            result = ptr.run_post_trade_review()

        self.assertEqual(result["evaluated_count"], 1)
        record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(record["evaluation"]["result_label"], "WIN")
        self.assertEqual(record["evaluation"]["matched_trade_id"], "t1")
        self.assertEqual(record["evaluation"]["pnl"], 125.0)


if __name__ == "__main__":
    unittest.main()
