import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import post_trade_review as ptr


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
        with patch.object(ptr, "call_llm_json", return_value=llm_result):
            result = ptr.evaluation_agent(replay_context, base)

        self.assertEqual(result["primary_cause"], "EXECUTION_SLIPPAGE_OR_SYNC")
        self.assertEqual(result["improvement_targets"], ["execution", "research"])
        self.assertEqual(result["matched_trade_id"], "trade_1")
        self.assertEqual(result["feedback_packets"][0]["target_layer"], "execution")
        self.assertEqual(result["traceability"]["candidate_structure"]["overall_state"], "directional_conflict")
        self.assertEqual(result["traceability"]["selected_trigger_sources"], ["Blueprint_A2"])
        self.assertEqual(result["traceability"]["proposed_trigger_sources"], ["Blueprint_A1", "Blueprint_A2"])


if __name__ == "__main__":
    unittest.main()
