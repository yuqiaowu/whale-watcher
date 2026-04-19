import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


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

        def build(symbol, rsi, macd_line, macd_signal, support, resistance):
            return {
                **base_snapshot,
                "symbol": symbol,
                "market_snapshot": {
                    "price": 100.0,
                    "atr_14": 2.0,
                    "rsi_4h": rsi,
                    "macd_line_4h": macd_line,
                    "macd_signal_4h": macd_signal,
                    "rel_volume_60": 1.6,
                    "structure_support_stop_long": support,
                    "structure_resistance_stop_short": resistance,
                },
                "onchain_snapshot": {},
            }

        bnb_batch = dp._build_candidate_proposals(build("BNB-USDT", 55, 1.2, 0.8, 95.0, 105.0))
        self.assertIn("Blueprint_F1", [c["trigger_source"] for c in bnb_batch["candidate_proposals"]])

        eth_short_batch = dp._build_candidate_proposals(build("ETH-USDT", 45, -1.2, -0.8, 95.0, 105.0))
        self.assertIn("Blueprint_F2", [c["trigger_source"] for c in eth_short_batch["candidate_proposals"]])

        doge_long_batch = dp._build_candidate_proposals(build("DOGE-USDT", 55, 1.2, 0.8, 95.0, 105.0))
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in doge_long_batch["candidate_proposals"]])

        doge_short_batch = dp._build_candidate_proposals(build("DOGE-USDT", 45, -1.2, -0.8, 95.0, 105.0))
        self.assertIn("Blueprint_F2", [c["trigger_source"] for c in doge_short_batch["candidate_proposals"]])

        btc_batch = dp._build_candidate_proposals(build("BTC-USDT", 55, 1.2, 0.8, 95.0, 105.0))
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in btc_batch["candidate_proposals"]])
        self.assertNotIn("Blueprint_F2", [c["trigger_source"] for c in btc_batch["candidate_proposals"]])

        sol_batch = dp._build_candidate_proposals(build("SOL-USDT", 45, -1.2, -0.8, 95.0, 105.0))
        self.assertNotIn("Blueprint_F1", [c["trigger_source"] for c in sol_batch["candidate_proposals"]])
        self.assertNotIn("Blueprint_F2", [c["trigger_source"] for c in sol_batch["candidate_proposals"]])


if __name__ == "__main__":
    unittest.main()
