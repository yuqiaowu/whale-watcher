import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from research_agent import build_research_output


class ResearchAgentTests(unittest.TestCase):
    def _base_snapshot(self):
        return {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_2026-04-13_1200",
            "market_snapshot": {
                "adx_14": 28,
                "funding_zscore": -1.8,
                "delta_oi_24h_percent": 0.12,
            },
            "onchain_snapshot": {
                "token_net_flow": -6_000_000,
                "stablecoin_net_flow": 2_500_000,
                "token_flow_semantic": "DISTRIBUTION_PRESSURE",
                "stablecoin_flow_semantic": "BUYING_POWER",
                "flow_composite_semantic": "MIXED",
                "liquidation_short_to_volume_4h": 0.012,
                "liquidation_long_to_volume_4h": 0.003,
            },
            "macro_snapshot": {
                "macro_mode": "RISK_OFF",
                "macro_horizon": "SWING",
                "macro_permission": "ALLOW_SHORT",
            },
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "macro_mode": "RISK_OFF",
                "macro_horizon": "SWING",
                "macro_permission": "ALLOW_SHORT",
                "regime_1d": "BEAR",
                "flow_data_available": True,
                "flow_composite_semantic": "MIXED",
                "flow_support_long": False,
                "flow_support_short": False,
            },
        }

    def test_research_selects_within_approved_candidates(self):
        snapshot = self._base_snapshot()
        candidate_batch = {
            "candidate_proposals": [
                {"decision_intent": "LONG", "trigger_source": "Blueprint_A1"},
                {"decision_intent": "SHORT", "trigger_source": "Blueprint_A2"},
            ]
        }
        rule_evaluation = {
            "passed": True,
            "approved_candidates": [
                {"decision_intent": "LONG", "trigger_source": "Blueprint_A1", "rrr": 2.2},
                {"decision_intent": "SHORT", "trigger_source": "Blueprint_A2", "rrr": 1.9},
            ],
        }

        result = build_research_output(snapshot, candidate_batch, rule_evaluation, previous_research=None)

        self.assertIsNotNone(result)
        self.assertEqual(result["selected_intent"], "SHORT")
        self.assertEqual(result["selected_trigger_sources"], ["Blueprint_A2"])
        self.assertIn(result["scenario_label"], {"trend_following", "mean_reversion", "trend_breakdown", "wait_no_trade"})
        self.assertEqual(result["macro_permission"], "ALLOW_SHORT")
        self.assertNotIn(result["selected_intent"], {"LONG"})
        self.assertEqual(result["onchain_context"]["bias"], "MIXED_FLOW")
        self.assertEqual(result["derivatives_context"]["bias"], "SHORT_CROWDING")
        self.assertIn("funding_z=", result["context_summary"])

    def test_research_continuity_marks_reversal(self):
        snapshot = self._base_snapshot()
        snapshot["decision_ready_features"]["macro_permission"] = "ALLOW_LONG"
        snapshot["decision_ready_features"]["macro_mode"] = "RISK_ON"
        candidate_batch = {"candidate_proposals": [{"decision_intent": "LONG", "trigger_source": "Blueprint_A1"}]}
        rule_evaluation = {
            "passed": True,
            "approved_candidates": [
                {"decision_intent": "LONG", "trigger_source": "Blueprint_A1", "rrr": 2.4},
            ],
        }
        previous = {
            "selected_intent": "SHORT",
            "thesis_strength": "MEDIUM",
        }

        result = build_research_output(snapshot, candidate_batch, rule_evaluation, previous_research=previous)

        self.assertEqual(result["selected_intent"], "LONG")
        self.assertEqual(result["thesis_change"], "REVERSED")
        self.assertIn("changed from SHORT to LONG", result["change_reason"])

    def test_conflicted_candidates_produce_wait_and_scenarios(self):
        snapshot = self._base_snapshot()
        snapshot["decision_ready_features"]["macro_permission"] = "ALLOW_BOTH"
        snapshot["decision_ready_features"]["macro_mode"] = "MIXED"
        candidate_batch = {
            "candidate_proposals": [
                {"decision_intent": "LONG", "trigger_source": "Blueprint_A1"},
                {"decision_intent": "SHORT", "trigger_source": "Blueprint_A2"},
            ]
        }
        rule_evaluation = {
            "passed": True,
            "approved_candidates": [
                {"decision_intent": "LONG", "trigger_source": "Blueprint_A1", "rrr": 2.2},
                {"decision_intent": "SHORT", "trigger_source": "Blueprint_A2", "rrr": 2.1},
            ],
        }

        result = build_research_output(snapshot, candidate_batch, rule_evaluation, previous_research=None)

        self.assertEqual(result["selected_intent"], "WAIT_FOR_CONFIRMATION")
        self.assertEqual(result["scenario_label"], "wait_no_trade")
        self.assertEqual(result["conflict_state"], "candidate_conflict")
        self.assertTrue(isinstance(result.get("scenario_candidates"), list))
        self.assertGreaterEqual(len(result["scenario_candidates"]), 2)
        self.assertTrue(all("score" in item for item in result["scenario_candidates"]))
        self.assertTrue(all("score_breakdown" in item for item in result["scenario_candidates"]))
        self.assertTrue(
            all(
                set(item["score_breakdown"].keys()) == {
                    "rrr_component",
                    "macro_component",
                    "technical_component",
                    "flow_component",
                    "event_component",
                }
                for item in result["scenario_candidates"]
            )
        )


if __name__ == "__main__":
    unittest.main()
