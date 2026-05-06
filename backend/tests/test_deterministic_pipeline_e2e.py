import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import deterministic_pipeline as dp


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
        return "shadow_order_1"


class DeterministicPipelineE2ETests(unittest.TestCase):
    def test_yen_stress_flag_uses_macro_tag_not_usdjpy_trend_alone(self):
        macro_snapshot = {
            "macro_mode": "MIXED",
            "macro_horizon": "NOISE",
            "macro_permission": "ALLOW_BOTH",
            "macro_bias_tier": "NO_CLEAR_EDGE",
            "macro_impact_score": 0,
            "macro_event_window": False,
            "key_events": [],
            "key_tags": [],
            "usdjpy_trend": "DOWN",
            "dxy_trend": "DOWN",
            "event_facts": {},
        }
        whale_analysis = {
            "btc": {
                "market": {
                    "price": 50000,
                    "funding_rate": 0.0,
                    "funding_zscore": 0.0,
                },
                "stats_24h": {},
            }
        }
        qlib_coin = {
            "rank": 3,
            "qlib_percentile": 0.5,
            "p_up_8h": 0.3,
            "p_down_8h": 0.3,
            "p_flat_8h": 0.4,
            "market_data": {"close": 50000, "atr_14": 500},
        }

        snapshot = dp._build_decision_snapshot(
            "BTC",
            whale_analysis,
            qlib_coin,
            {"positions": []},
            "cycle_test",
            macro_snapshot=macro_snapshot,
        )

        self.assertFalse(snapshot["decision_ready_features"]["yen_stress_flag"])

    def test_chart_feature_context_backfills_adx_delta_when_csv_lacks_adx(self):
        rows = []
        base_time = pd.Timestamp("2026-01-01 00:00:00")
        for idx in range(90):
            close = 2400 + ((idx % 12) - 6) * 8
            rows.append(
                {
                    "datetime": base_time + pd.Timedelta(hours=4 * idx),
                    "instrument": "ETH",
                    "open": close - 4,
                    "high": close + 18,
                    "low": close - 18,
                    "close": close,
                    "volume": 1000000 + idx * 1000,
                    "macd": 0.1,
                    "macd_signal": 0.05,
                    "macd_hist": 0.05,
                    "atr_14": 35,
                    "bb_width_20": 0.06,
                    "bb_pos_20": 0.5,
                    "rsi_14": 50,
                    "volume_usd_4h": 1000000 + idx * 1000,
                }
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "multi_coin_features.csv"
            pd.DataFrame(rows).to_csv(csv_path, index=False)

            with patch.object(dp, "QLOB_FEATURES_PATH", csv_path):
                context = dp._load_chart_feature_context_map()

        eth_context = context["ETH"]
        self.assertTrue(eth_context["grid_preflight_data_ok"])
        self.assertEqual([], eth_context["grid_preflight_missing_fields"])
        self.assertGreater(eth_context["adx_14_4h"], 0)
        self.assertIsInstance(eth_context["adx_delta"], float)

    def test_chart_feature_context_ignores_current_unfinished_4h_bar(self):
        rows = []
        completed_before = pd.Timestamp("2026-04-30 00:00:00")
        base_time = completed_before - pd.Timedelta(hours=4 * 90)
        for idx in range(90):
            close = 2400 + ((idx % 12) - 6) * 8
            rows.append(
                {
                    "datetime": base_time + pd.Timedelta(hours=4 * idx),
                    "instrument": "ETH",
                    "open": close - 4,
                    "high": close + 18,
                    "low": close - 18,
                    "close": close,
                    "volume": 1000000 + idx * 1000,
                    "macd": 0.1,
                    "macd_signal": 0.05,
                    "macd_hist": 0.05,
                    "atr_14": 35,
                    "bb_width_20": 0.06,
                    "bb_pos_20": 0.5,
                    "rsi_14": 50,
                    "volume_usd_4h": 1000000 + idx * 1000,
                }
            )
        rows.append(
            {
                "datetime": completed_before,
                "instrument": "ETH",
                "open": 9999,
                "high": 10999,
                "low": 9990,
                "close": 10000,
                "volume": 1,
                "macd": -99,
                "macd_signal": -99,
                "macd_hist": -99,
                "atr_14": 1,
                "bb_width_20": 0.01,
                "bb_pos_20": 0.01,
                "rsi_14": 1,
                "volume_usd_4h": 1,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "multi_coin_features.csv"
            pd.DataFrame(rows).to_csv(csv_path, index=False)

            with (
                patch.object(dp, "QLOB_FEATURES_PATH", csv_path),
                patch.object(dp, "_current_4h_bar_start_utc", return_value=completed_before),
            ):
                context = dp._load_chart_feature_context_map()

        eth_context = context["ETH"]
        self.assertEqual("2026-04-29 20:00:00", eth_context["chart_context_bar_time"])
        self.assertEqual("2026-04-30 00:00:00", eth_context["chart_context_completed_before"])
        self.assertNotEqual(1, eth_context["volume_usd_4h"])
        self.assertNotEqual(-99, eth_context["macd_line_4h"])
        self.assertEqual(38.89, eth_context["wick_ratio_lower"])
        self.assertEqual(50.0, eth_context["wick_ratio_upper"])

    def test_build_decision_snapshot_maps_flow_into_fixed_semantics(self):
        whale_analysis = {
            "fear_greed": {"value": 50, "value_classification": "Neutral"},
            "macro": {
                "fed_futures": {"change_5d_bps": 0, "trend": "flat", "implied_rate": 3.5},
                "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                "liquidity_monitor": {
                    "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                    "vix": {"price": 18.0, "change_5d_pct": 0.0},
                    "us10y": {"price": 4.1, "change_5d_pct": 0.0},
                },
                "global_stable_flow": 0,
            },
            "news": {"macro": {"items": []}, "calendar": {"items": []}},
            "eth": {
                "market": {"price": 2400, "rsi_4h": 48, "adx_14": 22, "volume_ratio": 1.1},
                "stats_24h": {"token_net_flow": -100000, "stablecoin_net_flow": 50000},
            },
        }

        snapshot = dp._build_decision_snapshot(
            "ETH",
            whale_analysis,
            {"qlib_score": 0.001, "rank": 2, "p_up_8h": 0.52, "p_down_8h": 0.24, "p_flat_8h": 0.24, "market_data": {"atr_14": 35, "close": 2400}},
            {"positions": [], "total_equity": 10000},
            "cycle_test",
        )

        self.assertEqual(snapshot["onchain_snapshot"]["token_flow_semantic"], "DISTRIBUTION_PRESSURE")
        self.assertEqual(snapshot["onchain_snapshot"]["stablecoin_flow_semantic"], "BUYING_POWER")
        self.assertEqual(snapshot["onchain_snapshot"]["flow_composite_semantic"], "MIXED")
        self.assertFalse(snapshot["decision_ready_features"]["flow_support_long"])
        self.assertFalse(snapshot["decision_ready_features"]["flow_support_short"])
        self.assertTrue(snapshot["decision_ready_features"]["flow_signal_mixed"])

    def test_build_decision_snapshot_prefers_confirmed_chart_wick_over_live_market_wick(self):
        whale_analysis = {
            "fear_greed": {"value": 45, "value_classification": "Fear"},
            "macro": {},
            "news": {},
            "btc": {
                "market": {
                    "price": 78000,
                    "rsi_4h": 65,
                    "adx_14": 20,
                    "volume_ratio": 1.0,
                    "wick_ratio_lower": 0,
                    "wick_ratio_upper": 72,
                }
            },
        }
        chart_context = {
            "BTC": {
                "rsi_4h": 65,
                "atr_14": 800,
                "wick_ratio_lower": 42.0,
                "wick_ratio_upper": 12.0,
                "chart_context_bar_time": "2026-05-01 16:00:00",
                "chart_context_completed_before": "2026-05-01 20:00:00",
            }
        }

        snapshot = dp._build_decision_snapshot(
            "BTC",
            whale_analysis,
            {
                "rank": 3,
                "p_up_8h": 0.2,
                "p_down_8h": 0.2,
                "p_flat_8h": 0.6,
                "market_data": {"atr_14": 800, "close": 78000},
            },
            {"positions": [], "total_equity": 10000},
            "cycle_2026-05-01_2000",
            chart_context=chart_context["BTC"],
        )

        self.assertEqual(12.0, snapshot["market_snapshot"]["wick_ratio_upper"])
        self.assertEqual(42.0, snapshot["market_snapshot"]["wick_ratio_lower"])
        proposals = dp._build_candidate_proposals(snapshot)
        self.assertNotIn("Blueprint_A2", [item["trigger_source"] for item in proposals["candidate_proposals"]])

    def test_a2_only_emits_for_bnb_btc_sol_with_bear_regime_and_rsi_above_60(self):
        def build_snapshot(symbol: str, regime: str, rsi: float, wick_upper: float) -> dict:
            return {
                "symbol": symbol,
                "cycleId": "cycle_test",
                "timeframe": "4h",
                "snapshot_timestamp": 1712743200,
                "market_snapshot": {
                    "price": 100.0,
                    "atr_14": 2.0,
                    "rsi_4h": rsi,
                    "wick_ratio_upper": wick_upper,
                },
                "onchain_snapshot": {
                    "token_net_flow": 0.0,
                    "stablecoin_net_flow": 0.0,
                    "qlib_relative_score_8h": 0.0,
                    "qlib_rank_8h": 3,
                    "qlib_percentile_8h": 0.5,
                    "p_up_8h": 0.2,
                    "p_down_8h": 0.2,
                    "p_flat_8h": 0.6,
                },
                "macro_snapshot": {},
                "position_snapshot": {"position_side": "NONE"},
                "decision_ready_features": {
                    "regime_1d": regime,
                    "flow_support_long": False,
                    "flow_support_short": False,
                },
            }

        allowed = dp._build_candidate_proposals(build_snapshot("BTC-USDT", "BEAR", 61, 35))
        self.assertIn("Blueprint_A2", [item["trigger_source"] for item in allowed["candidate_proposals"]])

        blocked_symbol = dp._build_candidate_proposals(build_snapshot("ETH-USDT", "BEAR", 61, 35))
        self.assertNotIn("Blueprint_A2", [item["trigger_source"] for item in blocked_symbol["candidate_proposals"]])

        blocked_regime = dp._build_candidate_proposals(build_snapshot("BTC-USDT", "BULL", 61, 35))
        self.assertNotIn("Blueprint_A2", [item["trigger_source"] for item in blocked_regime["candidate_proposals"]])

        blocked_rsi = dp._build_candidate_proposals(build_snapshot("BTC-USDT", "BEAR", 60, 35))
        self.assertNotIn("Blueprint_A2", [item["trigger_source"] for item in blocked_rsi["candidate_proposals"]])

    def test_a2_uses_real_trigger_candle_high_when_available(self):
        snapshot = {
            "symbol": "BTC-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "market_snapshot": {
                "price": 100.0,
                "atr_14": 2.0,
                "rsi_4h": 61,
                "wick_ratio_upper": 35,
                "trigger_candle_high": 106.0,
            },
            "onchain_snapshot": {
                "token_net_flow": 0.0,
                "stablecoin_net_flow": 0.0,
                "qlib_relative_score_8h": 0.0,
                "qlib_rank_8h": 3,
                "qlib_percentile_8h": 0.5,
                "p_up_8h": 0.2,
                "p_down_8h": 0.2,
                "p_flat_8h": 0.6,
            },
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "regime_1d": "BEAR",
                "flow_support_long": False,
                "flow_support_short": False,
            },
        }

        proposal = dp._build_candidate_proposals(snapshot)["candidate_proposals"][0]

        self.assertEqual("Blueprint_A2", proposal["trigger_source"])
        self.assertEqual(106.0, proposal["reference_values"]["trigger_candle_high"])
        self.assertEqual(106.212, proposal["proposed_sl_price"])

    def test_a2_rejects_entry_when_price_has_already_broken_trigger_candle_high(self):
        snapshot = {
            "symbol": "BTC-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "is_decision_eligible": True,
            "market_snapshot": {
                "price": 107.0,
                "atr_14": 2.0,
                "rsi_4h": 61,
                "wick_ratio_upper": 35,
                "trigger_candle_high": 106.0,
            },
            "onchain_snapshot": {
                "token_net_flow": 0.0,
                "stablecoin_net_flow": 0.0,
                "qlib_relative_score_8h": 0.0,
                "qlib_rank_8h": 3,
                "qlib_percentile_8h": 0.5,
                "p_up_8h": 0.2,
                "p_down_8h": 0.2,
                "p_flat_8h": 0.6,
            },
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "regime_1d": "BEAR",
                "flow_support_long": False,
                "flow_support_short": False,
                "macro_permission": "ALLOW_BOTH",
            },
        }

        candidate_batch = dp._build_candidate_proposals(snapshot)
        result = dp._evaluate_rules(snapshot, candidate_batch)

        self.assertFalse(result["passed"])
        self.assertIn("INVALIDATION_TRIGGERED", result["reason_codes"])
        self.assertEqual([], result["approved_candidates"])

    def test_qlib_coin_map_converts_rank_to_percentile_scale(self):
        qlib_payload = {
            "coins": [
                {"symbol": "BTC", "qlib_score": 0.0030, "rank": 4, "p_up_8h": 0.28, "p_down_8h": 0.47, "p_flat_8h": 0.25},
                {"symbol": "ETH", "qlib_score": 0.0044, "rank": 2, "p_up_8h": 0.62, "p_down_8h": 0.18, "p_flat_8h": 0.20},
                {"symbol": "SOL", "qlib_score": 0.0035, "rank": 3, "p_up_8h": 0.41, "p_down_8h": 0.29, "p_flat_8h": 0.30},
                {"symbol": "BNB", "qlib_score": 0.0019, "rank": 5, "p_up_8h": 0.14, "p_down_8h": 0.70, "p_flat_8h": 0.16},
                {"symbol": "DOGE", "qlib_score": 0.0045, "rank": 1, "p_up_8h": 0.68, "p_down_8h": 0.14, "p_flat_8h": 0.18},
            ]
        }

        result = dp._qlib_coin_map(qlib_payload)

        self.assertEqual(result["DOGE"]["qlib_percentile"], 1.0)
        self.assertEqual(result["ETH"]["qlib_percentile"], 0.75)
        self.assertEqual(result["SOL"]["qlib_percentile"], 0.5)
        self.assertEqual(result["BTC"]["qlib_percentile"], 0.25)
        self.assertEqual(result["BNB"]["qlib_percentile"], 0.0)

    def test_run_cycle_persists_trade_records_and_cycle_bundle(self):
        store = {
            "whale_analysis": {
                "fear_greed": {"value": 15, "value_classification": "Extreme Fear"},
                "macro": {
                    "fed_futures": {"change_5d_bps": 4, "trend": "restrictive", "implied_rate": 3.8},
                    "japan_macro": {"price": 145.0, "change_5d_pct": -0.8},
                    "liquidity_monitor": {
                        "dxy": {"price": 105.0, "change_5d_pct": 0.5},
                        "vix": {"price": 24.0, "change_5d_pct": 8.0},
                        "us10y": {"price": 4.2, "change_5d_pct": 0.2},
                    },
                    "global_stable_flow": -120000000,
                },
                "news": {
                    "macro": {"items": [{"title": "Powell says rates may stay higher for longer"}]},
                    "calendar": {"items": [{"title": "FOMC later today"}]},
                },
                "btc": {"market": {"price": 65000, "rsi_4h": 42, "adx_14": 29, "volume_ratio": 1.2, "wick_ratio_lower": 35, "wick_ratio_upper": 20}},
                "eth": {"market": {"price": 2400, "rsi_4h": 40, "adx_14": 26, "volume_ratio": 1.1, "wick_ratio_lower": 33, "wick_ratio_upper": 18}},
                "sol": {"market": {"price": 80, "rsi_4h": 39, "adx_14": 24, "volume_ratio": 1.0, "wick_ratio_lower": 31, "wick_ratio_upper": 22}},
                "bnb": {"market": {"price": 600, "rsi_4h": 41, "adx_14": 22, "volume_ratio": 1.0, "wick_ratio_lower": 28, "wick_ratio_upper": 25}},
                "doge": {"market": {"price": 0.1, "rsi_4h": 38, "adx_14": 18, "volume_ratio": 1.0, "wick_ratio_lower": 27, "wick_ratio_upper": 35}},
            },
            "portfolio_state": {"positions": [], "total_equity": 10000},
        }
        qlib_payload = {
            "coins": [
                {"symbol": "BTC", "qlib_score": -0.005, "rank": 1, "p_up_8h": 0.64, "p_down_8h": 0.16, "p_flat_8h": 0.20, "market_data": {"atr_14": 900, "close": 65000}},
                {"symbol": "ETH", "qlib_score": -0.004, "rank": 2, "p_up_8h": 0.61, "p_down_8h": 0.18, "p_flat_8h": 0.21, "market_data": {"atr_14": 35, "close": 2400}},
                {"symbol": "SOL", "qlib_score": -0.003, "rank": 3, "p_up_8h": 0.45, "p_down_8h": 0.25, "p_flat_8h": 0.30, "market_data": {"atr_14": 2.0, "close": 80}},
                {"symbol": "BNB", "qlib_score": -0.002, "rank": 4, "p_up_8h": 0.22, "p_down_8h": 0.43, "p_flat_8h": 0.35, "market_data": {"atr_14": 8, "close": 600}},
                {"symbol": "DOGE", "qlib_score": -0.006, "rank": 5, "p_up_8h": 0.16, "p_down_8h": 0.68, "p_flat_8h": 0.16, "market_data": {"atr_14": 0.002, "close": 0.1}},
            ]
        }
        fake_db = FakeDB(store)

        with patch.object(dp, "db", fake_db), \
             patch.object(dp, "_load_qlib_payload", return_value=qlib_payload), \
             patch.object(dp, "run_post_trade_review", return_value={"evaluated_count": 0, "record_count": 0}), \
             patch.dict(os.environ, {"ENABLE_V2_EXECUTION": "1"}, clear=False):
            result = dp.run_deterministic_cycle(executor=FakeExecutor())

        self.assertIn("executions", result)
        self.assertEqual(result["record_count"], 5)
        self.assertEqual(len(result["executions"]), 5)
        saved_records = fake_db.store.get("trade_decision_records", [])
        self.assertEqual(len(saved_records), 5)
        self.assertTrue(all("decisionId" in record for record in saved_records))
        self.assertTrue(any(record["execution"]["order_status"] == "SUBMITTED" for record in saved_records))
        approved_records = [record for record in saved_records if record["riskReview"].get("approved")]
        self.assertTrue(all("requested_protection" in record["execution"] for record in approved_records))
        self.assertTrue(all(record["execution"]["protection_status"] == "PENDING_SYNC" for record in approved_records))
        self.assertTrue(any(record.get("researchOutput", {}).get("scenario_candidates") for record in saved_records if record.get("researchOutput")))
        self.assertIn("latest_decision_cycle_v2", fake_db.store)

    def test_run_cycle_reuses_one_macro_snapshot_for_all_symbols(self):
        whale_analysis = {
            "fear_greed": {"value": 35, "value_classification": "Fear"},
            "macro": {},
            "news": {},
            "btc": {"market": {"price": 65000}},
            "eth": {"market": {"price": 2400}},
            "sol": {"market": {"price": 80}},
            "bnb": {"market": {"price": 600}},
            "doge": {"market": {"price": 0.1}},
        }
        store = {
            "whale_analysis": whale_analysis,
            "portfolio_state": {"positions": [], "total_equity": 10000},
        }
        qlib_payload = {
            "coins": [
                {"symbol": symbol, "rank": idx + 1, "p_up_8h": 0.2, "p_down_8h": 0.2, "p_flat_8h": 0.6, "market_data": {"atr_14": 1, "close": 100}}
                for idx, symbol in enumerate(dp.TRACKED_SYMBOLS)
            ]
        }
        macro_snapshot = {
            "macro_mode": "RISK_OFF",
            "macro_horizon": "MULTI_DAY",
            "macro_permission": "ALLOW_SHORT",
            "macro_event_window": False,
            "key_events": ["FED_HAWKISH", "RISK_OFF_NEWS"],
            "risk_off_score": 0.8,
            "macro_bias_tier": "STRONG_RISK_OFF",
            "macro_impact_score": -8,
            "event_facts": {"fear_greed_change_5d": -12},
            "vix_level": 24.5,
            "vix_change_5d_pct": 9.2,
        }
        fake_db = FakeDB(store)

        with patch.object(dp, "db", fake_db), \
             patch.object(dp, "_load_qlib_payload", return_value=qlib_payload), \
             patch.object(dp, "_build_macro_snapshot", return_value=macro_snapshot) as macro_mock, \
             patch.object(dp, "run_post_trade_review", return_value={"evaluated_count": 0, "record_count": 0}):
            result = dp.run_deterministic_cycle(executor=FakeExecutor())

        self.assertEqual(1, macro_mock.call_count)
        horizons = {snapshot["macro_snapshot"]["macro_horizon"] for snapshot in result["snapshots"]}
        modes = {snapshot["macro_snapshot"]["macro_mode"] for snapshot in result["snapshots"]}
        self.assertEqual({"MULTI_DAY"}, horizons)
        self.assertEqual({"RISK_OFF"}, modes)
        features = result["snapshots"][0]["decision_ready_features"]
        self.assertEqual("STRONG_RISK_OFF", features["macro_bias_tier"])
        self.assertEqual(-8, features["macro_impact_score"])
        self.assertEqual(-12, features["fear_greed_change_5d"])
        self.assertEqual(24.5, features["vix_level"])
        self.assertEqual(9.2, features["vix_change_5d_pct"])

    def test_derivatives_fields_are_mirrored_for_downstream_context(self):
        whale_analysis = {
            "fear_greed": {"value": 50, "value_classification": "Neutral"},
            "macro": {},
            "news": {},
            "sol": {
                "market": {
                    "price": 88,
                    "funding_rate": 0.0001,
                    "funding_zscore": 1.34,
                    "delta_oi_24h_percent": 6.45,
                    "oi_now": 256_500_000,
                }
            },
        }
        snapshot = dp._build_decision_snapshot(
            "SOL",
            whale_analysis,
            {"rank": 1, "p_up_8h": 0.2, "p_down_8h": 0.3, "p_flat_8h": 0.5, "market_data": {"close": 88}},
            {"positions": [], "total_equity": 10000},
            "cycle_test",
        )

        self.assertEqual(1.34, snapshot["market_snapshot"]["funding_zscore"])
        self.assertEqual(6.45, snapshot["market_snapshot"]["delta_oi_24h_percent"])
        self.assertEqual(1.34, snapshot["onchain_snapshot"]["funding_zscore"])
        self.assertEqual(6.45, snapshot["onchain_snapshot"]["delta_oi_24h_percent"])
        self.assertEqual(1.34, snapshot["decision_ready_features"]["funding_zscore"])
        self.assertEqual(6.45, snapshot["decision_ready_features"]["delta_oi_24h_percent"])

    def test_conflicted_research_waits_for_confirmation(self):
        store = {
            "whale_analysis": {
                "fear_greed": {"value": 50, "value_classification": "Neutral"},
                "macro": {
                    "fed_futures": {"change_5d_bps": 0, "trend": "flat", "implied_rate": 3.5},
                    "japan_macro": {"price": 145.0, "change_5d_pct": 0.0},
                    "liquidity_monitor": {
                        "dxy": {"price": 104.0, "change_5d_pct": 0.0},
                        "vix": {"price": 18.0, "change_5d_pct": 0.0},
                        "us10y": {"price": 4.1, "change_5d_pct": 0.0},
                    },
                    "global_stable_flow": 0,
                },
                "news": {
                    "macro": {"items": [{"title": "Macro conditions remain mixed ahead of key data"}]},
                    "calendar": {"items": []},
                },
                "eth": {"market": {"price": 2400, "rsi_4h": 40, "adx_14": 26, "volume_ratio": 1.6, "wick_ratio_lower": 33, "wick_ratio_upper": 18}},
            },
            "portfolio_state": {"positions": [], "total_equity": 10000},
        }
        snapshot = dp._build_decision_snapshot("ETH", store["whale_analysis"], {"qlib_score": 0.001, "rank": 2, "p_up_8h": 0.62, "p_down_8h": 0.18, "p_flat_8h": 0.20, "market_data": {"atr_14": 35, "close": 2400}}, store["portfolio_state"], "cycle_2026-04-13_1200")
        snapshot["decision_ready_features"]["macro_permission"] = "ALLOW_BOTH"
        snapshot["decision_ready_features"]["macro_mode"] = "MIXED"
        snapshot["decision_ready_features"]["flow_support_long"] = True
        snapshot["decision_ready_features"]["flow_support_short"] = False

        candidate_batch = {
            "symbol": "ETH-USDT",
            "cycleId": snapshot["cycleId"],
            "candidate_proposals": [
                {
                    "strategy_family": "DIRECTIONAL",
                    "decision_intent": "LONG",
                    "trigger_source": "Blueprint_F1",
                    "rrr": 2.2,
                    "entry_type": "MARKET",
                    "proposed_entry_price": 2400,
                    "proposed_sl_price": 2350,
                    "proposed_tp_price": 2510,
                    "reference_values": {},
                    "invalidation_basis": "long thesis invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
                {
                    "strategy_family": "DIRECTIONAL",
                    "decision_intent": "SHORT",
                    "trigger_source": "Blueprint_E2",
                    "rrr": 2.1,
                    "entry_type": "MARKET",
                    "proposed_entry_price": 2400,
                    "proposed_sl_price": 2455,
                    "proposed_tp_price": 2285,
                    "reference_values": {},
                    "invalidation_basis": "short thesis invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
            ],
        }
        rule_evaluation = {
            "passed": True,
            "approved_candidates": candidate_batch["candidate_proposals"],
        }

        result = dp.build_research_output(snapshot, candidate_batch, rule_evaluation, previous_research=None)

        self.assertIsNotNone(result)
        self.assertEqual(result["selected_intent"], "WAIT_FOR_CONFIRMATION")
        self.assertEqual(result["scenario_label"], "wait_no_trade")
        self.assertEqual(result["conflict_state"], "candidate_conflict")
        self.assertEqual(result["candidate_structure"]["overall_state"], "directional_conflict")

    def test_rule_engine_keeps_conflicted_candidates_for_research_to_resolve(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "is_decision_eligible": True,
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {"macro_permission": "ALLOW_BOTH"},
        }
        candidate_batch = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "candidate_proposals": [
                {
                    "strategy_family": "DIRECTIONAL",
                    "decision_intent": "LONG",
                    "trigger_source": "Blueprint_F1",
                    "entry_type": "MARKET",
                    "rationale": "long",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 95,
                    "proposed_tp_price": 110,
                    "reference_values": {},
                    "invalidation_basis": "long invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
                {
                    "strategy_family": "DIRECTIONAL",
                    "decision_intent": "SHORT",
                    "trigger_source": "Blueprint_E2",
                    "entry_type": "MARKET",
                    "rationale": "short",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 105,
                    "proposed_tp_price": 90,
                    "reference_values": {},
                    "invalidation_basis": "short invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
            ],
        }
        result = dp._evaluate_rules(snapshot, candidate_batch)
        self.assertTrue(result["passed"])
        self.assertEqual(result["candidate_structure"]["overall_state"], "directional_conflict")
        self.assertIn("CANDIDATE_CONFLICT", result["reason_codes"])
        self.assertEqual(len(result["approved_candidates"]), 2)

    def test_rule_engine_marks_same_direction_resonance(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "is_decision_eligible": True,
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {"macro_permission": "ALLOW_BOTH"},
        }
        candidate_batch = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "candidate_proposals": [
                {
                    "strategy_family": "DIRECTIONAL",
                    "decision_intent": "SHORT",
                    "trigger_source": "Blueprint_A2",
                    "entry_type": "MARKET",
                    "rationale": "short a2",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 104,
                    "proposed_tp_price": 92,
                    "reference_values": {},
                    "invalidation_basis": "invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
                {
                    "strategy_family": "DIRECTIONAL",
                    "decision_intent": "SHORT",
                    "trigger_source": "Blueprint_E2",
                    "entry_type": "MARKET",
                    "rationale": "short e2",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 104,
                    "proposed_tp_price": 92,
                    "reference_values": {},
                    "invalidation_basis": "invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
            ],
        }
        result = dp._evaluate_rules(snapshot, candidate_batch)
        self.assertTrue(result["passed"])
        self.assertEqual(result["candidate_structure"]["overall_state"], "same_direction_resonance")
        self.assertEqual(result["candidate_structure"]["short_count"], 2)
        self.assertTrue(all(c["resonance_bonus"] > 0 for c in result["approved_candidates"]))

    def test_risk_review_translates_resonance_bonus_into_size(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "decision_ready_features": {"macro_mode": "MIXED"},
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {
                "overall_state": "same_direction_resonance",
                "has_directional_conflict": False,
                "long_count": 0,
                "short_count": 2,
                "resonance_groups": {"LONG": [], "SHORT": ["Blueprint_A2", "Blueprint_E2"]},
                "approved_groups": {"LONG": [], "SHORT": ["Blueprint_A2", "Blueprint_E2"]},
                "approved_resonance_strength": 2,
            },
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "Blueprint_A2",
                    "entry_type": "MARKET",
                    "rationale": "short a2",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 104,
                    "proposed_tp_price": 92,
                    "reference_values": {},
                    "invalidation_basis": "invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                    "resonance_bonus": 0.05,
                },
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "Blueprint_E2",
                    "entry_type": "MARKET",
                    "rationale": "short e2",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 104,
                    "proposed_tp_price": 92,
                    "reference_values": {},
                    "invalidation_basis": "invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                    "resonance_bonus": 0.05,
                },
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(risk_review["approved_position_size_usd"], 105.0)
        self.assertIn("same-direction resonance increased size", risk_review["review_note"])
        self.assertEqual(risk_review["candidate_structure"]["overall_state"], "same_direction_resonance")

    def test_risk_review_caps_max_loss_at_two_percent_of_equity_and_uses_three_x_default_leverage(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "decision_ready_features": {"macro_mode": "MIXED"},
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {
                "overall_state": "single_signal",
                "has_directional_conflict": False,
                "long_count": 0,
                "short_count": 1,
                "resonance_groups": {"LONG": [], "SHORT": ["Blueprint_E2"]},
                "approved_groups": {"LONG": [], "SHORT": ["Blueprint_E2"]},
                "approved_resonance_strength": 1,
            },
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "Blueprint_E2",
                    "entry_type": "MARKET",
                    "rationale": "wide stop short",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 150,
                    "proposed_tp_price": 80,
                    "reference_values": {},
                    "invalidation_basis": "invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(risk_review["approved_risk_fraction"], 0.02)
        self.assertEqual(risk_review["leverage"], 3.0)
        self.assertEqual(risk_review["approved_position_size_usd"], 40.0)
        self.assertEqual(abs(100 - 150) / 100 * risk_review["approved_position_size_usd"], 20.0)

    def test_e2_uses_percentile_not_raw_small_score_scale(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "market_snapshot": {"price": 2400, "atr_14": 35},
            "onchain_snapshot": {"qlib_relative_score_8h": 0.0044, "qlib_rank_8h": 2, "qlib_percentile_8h": 0.75, "p_up_8h": 0.58, "p_down_8h": 0.22, "p_flat_8h": 0.20},
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {"regime_1d": "BEAR", "flow_support_long": False, "flow_support_short": False},
        }

        batch = dp._build_candidate_proposals(snapshot)
        triggers = [item["trigger_source"] for item in batch["candidate_proposals"]]

        self.assertNotIn("Blueprint_E2", triggers)
        diagnostic = batch["e_strategy_diagnostic"]
        self.assertIn("short_path", diagnostic)
        self.assertIn("blocked_by", diagnostic["short_path"])
        self.assertIn("rank_bucket", diagnostic["short_path"]["blocked_by"])

    def test_e2_requires_direction_probability_and_bottom_bucket(self):
        snapshot = {
            "symbol": "BNB-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "market_snapshot": {"price": 600, "atr_14": 8, "funding_zscore": 0.2, "rsi_4h": 48},
            "onchain_snapshot": {
                "token_net_flow": -100000,
                "stablecoin_net_flow": -50000,
                "qlib_relative_score_8h": 0.0019,
                "qlib_rank_8h": 5,
                "qlib_percentile_8h": 0.0,
                "p_up_8h": 0.14,
                "p_down_8h": 0.70,
                "p_flat_8h": 0.16,
            },
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {"regime_1d": "BEAR", "flow_support_long": False, "flow_support_short": True},
        }
        batch = dp._build_candidate_proposals(snapshot)
        triggers = [item["trigger_source"] for item in batch["candidate_proposals"]]
        self.assertIn("Blueprint_E2", triggers)
        diagnostic = batch["e_strategy_diagnostic"]
        self.assertTrue(diagnostic["short_path"]["eligible"])
        self.assertEqual(diagnostic["summary"], "Blueprint_E2 eligible")

    def test_g1_emits_grid_candidate_when_flat_regime_dominates(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "market_snapshot": {
                "price": 2400,
                "atr_14": 35,
                "funding_zscore": 0.1,
                "rsi_4h": 49,
                "adx_14": 18,
            },
            "onchain_snapshot": {
                "token_net_flow": 0.0,
                "stablecoin_net_flow": 0.0,
                "qlib_relative_score_8h": 0.001,
                "qlib_rank_8h": 3,
                "qlib_percentile_8h": 0.5,
                "p_up_8h": 0.22,
                "p_down_8h": 0.18,
                "p_flat_8h": 0.60,
            },
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "regime_1d": "CHOP",
                "macro_mode": "MIXED",
                "macro_permission": "ALLOW_BOTH",
                "range_regime": True,
                "grid_candidate_eligible": True,
                "range_lower_bound": 2320.0,
                "range_upper_bound": 2480.0,
                "range_width_pct": 0.066,
                "grid_mode": "ARITHMETIC",
                "grid_count": 8,
                "grid_spacing_pct": 0.0082,
                "min_profitable_spacing_pct": 0.0034,
                "grid_review_after_hours": 36,
                "grid_extension_step_hours": 12,
                "grid_max_lifetime_hours": 60,
                "grid_preflight_data_ok": True,
                "flow_support_long": False,
                "flow_support_short": False,
            },
        }
        batch = dp._build_candidate_proposals(snapshot)
        grid_candidates = [c for c in batch["candidate_proposals"] if c["trigger_source"] == "Blueprint_G1"]
        self.assertEqual(len(grid_candidates), 1)
        self.assertEqual(grid_candidates[0]["decision_intent"], "GRID_NEUTRAL")
        self.assertEqual(grid_candidates[0]["entry_type"], "GRID_BOT")
        self.assertEqual(grid_candidates[0]["reference_values"]["grid_count"], 8)
        self.assertGreater(
            grid_candidates[0]["reference_values"]["grid_spacing_pct"],
            grid_candidates[0]["reference_values"]["min_profitable_spacing_pct"],
        )

    def test_g1_does_not_emit_when_spacing_cannot_cover_fee_and_slippage(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "market_snapshot": {
                "price": 2400,
                "atr_14": 10,
                "funding_zscore": 0.1,
                "rsi_4h": 49,
                "adx_14": 18,
            },
            "onchain_snapshot": {
                "token_net_flow": 0.0,
                "stablecoin_net_flow": 0.0,
                "qlib_relative_score_8h": 0.001,
                "qlib_rank_8h": 3,
                "qlib_percentile_8h": 0.5,
                "p_up_8h": 0.22,
                "p_down_8h": 0.18,
                "p_flat_8h": 0.60,
            },
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "regime_1d": "CHOP",
                "macro_mode": "MIXED",
                "macro_permission": "ALLOW_BOTH",
                "range_regime": False,
                "grid_candidate_eligible": False,
                "range_lower_bound": 2390.0,
                "range_upper_bound": 2410.0,
                "range_width_pct": 0.0083,
                "grid_mode": "ARITHMETIC",
                "grid_count": 6,
                "grid_spacing_pct": 0.0013,
                "min_profitable_spacing_pct": 0.0034,
                "grid_review_after_hours": 36,
                "grid_extension_step_hours": 12,
                "grid_max_lifetime_hours": 60,
                "flow_support_long": False,
                "flow_support_short": False,
            },
        }
        batch = dp._build_candidate_proposals(snapshot)
        self.assertNotIn("Blueprint_G1", [c["trigger_source"] for c in batch["candidate_proposals"]])

    def test_g1_does_not_emit_when_macro_trend_gate_blocks(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "market_snapshot": {"price": 2400, "atr_14": 35, "funding_zscore": 0.1},
            "onchain_snapshot": {"p_up_8h": 0.22, "p_down_8h": 0.18, "p_flat_8h": 0.60},
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "macro_mode": "RISK_ON",
                "range_regime": True,
                "grid_candidate_eligible": True,
                "grid_preflight_data_ok": True,
                "grid_macro_trend_ok": False,
                "grid_macro_block_reasons": ["bullish_liquidity_macro_cluster"],
                "range_lower_bound": 2320.0,
                "range_upper_bound": 2480.0,
                "range_width_pct": 0.066,
                "grid_count": 8,
                "grid_spacing_pct": 0.0082,
                "min_profitable_spacing_pct": 0.0034,
            },
        }
        batch = dp._build_candidate_proposals(snapshot)
        self.assertNotIn("Blueprint_G1", [c["trigger_source"] for c in batch["candidate_proposals"]])

    def test_g1_does_not_emit_during_grid_cooldown(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "market_snapshot": {"price": 2400, "atr_14": 35, "funding_zscore": 0.1},
            "onchain_snapshot": {"p_up_8h": 0.22, "p_down_8h": 0.18, "p_flat_8h": 0.60},
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "macro_mode": "MIXED",
                "range_regime": True,
                "grid_candidate_eligible": True,
                "grid_preflight_data_ok": True,
                "grid_macro_trend_ok": True,
                "range_lower_bound": 2320.0,
                "range_upper_bound": 2480.0,
                "range_width_pct": 0.066,
                "grid_count": 8,
                "grid_spacing_pct": 0.0082,
                "min_profitable_spacing_pct": 0.0034,
            },
        }
        store = {
            "trade_decision_records": [
                {
                    "decisionId": "grid_failed",
                    "symbol": "ETH-USDT",
                    "positionState": "exit_pending",
                    "updated_at": dp._iso_now(),
                    "riskReview": {"strategy_family": "GRID"},
                    "execution": {
                        "execution_action": "START_GRID_BOT",
                        "runtime_reason": "grid_range_breakout",
                    },
                },
                {
                    "decisionId": "grid_failed_again",
                    "symbol": "ETH-USDT",
                    "positionState": "exit_pending",
                    "updated_at": dp._iso_now(),
                    "riskReview": {"strategy_family": "GRID"},
                    "execution": {
                        "execution_action": "START_GRID_BOT",
                        "runtime_reason": "grid_extension_rejected",
                    },
                }
            ]
        }
        fake_db = FakeDB(store)
        with patch.object(dp, "db", fake_db):
            batch = dp._build_candidate_proposals(snapshot)
        self.assertNotIn("Blueprint_G1", [c["trigger_source"] for c in batch["candidate_proposals"]])

    def test_g1_does_not_emit_when_preflight_data_missing(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "market_snapshot": {"price": 2400, "atr_14": 35, "funding_zscore": 0.1},
            "onchain_snapshot": {"p_up_8h": 0.22, "p_down_8h": 0.18, "p_flat_8h": 0.60},
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "macro_mode": "MIXED",
                "range_regime": True,
                "grid_candidate_eligible": True,
                "grid_preflight_data_ok": False,
                "grid_preflight_missing_fields": ["adx_delta"],
                "grid_macro_trend_ok": True,
                "range_lower_bound": 2320.0,
                "range_upper_bound": 2480.0,
                "range_width_pct": 0.066,
                "grid_count": 8,
                "grid_spacing_pct": 0.0082,
                "min_profitable_spacing_pct": 0.0034,
            },
        }
        batch = dp._build_candidate_proposals(snapshot)
        self.assertNotIn("Blueprint_G1", [c["trigger_source"] for c in batch["candidate_proposals"]])

    def test_grid_setup_blocks_daily_ma_cross(self):
        setup = dp._derive_grid_setup(
            symbol="ETH-USDT",
            price=2400,
            atr=35,
            adx_14=18,
            p_up_8h=0.22,
            p_down_8h=0.18,
            p_flat_8h=0.60,
            macro_mode="MIXED",
            support_level=2320,
            resistance_level=2480,
            bb_width=0.06,
            bb_mid_slope_pct=0.002,
            ma5_cross_up_ma10_1d=True,
            preflight_data_ok=True,
        )
        self.assertFalse(setup["grid_candidate_eligible"])
        self.assertFalse(setup["macro_trend_ok"])
        self.assertIn("ma5_cross_up_ma10_1d", setup["macro_block_reasons"])

    def test_grid_candidate_maps_to_start_grid_bot_risk_review(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "decision_ready_features": {"macro_mode": "MIXED"},
        }
        rule_evaluation = {
            "passed": True,
            "approved_candidates": [
                {
                    "decision_intent": "GRID_NEUTRAL",
                    "trigger_source": "Blueprint_G1",
                    "entry_type": "GRID_BOT",
                    "proposed_entry_price": 2400,
                    "proposed_sl_price": 2300,
                    "proposed_tp_price": 2500,
                    "reference_values": {
                        "range_lower_bound": 2320.0,
                        "range_upper_bound": 2480.0,
                        "grid_count": 8,
                        "grid_mode": "ARITHMETIC",
                        "grid_spacing_pct": 0.0082,
                        "min_profitable_spacing_pct": 0.0034,
                        "review_after_hours": 36,
                        "extension_step_hours": 12,
                        "max_lifetime_hours": 60,
                    },
                    "invalidation_basis": "range broken",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                    "rrr": 1.8,
                }
            ],
            "candidate_structure": {"overall_state": "single_signal"},
        }
        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 10000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)
            execution = dp._build_execution_request(snapshot, risk_review)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(risk_review["strategy_family"], "GRID")
        self.assertEqual(risk_review["final_intent"], "GRID_NEUTRAL")
        self.assertEqual(risk_review["execution_action"], "START_GRID_BOT")
        self.assertEqual(risk_review["leverage"], 3.0)
        self.assertEqual(execution["strategy_family"], "GRID")
        self.assertEqual(execution["execution_action"], "START_GRID_BOT")
        self.assertEqual(execution["grid_config"]["grid_mode"], "ARITHMETIC")
        self.assertEqual(risk_review["approved_candidate"]["reference_values"]["per_grid_notional_usd"], 62.5)

    def test_grid_candidate_rejected_when_per_grid_notional_too_small(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "decision_ready_features": {"macro_mode": "MIXED"},
        }
        rule_evaluation = {
            "passed": True,
            "approved_candidates": [
                {
                    "strategy_family": "GRID",
                    "decision_intent": "GRID_NEUTRAL",
                    "trigger_source": "Blueprint_G1",
                    "entry_type": "GRID_BOT",
                    "proposed_entry_price": 2400,
                    "proposed_sl_price": 2300,
                    "proposed_tp_price": 2500,
                    "reference_values": {
                        "range_lower_bound": 2320.0,
                        "range_upper_bound": 2480.0,
                        "grid_count": 8,
                        "grid_mode": "ARITHMETIC",
                        "review_after_hours": 36,
                        "extension_step_hours": 12,
                        "max_lifetime_hours": 60,
                    },
                    "invalidation_basis": "range broken",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                    "rrr": 1.8,
                }
            ],
            "candidate_structure": {"overall_state": "single_signal"},
        }
        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 200.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertFalse(risk_review["approved"])
        self.assertIn("per-cell", risk_review["review_note"])

    def test_cycle_bundle_includes_e_strategy_diagnostic(self):
        store = {
            "whale_analysis": {
                "fear_greed": {"value": 20, "value_classification": "Fear"},
                "macro": {
                    "fed_futures": {"change_5d_bps": 3, "trend": "restrictive", "implied_rate": 3.8},
                    "japan_macro": {"price": 145.0, "change_5d_pct": -0.4},
                    "liquidity_monitor": {
                        "dxy": {"price": 105.0, "change_5d_pct": 0.3},
                        "vix": {"price": 22.0, "change_5d_pct": 5.0},
                        "us10y": {"price": 4.2, "change_5d_pct": 0.1},
                    },
                    "global_stable_flow": -50_000_000,
                },
                "news": {"macro": {"items": []}, "calendar": {"items": []}},
            },
            "portfolio_state": {"positions": [], "total_equity": 10000},
        }
        qlib_payload = {
            "coins": [
                {"symbol": "BTC", "qlib_score": -0.005, "rank": 1, "p_up_8h": 0.20, "p_down_8h": 0.18, "p_flat_8h": 0.62, "market_data": {"atr_14": 900, "close": 65000}},
                {"symbol": "ETH", "qlib_score": -0.004, "rank": 2, "p_up_8h": 0.24, "p_down_8h": 0.20, "p_flat_8h": 0.56, "market_data": {"atr_14": 35, "close": 2400}},
                {"symbol": "SOL", "qlib_score": -0.003, "rank": 3, "p_up_8h": 0.25, "p_down_8h": 0.19, "p_flat_8h": 0.56, "market_data": {"atr_14": 2.0, "close": 80}},
                {"symbol": "BNB", "qlib_score": -0.002, "rank": 4, "p_up_8h": 0.19, "p_down_8h": 0.33, "p_flat_8h": 0.48, "market_data": {"atr_14": 8, "close": 600}},
                {"symbol": "DOGE", "qlib_score": -0.006, "rank": 5, "p_up_8h": 0.18, "p_down_8h": 0.34, "p_flat_8h": 0.48, "market_data": {"atr_14": 0.002, "close": 0.1}},
            ]
        }
        fake_db = FakeDB(store)

        with patch.object(dp, "db", fake_db), \
             patch.object(dp, "_load_qlib_payload", return_value=qlib_payload), \
             patch.object(dp, "run_post_trade_review", return_value={"evaluated_count": 0, "record_count": 0}), \
             patch.dict(os.environ, {"ENABLE_V2_EXECUTION": "0"}, clear=False):
            result = dp.run_deterministic_cycle(executor=FakeExecutor())

        first_batch = result["candidate_batches"][0]
        self.assertIn("e_strategy_diagnostic", first_batch)
        self.assertIn("summary", first_batch["e_strategy_diagnostic"])
        self.assertIn("long_path", first_batch["e_strategy_diagnostic"])
        self.assertIn("short_path", first_batch["e_strategy_diagnostic"])

    def test_f_strategy_universe_is_formally_constrained(self):
        base_snapshot = {
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "macro_snapshot": {},
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {"regime_1d": "BULL", "flow_support_long": True, "flow_support_short": True},
        }

        def build(
            symbol,
            rsi,
            macd_line,
            macd_signal,
            support,
            resistance,
            *,
            rsi_delta=1.0,
            macd_cross_up=False,
            macd_cross_down=False,
        ):
            return {
                **base_snapshot,
                "symbol": symbol,
                "market_snapshot": {
                    "price": 100.0,
                    "atr_14": 2.0,
                    "rsi_4h": rsi,
                    "rsi_delta_4h": rsi_delta,
                    "macd_line_4h": macd_line,
                    "macd_signal_4h": macd_signal,
                    "macd_cross_up_4h": macd_cross_up,
                    "macd_cross_down_4h": macd_cross_down,
                    "rel_volume_60": 1.6,
                    "structure_support_stop_long": support,
                    "structure_resistance_stop_short": resistance,
                },
                "onchain_snapshot": {},
            }

        bnb_batch = dp._build_candidate_proposals(
            build("BNB-USDT", 55, 1.2, 0.8, 95.0, 105.0, rsi_delta=1.0, macd_cross_up=True)
        )
        self.assertIn("Blueprint_F1", [c["trigger_source"] for c in bnb_batch["candidate_proposals"]])

        stale_macd_long_batch = dp._build_candidate_proposals(
            build("BNB-USDT", 55, 1.2, 0.8, 95.0, 105.0, rsi_delta=1.0, macd_cross_up=False)
        )
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in stale_macd_long_batch["candidate_proposals"]])

        falling_rsi_long_batch = dp._build_candidate_proposals(
            build("BNB-USDT", 55, 1.2, 0.8, 95.0, 105.0, rsi_delta=-1.0, macd_cross_up=True)
        )
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in falling_rsi_long_batch["candidate_proposals"]])

        overheated_long_batch = dp._build_candidate_proposals(
            build("BNB-USDT", 72, 1.2, 0.8, 95.0, 105.0, rsi_delta=1.0, macd_cross_up=True)
        )
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in overheated_long_batch["candidate_proposals"]])

        extended_long_batch = dp._build_candidate_proposals(
            build("BNB-USDT", 65, 1.2, 0.8, 95.0, 105.0, rsi_delta=1.0, macd_cross_up=True)
        )
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in extended_long_batch["candidate_proposals"]])

        eth_short_batch = dp._build_candidate_proposals(
            build("ETH-USDT", 45, -1.2, -0.8, 95.0, 105.0, rsi_delta=-1.0, macd_cross_down=True)
        )
        self.assertIn("Blueprint_F2", [c["trigger_source"] for c in eth_short_batch["candidate_proposals"]])

        stale_macd_short_batch = dp._build_candidate_proposals(
            build("ETH-USDT", 45, -1.2, -0.8, 95.0, 105.0, rsi_delta=-1.0, macd_cross_down=False)
        )
        self.assertNotIn("Blueprint_F2", [c["trigger_source"] for c in stale_macd_short_batch["candidate_proposals"]])

        rising_rsi_short_batch = dp._build_candidate_proposals(
            build("ETH-USDT", 45, -1.2, -0.8, 95.0, 105.0, rsi_delta=1.0, macd_cross_down=True)
        )
        self.assertNotIn("Blueprint_F2", [c["trigger_source"] for c in rising_rsi_short_batch["candidate_proposals"]])

        oversold_short_batch = dp._build_candidate_proposals(
            build("ETH-USDT", 28, -1.2, -0.8, 95.0, 105.0, rsi_delta=-1.0, macd_cross_down=True)
        )
        self.assertNotIn("Blueprint_F2", [c["trigger_source"] for c in oversold_short_batch["candidate_proposals"]])

        extended_short_batch = dp._build_candidate_proposals(
            build("ETH-USDT", 35, -1.2, -0.8, 95.0, 105.0, rsi_delta=-1.0, macd_cross_down=True)
        )
        self.assertNotIn("Blueprint_F2", [c["trigger_source"] for c in extended_short_batch["candidate_proposals"]])

        doge_long_batch = dp._build_candidate_proposals(
            build("DOGE-USDT", 55, 1.2, 0.8, 95.0, 105.0, rsi_delta=1.0, macd_cross_up=True)
        )
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in doge_long_batch["candidate_proposals"]])

        doge_short_batch = dp._build_candidate_proposals(
            build("DOGE-USDT", 45, -1.2, -0.8, 95.0, 105.0, rsi_delta=-1.0, macd_cross_down=True)
        )
        self.assertIn("Blueprint_F2", [c["trigger_source"] for c in doge_short_batch["candidate_proposals"]])

        btc_batch = dp._build_candidate_proposals(
            build("BTC-USDT", 55, 1.2, 0.8, 95.0, 105.0, rsi_delta=1.0, macd_cross_up=True)
        )
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in btc_batch["candidate_proposals"]])
        self.assertNotIn("Blueprint_F2", [c["trigger_source"] for c in btc_batch["candidate_proposals"]])

        sol_batch = dp._build_candidate_proposals(
            build("SOL-USDT", 45, -1.2, -0.8, 95.0, 105.0, rsi_delta=-1.0, macd_cross_down=True)
        )
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in sol_batch["candidate_proposals"]])
        self.assertNotIn("Blueprint_F2", [c["trigger_source"] for c in sol_batch["candidate_proposals"]])

    def test_demo_mode_executes_when_v2_flag_is_unset(self):
        execution = {
            "symbol": "ETH-USDT",
            "execution_action": "OPEN_LONG",
            "requested_size_usd": 1000.0,
            "requested_leverage": 3.0,
            "requested_protection": {"stop_loss": 2400.0, "take_profit": 2600.0},
            "history": [],
        }
        risk_review = {
            "approved_candidate": {
                "trigger_source": "Blueprint_E1",
                "proposed_sl_price": 2400.0,
                "proposed_tp_price": 2600.0,
            }
        }

        class MiniExecutor:
            def execute_trade(self, **kwargs):
                return "demo-order-1"

        with patch.dict(os.environ, {"TRADING_MODE": "DEMO"}, clear=False):
            os.environ.pop("ENABLE_V2_EXECUTION", None)
            result = dp._execute_if_enabled(MiniExecutor(), execution, risk_review)

        self.assertEqual(result["order_status"], "SUBMITTED")
        self.assertIsNone(result.get("failure_reason"))
        self.assertEqual(result["exchange_order_id"], "demo-order-1")

    def test_run_cycle_persists_pending_record_before_submit(self):
        fake_db = FakeDB({"portfolio_state": {"positions": [], "total_equity": 10000}})
        snapshot = {
            "decision_id": "cycle_test_BNB",
            "cycleId": "cycle_test",
            "symbol": "BNB-USDT",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "decision_ready_features": {"macro_mode": "RISK_OFF"},
        }
        candidate = {
            "strategy_family": "DIRECTIONAL",
            "decision_intent": "SHORT",
            "trigger_source": "Blueprint_F2",
            "entry_type": "MARKET",
            "proposed_entry_price": 615.0,
            "proposed_sl_price": 628.0,
            "proposed_tp_price": 589.0,
            "reference_values": {"structure_resistance_stop_short": 628.0},
            "invalidation_basis": "F2 resistance broken",
            "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
        }
        candidate_batch = {
            "symbol": "BNB-USDT",
            "cycleId": "cycle_test",
            "candidate_proposals": [candidate],
        }
        rule_evaluation = {
            "passed": True,
            "approved_candidates": [candidate],
            "candidate_structure": {"overall_state": "single_signal"},
        }
        risk_review = {
            "symbol": "BNB-USDT",
            "cycleId": "cycle_test",
            "strategy_family": "DIRECTIONAL",
            "approved": True,
            "final_intent": "SHORT",
            "approved_risk_fraction": 0.01,
            "approved_position_size_usd": 424.0,
            "leverage": 2.0,
            "max_holding_bars": 3,
            "execution_action": "OPEN_SHORT",
            "next_position_state": "approved",
            "review_note": "approved from Blueprint_F2",
            "approved_candidate": candidate,
        }
        test_case = self

        class InspectingExecutor:
            def execute_trade(self, **kwargs):
                records = fake_db.store.get("trade_decision_records", [])
                test_case.assertEqual(len(records), 1)
                pending = records[0]
                test_case.assertEqual(pending["decisionId"], "cycle_test_BNB")
                test_case.assertEqual(pending["riskReview"]["approved_candidate"]["trigger_source"], "Blueprint_F2")
                test_case.assertEqual(pending["execution"]["order_status"], "PENDING_SUBMIT")
                return "order-f2-1"

        with patch.object(dp, "db", fake_db), \
             patch.object(dp, "TRACKED_SYMBOLS", ["BNB-USDT"]), \
             patch.object(dp, "_load_whale_analysis", return_value={}), \
             patch.object(dp, "_load_qlib_payload", return_value={}), \
             patch.object(dp, "_qlib_coin_map", return_value={}), \
             patch.object(dp, "_load_chart_feature_context_map", return_value={}), \
             patch.object(dp, "_build_macro_snapshot", return_value={}), \
             patch.object(dp, "_aligned_cycle_id", return_value="cycle_test"), \
             patch.object(dp, "_build_decision_snapshot", return_value=snapshot), \
             patch.object(dp, "_build_candidate_proposals", return_value=candidate_batch), \
             patch.object(dp, "_evaluate_rules", return_value=rule_evaluation), \
             patch.object(dp, "build_research_output", return_value=None), \
             patch.object(dp, "_build_risk_review_with_research", return_value=risk_review), \
             patch.object(dp, "run_post_trade_review", return_value={"evaluated_count": 0, "record_count": 1}), \
             patch.dict(os.environ, {"ENABLE_V2_EXECUTION": "1"}, clear=False):
            dp.run_deterministic_cycle(executor=InspectingExecutor())

        final_record = fake_db.store["trade_decision_records"][0]
        self.assertEqual(final_record["execution"]["order_status"], "SUBMITTED")
        self.assertEqual(final_record["execution"]["exchange_order_id"], "order-f2-1")
        self.assertEqual(final_record["riskReview"]["approved_candidate"]["trigger_source"], "Blueprint_F2")

    def test_append_trade_record_does_not_replace_active_execution_with_no_trade(self):
        active_record = {
            "decisionId": "cycle_test_BNB",
            "symbol": "BNB-USDT",
            "riskReview": {
                "approved": True,
                "final_intent": "SHORT",
                "approved_candidate": {"trigger_source": "Blueprint_F2"},
            },
            "execution": {
                "execution_action": "OPEN_SHORT",
                "order_status": "SUBMITTED",
                "sync_status": "SUBMITTED",
                "exchange_order_id": "order-f2-1",
            },
        }
        incoming_no_trade = {
            "decisionId": "cycle_test_BNB",
            "symbol": "BNB-USDT",
            "riskReview": {"approved": False, "final_intent": "NO_TRADE"},
            "execution": {
                "execution_action": "DO_NOTHING",
                "order_status": "SKIPPED",
                "sync_status": "SKIPPED",
            },
        }
        fake_db = FakeDB({"trade_decision_records": [active_record]})

        with patch.object(dp, "db", fake_db):
            dp._append_trade_record(incoming_no_trade)

        saved = fake_db.store["trade_decision_records"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["execution"]["order_status"], "SUBMITTED")
        self.assertEqual(saved[0]["riskReview"]["approved_candidate"]["trigger_source"], "Blueprint_F2")

    def test_open_execution_skips_when_symbol_position_already_exists(self):
        execution = {
            "symbol": "BNB-USDT",
            "execution_action": "OPEN_SHORT",
            "requested_size_usd": 1000.0,
            "requested_leverage": 2.0,
            "requested_protection": {"stop_loss": 628.0, "take_profit": 588.0},
            "history": [],
        }
        risk_review = {
            "approved_candidate": {
                "trigger_source": "Blueprint_F2",
                "proposed_sl_price": 628.0,
                "proposed_tp_price": 588.0,
            }
        }

        class MiniExecutor:
            def __init__(self):
                self.called = False

            def get_all_positions(self):
                return [{"symbol": "BNB", "type": "short", "amount": "0.92"}]

            def execute_trade(self, **kwargs):
                self.called = True
                return "should-not-submit"

        executor = MiniExecutor()
        with patch.dict(os.environ, {"TRADING_MODE": "DEMO"}, clear=False):
            os.environ.pop("ENABLE_V2_EXECUTION", None)
            result = dp._execute_if_enabled(executor, execution, risk_review)

        self.assertFalse(executor.called)
        self.assertEqual(result["order_status"], "SKIPPED")
        self.assertEqual(result["sync_status"], "POSITION_OPEN_SKIPPED")
        self.assertEqual(result["failure_reason"], "existing_position_open")


if __name__ == "__main__":
    unittest.main()
