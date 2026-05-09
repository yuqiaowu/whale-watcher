import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from macro_news_pipeline import (
    _event_headlines,
    _impact_horizon,
    _macro_bias_tier,
    _market_impact,
    _market_impact_score,
    _policy_stance,
    _llm_summary_override,
    build_macro_news_snapshot,
)


class MacroNewsPipelineTests(unittest.TestCase):
    def test_build_macro_news_snapshot_has_required_fields(self):
        whale_analysis = {
            "fear_greed": {"value": 29, "value_classification": "Fear"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "restrictive"},
                "japan_macro": {"price": 142.1, "change_5d_pct": -1.2},
                "liquidity_monitor": {
                    "dxy": {"price": 105.2, "change_5d_pct": 0.8},
                    "vix": {"price": 24.8, "change_1d_pct": 9.0, "change_5d_pct": 10.0},
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
        self.assertEqual(result["macro_bias_tier"], "STRONG_RISK_OFF")
        self.assertLessEqual(result["macro_impact_score"], -6)
        self.assertEqual(result["impact_horizon"], "MULTI_DAY")
        self.assertEqual(result["macro_horizon"], "MULTI_DAY")
        self.assertEqual(result["policy_stance"], "HAWKISH")
        self.assertIn("FED_HAWKISH", result["key_tags"])
        self.assertIn("USD_STRENGTH", result["key_tags"])
        self.assertIn("YEN_STRESS", result["key_tags"])
        self.assertIn("classification_basis", result)
        self.assertIn("event_facts", result)
        self.assertEqual(result["fear_greed_index"], 29)
        self.assertIsNone(result["fear_greed_change_5d"])
        self.assertEqual(result["vix_level"], 24.8)
        self.assertEqual(result["vix_change_1d_pct"], 9.0)
        self.assertEqual(result["vix_change_5d_pct"], 10.0)
        self.assertEqual(result["event_facts"]["vix_level"], 24.8)
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

    def test_macro_bias_tier_splits_mild_and_strong_edges(self):
        self.assertEqual(_macro_bias_tier(_market_impact_score(["FED_HAWKISH"]), "RISK_OFF"), "MILD_RISK_OFF")
        self.assertEqual(_macro_bias_tier(_market_impact_score(["FED_HAWKISH", "RISK_OFF_NEWS"]), "RISK_OFF"), "STRONG_RISK_OFF")
        self.assertEqual(_macro_bias_tier(_market_impact_score(["RISK_ON_NEWS"]), "RISK_ON"), "MILD_RISK_ON")
        self.assertEqual(_macro_bias_tier(_market_impact_score(["FED_DOVISH", "LIQUIDITY_EXPANDING"]), "RISK_ON"), "STRONG_RISK_ON")

    def test_mild_macro_edge_keeps_both_directions_allowed(self):
        whale_analysis = {
            "fear_greed": {"value": 50, "value_classification": "Neutral"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "restrictive"},
                "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                "liquidity_monitor": {
                    "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                    "vix": {"price": 17.0, "change_5d_pct": 0.0},
                    "us10y": {"price": 4.2, "change_5d_pct": 0.0},
                },
                "global_stable_flow": 0,
            },
            "news": {"macro": {"items": [{"title": "Fed officials say policy remains restrictive"}]}},
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertEqual(result["market_impact"], "RISK_OFF")
        self.assertEqual(result["macro_bias_tier"], "MILD_RISK_OFF")
        self.assertEqual(result["macro_mode"], "MIXED")
        self.assertEqual(result["macro_permission"], "ALLOW_BOTH")
        self.assertEqual(result["risk_off_score"], 0.65)

    def test_rate_and_vol_relief_offset_but_do_not_flip_risk_off(self):
        whale_analysis = {
            "fear_greed": {"value": 46, "value_classification": "Fear"},
            "macro": {
                "fed_futures": {"change_5d_bps": -5.3, "trend": "restrictive"},
                "japan_macro": {"price": 155.9, "change_5d_pct": -2.25},
                "liquidity_monitor": {
                    "dxy": {"price": 97.8, "change_5d_pct": -0.42},
                    "vix": {"price": 16.74, "change_1d_pct": -0.89, "change_5d_pct": 2.5},
                    "us10y": {"price": 4.42, "change_5d_pct": -0.05},
                },
                "global_stable_flow": -544_910_719,
                "global_stable_market_cap": 267_761_692_719,
            },
            "news": {"macro": {"items": []}, "calendar": {"items": []}, "general": {"items": []}},
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertIn("FED_HAWKISH", result["key_tags"])
        self.assertIn("RATE_EXPECTATION_EASING", result["key_tags"])
        self.assertIn("VOL_PRESSURE_EASING", result["key_tags"])
        self.assertIn("LIQUIDITY_CONTRACTING", result["key_tags"])
        self.assertNotIn("YEN_STRESS", result["key_tags"])
        self.assertEqual(result["macro_impact_score"], -3)
        self.assertEqual(result["macro_bias_tier"], "MILD_RISK_OFF")
        self.assertEqual(result["macro_permission"], "ALLOW_BOTH")

    def test_yen_strength_requires_risk_context_before_stress_tag(self):
        whale_analysis = {
            "fear_greed": {"value": 46, "value_classification": "Fear"},
            "macro": {
                "fed_futures": {"change_5d_bps": -3.3, "trend": "restrictive"},
                "japan_macro": {"price": 156.474, "change_5d_pct": -1.93},
                "liquidity_monitor": {
                    "dxy": {"price": 97.97, "change_5d_pct": -0.24},
                    "vix": {"price": 17.22, "change_1d_pct": -0.52, "change_5d_pct": 1.95},
                    "us10y": {"price": 4.35, "change_5d_pct": -0.82},
                },
                "global_stable_flow": 302_452_325,
                "global_stable_market_cap": 268_621_121_668,
            },
            "news": {"macro": {"items": []}, "calendar": {"items": []}, "general": {"items": []}},
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertIn("RATE_EXPECTATION_EASING", result["key_tags"])
        self.assertNotIn("VOL_PRESSURE_RISING", result["key_tags"])
        self.assertIn("LIQUIDITY_EXPANDING", result["key_tags"])
        self.assertNotIn("YEN_STRESS", result["key_tags"])

    def test_geopolitical_relief_adds_positive_margin_tag(self):
        whale_analysis = {
            "fear_greed": {"value": 50, "value_classification": "Neutral"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "flat"},
                "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                "liquidity_monitor": {
                    "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                    "vix": {"price": 17.0, "change_5d_pct": 0.0},
                    "us10y": {"price": 4.2, "change_5d_pct": 0.0},
                },
                "global_stable_flow": 0,
            },
            "news": {"macro": {"items": [{"title": "Ceasefire talks signal de-escalation in the region"}]}},
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertIn("GEOPOLITICAL_RISK_EASING", result["key_tags"])
        self.assertEqual(result["macro_bias_tier"], "NO_CLEAR_EDGE")
        self.assertEqual(result["macro_permission"], "ALLOW_BOTH")

    def test_event_headlines_rank_crypto_and_macro_events_across_buckets(self):
        news_obj = {
            "macro": {
                "items": [
                    {"title": f"Routine lifestyle headline {idx}", "summary": "low relevance"}
                    for idx in range(8)
                ]
            },
            "bitcoin": {
                "items": [
                    {
                        "title": "Bitcoin drops as ETF outflows and liquidations hit crypto markets",
                        "summary": "BTC leverage unwinds across major exchanges",
                        "sentiment": "Bearish",
                    }
                ]
            },
            "general": {
                "items": [
                    {
                        "title": "Stablecoin regulation bill advances after exchange probe",
                        "summary": "Crypto market structure remains in focus",
                        "sentiment": "Bearish",
                    }
                ]
            },
        }

        headlines = _event_headlines(news_obj, limit=3)

        self.assertIn("Bitcoin drops as ETF outflows and liquidations hit crypto markets", headlines)
        self.assertIn("Stablecoin regulation bill advances after exchange probe", headlines)

    def test_labor_resilience_offsets_hawkish_risk_off_pressure(self):
        whale_analysis = {
            "fear_greed": {"value": 38, "value_classification": "Fear"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "restrictive"},
                "japan_macro": {"price": 156.6, "change_5d_pct": -0.23},
                "liquidity_monitor": {
                    "dxy": {"price": 97.84, "change_5d_pct": -0.38},
                    "vix": {"price": 17.19, "change_1d_pct": 0.64, "change_5d_pct": 1.18},
                    "us10y": {"price": 4.36, "change_5d_pct": -0.32},
                },
                "global_stable_flow": -508_870_394,
                "global_stable_market_cap": 268_599_075_693,
            },
            "news": {
                "macro": {
                    "items": [
                        {"title": "The Federal Reserve is quickly running out of reasons to cut interest rates"},
                        {"title": "U.S. payrolls jump more than expected, but the report had several red flags for the economy", "sentiment": "Bullish"},
                    ]
                },
                "bitcoin": {
                    "items": [
                        {"title": "Bitcoin stalls as BTC ETF outflows hit $268M", "sentiment": "Bearish"},
                    ]
                },
            },
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertIn("LABOR_RESILIENT", result["key_tags"])
        self.assertIn("LIQUIDITY_CONTRACTING", result["key_tags"])
        self.assertEqual(-4, result["macro_impact_score"])
        self.assertEqual("MILD_RISK_OFF", result["macro_bias_tier"])
        self.assertEqual("ALLOW_BOTH", result["macro_permission"])

    def test_labor_news_is_selected_ahead_of_lower_value_macro_chatter(self):
        news_obj = {
            "macro": {
                "items": [
                    {"title": f"Routine macro commentary item {idx}", "summary": "market discussion"}
                    for idx in range(10)
                ] + [
                    {"title": "U.S. payrolls jump more than expected as unemployment rate unchanged", "sentiment": "Bullish"}
                ]
            },
            "general": {"items": []},
            "bitcoin": {"items": []},
        }

        headlines = _event_headlines(news_obj, limit=3)

        self.assertIn("U.S. payrolls jump more than expected as unemployment rate unchanged", headlines)

    def test_fear_greed_cooling_from_greed_registers_mild_risk_off(self):
        whale_analysis = {
            "fear_greed": {"value": 58, "value_classification": "Neutral"},
            "macro": {
                "fear_greed_change_5d": -14,
                "fed_futures": {"change_5d_bps": 0, "trend": "flat"},
                "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                "liquidity_monitor": {
                    "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                    "vix": {"price": 17.0, "change_5d_pct": 0.0},
                    "us10y": {"price": 4.2, "change_5d_pct": 0.0},
                },
                "global_stable_flow": 0,
            },
            "news": {"macro": {"items": []}, "calendar": {"items": []}, "general": {"items": []}},
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertIn("SENTIMENT_COOLING", result["key_tags"])
        self.assertEqual(result["macro_bias_tier"], "MILD_RISK_OFF")
        self.assertEqual(result["macro_permission"], "ALLOW_BOTH")
        self.assertEqual(result["fear_greed_change_5d"], -14)

    def test_fear_greed_recovery_offsets_absolute_fear(self):
        whale_analysis = {
            "fear_greed": {"value": 30, "value_classification": "Fear"},
            "macro": {
                "fear_greed_change_5d": 13,
                "fed_futures": {"change_5d_bps": 0, "trend": "flat"},
                "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                "liquidity_monitor": {
                    "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                    "vix": {"price": 17.0, "change_5d_pct": 0.0},
                    "us10y": {"price": 4.2, "change_5d_pct": 0.0},
                },
                "global_stable_flow": 0,
            },
            "news": {"macro": {"items": []}, "calendar": {"items": []}, "general": {"items": []}},
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertIn("RISK_OFF_NEWS", result["key_tags"])
        self.assertIn("SENTIMENT_RELIEF", result["key_tags"])
        self.assertEqual(result["macro_bias_tier"], "NO_CLEAR_EDGE")
        self.assertEqual(result["macro_permission"], "ALLOW_BOTH")

    def test_missing_fear_greed_change_stays_null_and_does_not_add_sentiment_tag(self):
        whale_analysis = {
            "fear_greed": {"value": 58, "value_classification": "Neutral"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "flat"},
                "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                "liquidity_monitor": {
                    "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                    "vix": {"price": 17.0, "change_5d_pct": 0.0},
                    "us10y": {"price": 4.2, "change_5d_pct": 0.0},
                },
                "global_stable_flow": 0,
            },
            "news": {"macro": {"items": []}, "calendar": {"items": []}, "general": {"items": []}},
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertIsNone(result["fear_greed_change_5d"])
        self.assertIsNone(result["event_facts"]["fear_greed_change_5d"])
        self.assertNotIn("SENTIMENT_COOLING", result["key_tags"])
        self.assertNotIn("SENTIMENT_RELIEF", result["key_tags"])

    def test_macro_snapshot_records_news_selection_for_auditability(self):
        whale_analysis = {
            "fear_greed": {"value": 52, "value_classification": "Neutral"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "flat"},
                "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                "liquidity_monitor": {
                    "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                    "vix": {"price": 17.0, "change_5d_pct": 0.0},
                    "us10y": {"price": 4.2, "change_5d_pct": 0.0},
                },
                "global_stable_flow": 0,
            },
            "news": {
                "macro": {
                    "items": [
                        {"title": f"Routine market commentary item {idx}", "summary": "low relevance"}
                        for idx in range(14)
                    ]
                },
                "general": {
                    "items": [
                        {
                            "title": "Major crypto exchange probe triggers liquidation risk",
                            "summary": "Crypto leverage and exchange risk rise",
                            "sentiment": "Bearish",
                        }
                    ]
                },
            },
        }

        result = build_macro_news_snapshot(whale_analysis)

        self.assertIn("news_selection", result)
        self.assertGreater(result["news_selection"]["candidate_count"], len(result["news_selection"]["selected"]))
        self.assertIn("Major crypto exchange probe triggers liquidation risk", result["news_headlines"])

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

    def test_llm_adjudication_becomes_final_macro_conclusion(self):
        whale_analysis = {
            "fear_greed": {"value": 46, "value_classification": "Fear"},
            "macro": {
                "fed_futures": {"change_5d_bps": -3.3, "trend": "restrictive"},
                "japan_macro": {"price": 156.474, "change_5d_pct": -1.93},
                "liquidity_monitor": {
                    "dxy": {"price": 97.97, "change_5d_pct": -0.24},
                    "vix": {"price": 17.22, "change_1d_pct": -0.52, "change_5d_pct": 1.95},
                    "us10y": {"price": 4.35, "change_5d_pct": -0.82},
                },
                "global_stable_flow": 302_452_325,
                "global_stable_market_cap": 268_621_121_668,
            },
            "news": {
                "macro": {"items": [{"title": "Corporate earnings mixed while auto debt stress rises"}]},
                "general": {"items": [{"title": "Political hearing dominates headlines"}]},
            },
        }
        first_pass_llm = {
            "news_summary": "mixed headlines",
            "brief_rationale": "news looks noisy",
            "market_impact": "MIXED",
            "impact_horizon": "NOISE",
            "crypto_relevance": "LOW",
            "key_tags": ["MACRO_NOISE"],
        }
        adjudication = {
            "selected_view": "llm",
            "final_market_impact": "MIXED",
            "final_impact_horizon": "NOISE",
            "final_crypto_relevance": "LOW",
            "final_key_tags": ["MACRO_NOISE"],
            "confidence": "HIGH",
            "reason": "Marginal facts are mixed and the headlines do not create a tradeable macro shock.",
        }

        with patch(
            "macro_news_pipeline.call_llm_json_with_audit",
            side_effect=[
                (first_pass_llm, {"status": "parsed", "parsed_response": first_pass_llm}),
                (adjudication, {"status": "parsed", "parsed_response": adjudication}),
            ],
        ), patch.dict("os.environ", {"ENABLE_MACRO_NEWS_LLM": "1"}, clear=False):
            result = build_macro_news_snapshot(whale_analysis)

        self.assertEqual(result["market_impact"], "MIXED")
        self.assertEqual(result["impact_horizon"], "NOISE")
        self.assertEqual(result["crypto_relevance"], "LOW")
        self.assertEqual(result["key_tags"], ["MACRO_NOISE"])
        self.assertEqual(result["macro_permission"], "ALLOW_BOTH")
        self.assertEqual(result["macro_decision_source"], "llm_adjudicated")
        self.assertEqual(result["final_macro_decision"]["selected_view"], "llm")
        self.assertEqual(result["final_macro_decision"]["llm_view"]["market_impact"], "MIXED")
        self.assertEqual(result["final_macro_decision"]["deterministic_view"]["market_impact"], "MIXED")

    def test_llm_adjudication_invalid_result_falls_back_to_deterministic(self):
        whale_analysis = {
            "fear_greed": {"value": 29, "value_classification": "Fear"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "restrictive"},
                "japan_macro": {"price": 142.1, "change_5d_pct": -1.2},
                "liquidity_monitor": {
                    "dxy": {"price": 105.2, "change_5d_pct": 0.8},
                    "vix": {"price": 24.8, "change_1d_pct": 9.0, "change_5d_pct": 10.0},
                    "us10y": {"price": 4.45, "change_5d_pct": 0.2},
                },
                "global_stable_flow": -150000000,
            },
            "news": {"macro": {"items": [{"title": "Powell says policy must stay restrictive"}]}},
        }
        first_pass_llm = {
            "news_summary": "mixed",
            "brief_rationale": "mixed",
            "market_impact": "MIXED",
            "impact_horizon": "NOISE",
            "crypto_relevance": "LOW",
            "key_tags": ["MACRO_NOISE"],
        }
        bad_adjudication = {
            "selected_view": "llm",
            "final_market_impact": "BULLISH",
            "final_impact_horizon": "NOISE",
            "final_crypto_relevance": "LOW",
            "final_key_tags": ["MACRO_NOISE"],
            "confidence": "HIGH",
            "reason": "invalid",
        }

        with patch(
            "macro_news_pipeline.call_llm_json_with_audit",
            side_effect=[
                (first_pass_llm, {"status": "parsed", "parsed_response": first_pass_llm}),
                (bad_adjudication, {"status": "parsed", "parsed_response": bad_adjudication}),
            ],
        ), patch.dict("os.environ", {"ENABLE_MACRO_NEWS_LLM": "1"}, clear=False):
            result = build_macro_news_snapshot(whale_analysis)

        self.assertEqual(result["market_impact"], "RISK_OFF")
        self.assertEqual(result["macro_decision_source"], "deterministic")
        self.assertEqual(result["final_macro_decision"]["selected_view"], "deterministic")


if __name__ == "__main__":
    unittest.main()
