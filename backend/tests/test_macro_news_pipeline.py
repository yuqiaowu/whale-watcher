import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from macro_news_pipeline import build_macro_news_snapshot


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
        self.assertEqual(result["impact_horizon"], "INTRADAY")
        self.assertEqual(result["macro_horizon"], "INTRADAY")
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


if __name__ == "__main__":
    unittest.main()
