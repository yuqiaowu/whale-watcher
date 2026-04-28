import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from macro_news_pipeline import (
    _impact_horizon,
    _market_impact,
    _policy_stance,
    _llm_summary_override,
    build_macro_news_snapshot,
)


class MacroNewsPipelineTests(unittest.TestCase):
    def test_build_macro_news_snapshot_has_required_fields(self):
        whale_analysis = {
            "fear_greed": {"value": 29, "value_classification": "Fear"},
            "macro": {
                "fed_futures": {"change_5d_bps": 4, "trend": "restrictive"},
                "japan_macro": {"price": 142.1, "change_5d_pct": -1.2},
                "liquidity_monitor": {
                    "dxy": {"price": 105.2, "change_5d_pct": 0.8},
                    "vix": {"price": 24.8, "change_5d_pct": 10.0},
                    "us10y": {"price": 4.45, "change_5d_pct": 0.2},
                },
                "global_stable_flow": -150000000,
            },
            "news": {
                "macro": {
                    "items": [
                        {"title": "Powell says inflation remains sticky and policy must stay restrictive"},
                        {"title": "CPI hotter than expected as core inflation remains elevated"},
                    ]
                },
                "calendar": {"items": [{"title": "FOMC press conference tonight"}]},
            },
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertEqual(result["market_impact"], "RISK_OFF")
        self.assertEqual(result["macro_mode"], "RISK_OFF")
        self.assertEqual(result["macro_permission"], "ALLOW_SHORT")
        self.assertEqual(result["impact_horizon"], "MULTI_DAY")
        self.assertEqual(result["macro_horizon"], "MULTI_DAY")
        self.assertEqual(result["policy_stance"], "HAWKISH")
        self.assertIn("FED_HAWKISH", result["key_tags"])
        self.assertIn("USD_STRENGTH", result["key_tags"])
        self.assertIn("YEN_STRESS", result["key_tags"])
        self.assertIn("classification_basis", result)
        self.assertIn("event_facts", result)
        self.assertIn("news_summary", result)
        self.assertIn("brief_rationale", result)
        self.assertTrue(result["macro_event_window"])

    def test_noise_case_defaults_to_non_directional_outputs(self):
        whale_analysis = {
            "fear_greed": {"value": 52, "value_classification": "Neutral"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "flat"},
                "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                "liquidity_monitor": {
                    "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                    "vix": {"price": 16.0, "change_5d_pct": 0.0},
                    "us10y": {"price": 4.2, "change_5d_pct": 0.0},
                },
                "global_stable_flow": 0,
            },
            "news": {"macro": {"items": []}, "calendar": {"items": []}, "general": {"items": []}},
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertEqual(result["event_type"], "NOISE")
        self.assertIn(result["market_impact"], {"NO_CLEAR_IMPACT", "MIXED"})
        self.assertEqual(result["macro_permission"], "ALLOW_BOTH")
        self.assertIn("MACRO_NOISE", result["key_tags"])
        self.assertEqual(result["crypto_relevance"], "LOW")

    def test_policy_stance_ignores_negated_dovish_keyword(self):
        macro = {
            "fed_futures": {
                "trend": "The Fed is not dovish and policy is still restrictive",
                "change_5d_bps": 0,
            }
        }

        result = _policy_stance(macro)

        self.assertEqual(result, "HAWKISH")

    def test_market_impact_uses_weighted_scoring_not_single_conflict_mixed(self):
        tags = ["FED_DOVISH", "CPI_COOL", "LIQUIDITY_EXPANDING", "USD_STRENGTH"]

        result = _market_impact(tags)

        self.assertEqual(result, "RISK_ON")

    def test_foreign_inflation_forecast_does_not_force_multi_day(self):
        facts = {
            "dxy_change_5d_pct": -0.32,
            "usdjpy_change_5d_pct": 0.12,
            "global_stable_flow": -173_395_342,
            "global_stable_flow_ratio_pct": -0.065,
        }
        headlines = ["Bank of Japan keeps policy rate steady while raising inflation forecast"]

        result = _impact_horizon(facts, ["FED_HAWKISH", "RISK_OFF_NEWS"], headlines)

        self.assertEqual(result, "SWING")

    def test_us_core_macro_event_can_still_force_multi_day(self):
        facts = {
            "dxy_change_5d_pct": 0.1,
            "usdjpy_change_5d_pct": 0.1,
            "global_stable_flow": 0,
            "global_stable_flow_ratio_pct": 0.0,
        }
        headlines = ["Core CPI hotter than expected ahead of FOMC press conference"]

        result = _impact_horizon(facts, ["FED_HAWKISH", "CPI_HOT"], headlines)

        self.assertEqual(result, "MULTI_DAY")

    def test_llm_default_only_overrides_summary_fields(self):
        classification = {
            "news_summary": "old summary",
            "brief_rationale": "old rationale",
            "market_impact": "RISK_OFF",
            "impact_horizon": "SWING",
            "crypto_relevance": "MEDIUM",
            "key_tags": ["FED_HAWKISH", "RISK_OFF_NEWS"],
            "key_events": ["FED_HAWKISH", "RISK_OFF_NEWS"],
        }
        llm_result = {
            "news_summary": "new summary",
            "brief_rationale": "new rationale",
            "market_impact": "MIXED",
            "impact_horizon": "NOISE",
            "crypto_relevance": "LOW",
            "key_tags": ["MACRO_NOISE"],
        }

        with patch("macro_news_pipeline.call_llm_json_with_audit", return_value=(llm_result, {"status": "parsed"})), \
             patch.dict("os.environ", {"ENABLE_MACRO_NEWS_LLM": "1"}, clear=False):
            result = _llm_summary_override(classification, ["headline"])

        self.assertEqual(result["news_summary"], "new summary")
        self.assertEqual(result["brief_rationale"], "new rationale")
        self.assertEqual(result["market_impact"], "RISK_OFF")
        self.assertEqual(result["impact_horizon"], "SWING")
        self.assertEqual(result["crypto_relevance"], "MEDIUM")
        self.assertEqual(result["key_tags"], ["FED_HAWKISH", "RISK_OFF_NEWS"])


if __name__ == "__main__":
    unittest.main()
