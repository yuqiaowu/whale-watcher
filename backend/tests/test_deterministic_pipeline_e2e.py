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
import llm_client
import model_decision_agent
import vwap_features


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
    def _fresh_qlib_report(self):
        return {
            "fresh": True,
            "expected_completed_bar": "2026-05-11 00:00:00",
            "payload_as_of": "2026-05-11 00:00:00",
            "payload_symbols": sorted(dp.TRACKED_SYMBOLS),
            "missing_payload_symbols": [],
            "csv_latest_by_symbol": {symbol: "2026-05-11 00:00:00" for symbol in dp.TRACKED_SYMBOLS},
            "stale_csv_symbols": [],
            "reasons": [],
        }

    def test_regime_1d_uses_technical_structure_not_macro_mode(self):
        macro_snapshot = {"macro_mode": "RISK_OFF"}
        market_snapshot = {
            "price": 651.5,
            "sma5_1d": 638.11,
            "sma10_1d": 628.025,
            "sma200_1d": 700.0,
            "rsi_4h": 64.54,
        }

        self.assertEqual("BULL", dp._derive_regime_1d(macro_snapshot, market_snapshot))
        self.assertEqual(
            {
                "major_trend_1d": "BEAR",
                "major_trend_source": "PRICE_VS_SMA200",
                "sma200_distance_pct": -6.9286,
                "short_term_major_trend_alignment": "CONFLICT",
            },
            dp._derive_major_trend_context(market_snapshot, "BULL"),
        )

    def test_regime_1d_falls_back_to_rsi_when_trend_averages_missing(self):
        self.assertEqual(
            "BEAR",
            dp._derive_regime_1d({"macro_mode": "RISK_ON"}, {"rsi_4h": 42.0}),
        )

    def test_major_trend_context_is_unknown_without_sma200(self):
        self.assertEqual(
            {
                "major_trend_1d": "UNKNOWN",
                "major_trend_source": "SMA200_UNAVAILABLE",
                "sma200_distance_pct": None,
                "short_term_major_trend_alignment": "UNKNOWN",
            },
            dp._derive_major_trend_context({"price": 100.0, "sma5_1d": 101.0, "sma10_1d": 99.0}, "BULL"),
        )

    def test_model_decision_candidate_keeps_model_out_of_sizing(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_model",
            "timeframe": "4h",
            "snapshot_timestamp": "2026-05-11T00:00:00Z",
            "market_snapshot": {"price": 2500.0, "atr_14": 60.0, "structure_support_12bar_volume_confirmed": 2440.0, "sma50_4h": 2475.0},
            "decision_ready_features": {"macro_permission": "ALLOW_BOTH", "major_trend_1d": "BULL"},
            "position_snapshot": {"position_side": None},
            "is_decision_eligible": True,
        }
        market_state = {
            "technical": {"current_price": 2500.0, "atr14": 60.0},
        }
        model_decision = {
            "action": "BUY",
            "direction": "LONG",
            "confidence": 0.82,
            "setup_type": "bottom_reversal",
            "risk_level": "LOW",
            "horizon": "SWING",
            "reason_codes": ["vix_panic", "rsi_repair"],
            "invalid_if": ["close below reversal low"],
            "invalidation_rules": [
                {"field": "price", "op": "<=", "value_ref": "recent_swing_low", "persistence": 1, "reason": "reversal low lost"},
                {"field": "macro_permission", "op": "==", "value": "ALLOW_SHORT", "persistence": 1, "reason": "macro turned short-only"},
                {"field": "price", "op": ">=", "value": 2600.0, "reason": "wrong direction should reject"},
            ],
            "summary": "panic washout repaired",
        }

        batch = dp._build_model_decision_candidate_batch(snapshot, market_state, model_decision)
        evaluation = dp._evaluate_rules(snapshot, batch)
        research = dp._research_output_from_model_decision(snapshot, evaluation, model_decision)

        self.assertEqual("model_decision", batch["generation_mode"])
        self.assertEqual(1, len(batch["candidate_proposals"]))
        candidate = batch["candidate_proposals"][0]
        self.assertEqual("LONG", candidate["decision_intent"])
        self.assertEqual(dp.MODEL_DECISION_TRIGGER_SOURCE, candidate["trigger_source"])
        rules = candidate["invalidation_conditions"]["rules"]
        self.assertIn({"field": "price", "op": "<=", "value_ref": "model_stop_price"}, rules)
        self.assertIn({"field": "price", "op": "<=", "value_ref": "recent_swing_low", "reason": "reversal low lost", "persistence": 1}, rules)
        self.assertIn({"field": "macro_permission", "op": "==", "value": "ALLOW_SHORT", "reason": "macro turned short-only", "persistence": 1}, rules)
        self.assertEqual(
            "long_price_rule_wrong_direction",
            candidate["reference_values"]["model_rejected_invalidation_rules"][0]["reason"],
        )
        self.assertGreater(candidate["proposed_tp_price"], candidate["proposed_entry_price"])
        self.assertLess(candidate["proposed_sl_price"], candidate["proposed_entry_price"])
        self.assertTrue(evaluation["passed"])
        self.assertEqual("LONG", research["selected_intent"])
        self.assertEqual("HIGH", research["thesis_strength"])

    def test_model_decision_low_confidence_creates_no_candidate(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_model",
            "timeframe": "4h",
            "snapshot_timestamp": "2026-05-11T00:00:00Z",
            "market_snapshot": {"price": 2500.0, "atr_14": 60.0},
            "decision_ready_features": {"macro_permission": "ALLOW_BOTH", "major_trend_1d": "BULL"},
            "position_snapshot": {"position_side": None},
            "is_decision_eligible": True,
        }
        batch = dp._build_model_decision_candidate_batch(
            snapshot,
            {"technical": {"current_price": 2500.0, "atr14": 60.0}},
            {"action": "BUY", "direction": "LONG", "confidence": 0.6},
        )

        self.assertEqual([], batch["candidate_proposals"])
        self.assertEqual(0.65, batch["model_decision_diagnostic"]["min_confidence"])
        self.assertEqual("model_confidence_below_threshold", batch["model_decision_diagnostic"]["reason"])

    def test_model_decision_allows_vwap_reclaim_as_short_invalidation(self):
        snapshot = {
            "symbol": "BTC-USDT",
            "cycleId": "cycle_model",
            "timeframe": "4h",
            "snapshot_timestamp": "2026-05-15T16:00:00Z",
            "market_snapshot": {
                "price": 79120.5,
                "atr_14": 1047.2,
                "price_vs_vwap_16h_pct": -0.8187,
            },
            "decision_ready_features": {"macro_permission": "ALLOW_SHORT", "major_trend_1d": "BEAR"},
            "position_snapshot": {"position_side": None},
            "is_decision_eligible": True,
        }
        market_state = {
            "technical": {
                "current_price": 79120.5,
                "atr14": 1047.2,
                "price_vs_vwap_16h_pct": -0.8187,
            },
        }
        model_decision = {
            "action": "SELL",
            "direction": "SHORT",
            "confidence": 0.85,
            "setup_type": "trend_breakdown",
            "risk_level": "HIGH",
            "horizon": "MULTI_DAY",
            "reason_codes": ["price_below_vwap_16h"],
            "invalid_if": ["price reclaims VWAP_16h"],
            "invalidation_rules": [
                {"field": "price_vs_vwap_16h_pct", "op": ">=", "value": 0.0, "persistence": 2, "reason": "price reclaims VWAP_16h"},
            ],
            "summary": "short while price stays below 16h vwap",
        }

        batch = dp._build_model_decision_candidate_batch(snapshot, market_state, model_decision)

        candidate = batch["candidate_proposals"][0]
        self.assertIn(
            {"field": "price_vs_vwap_16h_pct", "op": ">=", "reason": "price reclaims VWAP_16h", "value": 0.0, "persistence": 2},
            candidate["invalidation_conditions"]["rules"],
        )
        self.assertEqual([], candidate["reference_values"]["model_rejected_invalidation_rules"])

    def test_model_market_state_carries_qlib_and_macro_fields(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_model",
            "timeframe": "4h",
            "snapshot_timestamp": "2026-05-11T00:00:00Z",
            "market_snapshot": {
                "price": 2500.0,
                "rsi_4h": 61.0,
                "williams_r14": -35.0,
                "bb_pct_b": 0.72,
                "ma_20": 2450.0,
                "sma50_1d": 2400.0,
                "sma200_1d": 2100.0,
                "volume_ratio": 1.4,
            },
            "onchain_snapshot": {
                "qlib_rank_8h": 2,
                "qlib_percentile_8h": 0.8,
                "p_up_8h": 0.62,
                "p_down_8h": 0.18,
                "p_flat_8h": 0.2,
                "qlib_relative_score_8h": 0.44,
                "flow_data_available": True,
                "token_net_flow": 7868172.45,
                "stablecoin_net_flow": 882425.49,
                "token_flow_semantic": "ACCUMULATION_HINT",
                "stablecoin_flow_semantic": "BUYING_POWER",
                "flow_composite_semantic": "LONG_SUPPORT",
                "flow_signal_mixed": False,
                "liquidation_long_to_volume_4h": 0.023,
                "liquidation_short_to_volume_4h": 0.019,
                "oi_now": 1525790534.8,
                "delta_oi_24h_percent": -4.55,
            },
            "decision_ready_features": {
                "qlib_direction": "LONG",
                "qlib_direction_confident": True,
                "vix_level": 18.5,
                "major_trend_1d": "BULL",
                "regime_1d": "BULL",
            },
            "macro_snapshot": {
                "macro_mode": "RISK_ON",
                "macro_permission": "ALLOW_BOTH",
                "macro_bias_tier": "MILD_RISK_ON",
                "prediction_market": {
                    "available": True,
                    "calculation_owner": "program",
                    "interpretation_scope": "prediction_market_expectation_reference_only",
                    "combined_score": 0.18,
                    "combined_label": "MILD_RISK_ON",
                    "score_delta_24h": 0.03,
                    "score_delta_24h_label": "SLIGHTLY_IMPROVING",
                },
            },
            "position_snapshot": {},
        }

        state = dp.build_market_state(snapshot)

        self.assertEqual(0.62, state["qlib"]["p_up_8h"])
        self.assertEqual("LONG", state["qlib"]["direction"])
        self.assertEqual(18.5, state["technical"]["vix"])
        self.assertEqual(2.0408, state["technical"]["relative_sma20_pct"])
        self.assertEqual(19.0476, state["technical"]["relative_sma200_pct"])
        self.assertTrue(state["onchain"]["flow_data_available"])
        self.assertEqual(7868172.45, state["onchain"]["token_net_flow"])
        self.assertEqual(882425.49, state["onchain"]["stablecoin_net_flow"])
        self.assertEqual("LONG_SUPPORT", state["onchain"]["flow_composite_semantic"])
        self.assertEqual(0.023, state["onchain"]["liquidation_long_to_volume_4h"])
        self.assertEqual(1525790534.8, state["onchain"]["open_interest"])
        self.assertTrue(state["data_availability"]["has_vix"])
        self.assertTrue(state["data_availability"]["has_sma20_distance"])
        self.assertTrue(state["data_availability"]["has_onchain_flow_data"])
        self.assertTrue(state["data_availability"]["has_flow_semantics"])
        self.assertEqual([], state["data_availability"]["required_missing_fields"])
        self.assertEqual(["exchange_netflow_24h", "large_transfer_count_24h"], state["data_availability"]["optional_missing_fields"])
        self.assertEqual("MILD_RISK_ON", state["macro"]["prediction_market"]["combined_label"])
        self.assertEqual("program", state["macro"]["prediction_market"]["calculation_owner"])

    def test_model_market_state_carries_vwap_fields(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_model",
            "timeframe": "4h",
            "snapshot_timestamp": "2026-05-11T00:00:00Z",
            "market_snapshot": {
                "price": 2500.0,
                "vwap_available": True,
                "vwap_bar": "5m",
                "vwap_source": "HLC3",
                "vwap_band_method": "volume_weighted_standard_deviation",
                "vwap_band_multipliers": [1, 2, 3],
                "vwap_4h": 2480.0,
                "vwap_std_4h": 8.0,
                "vwap_upper_1_4h": 2488.0,
                "vwap_lower_1_4h": 2472.0,
                "price_vs_vwap_4h_pct": 0.8065,
                "price_vwap_zscore_4h": 2.5,
                "vwap_4h_zone": "ABOVE_UPPER_2_BELOW_UPPER_3",
                "vwap_16h": 2460.0,
                "vwap_std_16h": 20.0,
                "vwap_upper_1_16h": 2480.0,
                "vwap_lower_1_16h": 2440.0,
                "vwap_upper_2_16h": 2500.0,
                "vwap_lower_2_16h": 2420.0,
                "vwap_upper_3_16h": 2520.0,
                "vwap_lower_3_16h": 2400.0,
                "price_vs_vwap_16h_pct": 1.626,
                "price_vs_vwap_upper_1_16h_pct": 0.8065,
                "price_vs_vwap_lower_1_16h_pct": 2.459,
                "price_vwap_zscore_16h": 2.0,
                "vwap_16h_zone": "ABOVE_UPPER_2_BELOW_UPPER_3",
            },
            "onchain_snapshot": {},
            "decision_ready_features": {},
            "macro_snapshot": {},
            "position_snapshot": {},
        }

        state = dp.build_market_state(snapshot)

        technical = state["technical"]
        self.assertTrue(technical["vwap_available"])
        self.assertEqual("5m", technical["vwap_bar"])
        self.assertEqual("HLC3", technical["vwap_source"])
        self.assertEqual([1, 2, 3], technical["vwap_band_multipliers"])
        self.assertEqual(2480.0, technical["vwap_4h"])
        self.assertEqual(2460.0, technical["vwap_16h"])
        self.assertEqual(2.0, technical["price_vwap_zscore_16h"])
        self.assertEqual("ABOVE_UPPER_2_BELOW_UPPER_3", technical["vwap_16h_zone"])
        self.assertTrue(state["data_availability"]["has_vwap_4h"])
        self.assertTrue(state["data_availability"]["has_vwap_16h"])

    def test_model_market_state_preserves_zero_values(self):
        snapshot = {
            "symbol": "BNB-USDT",
            "cycleId": "cycle_model",
            "timeframe": "4h",
            "snapshot_timestamp": "2026-05-11T00:00:00Z",
            "market_snapshot": {
                "price": 600.0,
                "volume_ratio": 0.0,
                "drawdown_120d_pct": 0.0,
            },
            "qlib_snapshot": {
                "rank": 5,
                "qlib_percentile": 0.0,
                "p_up_8h": 0.0,
                "p_down_8h": 0.7,
                "p_flat_8h": 0.3,
                "qlib_relative_score_8h": 0.0,
            },
            "onchain_snapshot": {
                "qlib_percentile_8h": 0.9,
                "p_up_8h": 0.6,
            },
            "decision_ready_features": {},
            "macro_snapshot": {},
            "position_snapshot": {},
        }

        state = dp.build_market_state(snapshot)

        self.assertEqual(0.0, state["qlib"]["qlib_percentile"])
        self.assertEqual(0.0, state["qlib"]["p_up_8h"])
        self.assertEqual(0.0, state["qlib"]["relative_score_8h"])
        self.assertEqual(0.0, state["technical"]["relative_volume_20"])
        self.assertEqual(0.0, state["technical"]["prior_120d_drawdown_pct"])
        self.assertTrue(state["data_availability"]["has_prior_120d_drawdown"])

    def test_vwap_feature_computation_uses_hlc3_quote_volume_and_bands(self):
        candles = []
        for idx in range(192):
            price = 100.0 + idx * 0.1
            candles.append(
                [
                    str(1770000000000 + idx * 300000),
                    str(price - 0.2),
                    str(price + 0.5),
                    str(price - 0.5),
                    str(price),
                    "10",
                    "1000",
                    str(1000 + idx),
                    "1",
                ]
            )

        features = vwap_features.compute_vwap_features_from_candles(candles)

        self.assertTrue(features["vwap_available"])
        self.assertTrue(features["vwap_4h_available"])
        self.assertTrue(features["vwap_16h_available"])
        self.assertEqual("5m", features["vwap_bar"])
        self.assertEqual("HLC3", features["vwap_source"])
        self.assertEqual("volume_weighted_standard_deviation", features["vwap_band_method"])
        self.assertEqual([1, 2, 3], features["vwap_band_multipliers"])
        self.assertEqual(48, features["vwap_4h_bar_count"])
        self.assertEqual(192, features["vwap_16h_bar_count"])
        self.assertGreater(features["vwap_upper_1_16h"], features["vwap_16h"])
        self.assertLess(features["vwap_lower_1_16h"], features["vwap_16h"])
        self.assertIn("vwap_16h_zone", features)

    def test_qlib_freshness_report_flags_stale_payload_and_csv(self):
        qlib_payload = {
            "as_of": "2026-05-10 20:00:00",
            "coins": [{"symbol": symbol, "rank": idx + 1} for idx, symbol in enumerate(dp.TRACKED_SYMBOLS)],
        }
        qlib_map = dp._qlib_coin_map(qlib_payload)
        chart_context_map = {
            symbol: {"chart_context_bar_time": "2026-05-10 20:00:00"}
            for symbol in dp.TRACKED_SYMBOLS
        }

        report = dp._qlib_freshness_report(
            qlib_payload,
            qlib_map,
            chart_context_map,
            expected_bar=pd.Timestamp("2026-05-11 00:00:00"),
        )

        self.assertFalse(report["fresh"])
        self.assertEqual("2026-05-11 00:00:00", report["expected_completed_bar"])
        self.assertIn("payload_as_of_stale", report["reasons"])
        self.assertIn("feature_csv_stale", report["reasons"])
        self.assertEqual(sorted(dp.TRACKED_SYMBOLS), report["stale_csv_symbols"])

    def test_qlib_stale_blocks_qlib_dependent_candidate(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_model",
            "timeframe": "4h",
            "snapshot_timestamp": "2026-05-11T00:00:00Z",
            "market_snapshot": {},
            "decision_ready_features": {"macro_permission": "ALLOW_BOTH"},
            "position_snapshot": {"position_side": "NONE"},
            "is_decision_eligible": True,
            "qlib_freshness": {
                "fresh": False,
                "expected_completed_bar": "2026-05-11 00:00:00",
                "payload_as_of": "2026-05-10 20:00:00",
                "reasons": ["payload_as_of_stale"],
            },
        }
        candidate_batch = {
            "candidate_proposals": [
                {"trigger_source": "Blueprint_E1"}
            ]
        }

        result = dp._evaluate_rules(snapshot, candidate_batch)

        self.assertFalse(result["passed"])
        self.assertEqual(["QLIB_STALE"], result["reason_codes"])
        self.assertIn("QLIB_FRESHNESS_CHECK", [trace["rule"] for trace in result["rule_trace"]])

    def test_inconsistent_model_decision_falls_back_to_wait_flat(self):
        with (
            patch.object(
                model_decision_agent,
                "call_deepseek_text_with_audit",
                return_value=("bullish evidence but formatter will contradict it", {"status": "parsed"}),
            ),
            patch.object(
                model_decision_agent,
                "call_deepseek_json_with_audit",
                return_value=({"action": "BUY", "direction": "SHORT", "confidence": 0.9}, {"status": "parsed"}),
            ),
        ):
            decision = model_decision_agent.build_model_decision({"symbol": "ETH-USDT"})

        self.assertEqual("WAIT", decision["action"])
        self.assertEqual("FLAT", decision["direction"])
        self.assertEqual(["inconsistent_action_direction_BUY_SHORT"], decision["reason_codes"])
        self.assertEqual("reasoner_then_json_formatter", decision["llm_audit"]["pipeline"])

    def test_model_decision_reasoner_failure_is_wait_flat(self):
        with patch.object(
            model_decision_agent,
            "call_deepseek_text_with_audit",
            return_value=(None, {"status": "http_error"}),
        ):
            decision = model_decision_agent.build_model_decision({"symbol": "ETH-USDT"})

        self.assertEqual("WAIT", decision["action"])
        self.assertEqual("FLAT", decision["direction"])
        self.assertEqual(["reasoner_http_error"], decision["reason_codes"])

    def test_deepseek_text_retries_transient_failure(self):
        class Response:
            status_code = 200
            text = "{}"

            def json(self):
                return {"choices": [{"message": {"content": "WAIT because evidence conflicts"}}]}

        calls = {"count": 0}

        def flaky_post(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("transient chunk failure")
            return Response()

        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test", "DEEPSEEK_RETRY_ATTEMPTS": "2", "DEEPSEEK_RETRY_DELAY_SECONDS": "0"}),
            patch.object(llm_client.requests, "post", side_effect=flaky_post),
        ):
            content, audit = llm_client.call_deepseek_text_with_audit(
                "prompt",
                system_prompt="system",
            )

        self.assertEqual("WAIT because evidence conflicts", content)
        self.assertEqual(2, calls["count"])
        self.assertEqual(2, audit["attempt_count"])
        self.assertEqual("exception", audit["attempts"][0]["status"])
        self.assertEqual("parsed", audit["status"])

    def test_model_decision_keeps_structured_invalidation_rules(self):
        formatter_decision = {
            "action": "SELL",
            "direction": "SHORT",
            "confidence": 0.72,
            "setup_type": "trend_breakdown",
            "risk_level": "MEDIUM",
            "horizon": "SWING",
            "reason_codes": ["trend_breakdown"],
            "invalid_if": ["price reclaims swing high"],
            "invalidation_rules": [
                {"field": "price", "op": ">=", "value_ref": "recent_swing_high", "persistence": 2, "reason": "swing high reclaimed"},
                {"field": "", "op": ">=", "value": 1},
            ],
            "summary": "short setup",
        }
        verifier_result = {
            "veto": False,
            "veto_reasons": [],
            "missing_data": [],
            "risk_notes": [],
            "risk_adjustment": "NEUTRAL",
            "adjustment_reason": "",
        }
        with (
            patch.dict(os.environ, {"ENABLE_MODEL_DECISION_VERIFIER": "1"}, clear=False),
            patch.object(
                model_decision_agent,
                "call_deepseek_text_with_audit",
                return_value=("short evidence exists", {"status": "parsed"}),
            ),
            patch.object(
                model_decision_agent,
                "call_deepseek_json_with_audit",
                side_effect=[
                    (formatter_decision, {"status": "parsed"}),
                    (verifier_result, {"status": "parsed"}),
                ],
            ),
        ):
            decision = model_decision_agent.build_model_decision({"symbol": "BTC-USDT"})

        self.assertEqual("SELL", decision["action"])
        self.assertEqual(
            [{"field": "price", "op": ">=", "reason": "swing high reclaimed", "value_ref": "recent_swing_high", "persistence": 2}],
            decision["invalidation_rules"],
        )
        self.assertEqual("NEUTRAL", decision["verifier"]["risk_adjustment"])

    def test_model_decision_verifier_veto_falls_back_to_wait_flat(self):
        formatter_decision = {
            "action": "BUY",
            "direction": "LONG",
            "confidence": 0.88,
            "setup_type": "trend_following",
            "risk_level": "MEDIUM",
            "horizon": "SWING",
            "reason_codes": ["qlib_upside", "trend_support"],
            "invalid_if": ["trend fails"],
            "summary": "upside setup",
        }
        verifier_veto = {
            "veto": True,
            "veto_reasons": ["qlib_stale", "macro_conflict"],
            "missing_data": ["fresh_qlib"],
            "risk_notes": ["evidence conflicts"],
        }

        with (
            patch.dict(os.environ, {"ENABLE_MODEL_DECISION_VERIFIER": "1"}, clear=False),
            patch.object(
                model_decision_agent,
                "call_deepseek_text_with_audit",
                return_value=("long evidence exists, but needs verification", {"status": "parsed"}),
            ),
            patch.object(
                model_decision_agent,
                "call_deepseek_json_with_audit",
                side_effect=[
                    (formatter_decision, {"status": "parsed", "model": "deepseek-chat"}),
                    (verifier_veto, {"status": "parsed", "model": "deepseek-chat"}),
                ],
            ) as json_mock,
        ):
            decision = model_decision_agent.build_model_decision({"symbol": "ETH-USDT"})

        self.assertEqual(2, json_mock.call_count)
        self.assertEqual("WAIT", decision["action"])
        self.assertEqual("FLAT", decision["direction"])
        self.assertEqual(["verifier_veto", "qlib_stale", "macro_conflict"], decision["reason_codes"])
        self.assertEqual("reasoner_then_json_formatter_then_verifier", decision["llm_audit"]["pipeline"])

    def test_model_decision_verifier_downgrades_optional_onchain_missing_veto(self):
        formatter_decision = {
            "action": "SELL",
            "direction": "SHORT",
            "confidence": 0.82,
            "setup_type": "trend_breakdown",
            "risk_level": "MEDIUM",
            "horizon": "SWING",
            "reason_codes": ["qlib_downside", "trend_breakdown"],
            "invalid_if": ["breakdown fails"],
            "summary": "downside setup",
        }
        verifier_veto = {
            "veto": True,
            "veto_reasons": [
                "Missing exchange netflow, large transfer count, whale bias, and stablecoin flow weaken onchain confirmation"
            ],
            "missing_data": [],
            "risk_notes": [],
        }

        with (
            patch.dict(os.environ, {"ENABLE_MODEL_DECISION_VERIFIER": "1"}, clear=False),
            patch.object(
                model_decision_agent,
                "call_deepseek_text_with_audit",
                return_value=("short evidence exists, but onchain coverage is unavailable", {"status": "parsed"}),
            ),
            patch.object(
                model_decision_agent,
                "call_deepseek_json_with_audit",
                side_effect=[
                    (formatter_decision, {"status": "parsed", "model": "deepseek-chat"}),
                    (verifier_veto, {"status": "parsed", "model": "deepseek-chat"}),
                ],
            ),
        ):
            decision = model_decision_agent.build_model_decision(
                {
                    "symbol": "DOGE-USDT",
                    "onchain": {"flow_data_available": False, "flow_composite_semantic": "UNAVAILABLE"},
                }
            )

        self.assertEqual("SELL", decision["action"])
        self.assertEqual("SHORT", decision["direction"])
        self.assertFalse(decision["verifier"]["veto"])
        self.assertEqual([], decision["verifier"]["veto_reasons"])
        self.assertEqual(verifier_veto["veto_reasons"], decision["verifier"]["missing_data"])
        self.assertIn("optional_onchain_missing_data_downgraded", decision["verifier"]["risk_notes"])
        self.assertEqual("NEUTRAL", decision["verifier"]["risk_adjustment"])

    def test_model_decision_verifier_keeps_risk_adjustment_for_risk_review(self):
        formatter_decision = {
            "action": "SELL",
            "direction": "SHORT",
            "confidence": 0.67,
            "setup_type": "trend_breakdown",
            "risk_level": "MEDIUM",
            "horizon": "SWING",
            "reason_codes": ["qlib_downside"],
            "invalid_if": ["breakdown fails"],
            "summary": "downside setup with some risks",
        }
        verifier_result = {
            "veto": False,
            "veto_reasons": [],
            "missing_data": [],
            "risk_notes": ["countertrend bounce risk"],
            "risk_adjustment": "REDUCE_SIZE",
            "adjustment_reason": "short evidence is valid but not clean",
        }

        with (
            patch.dict(os.environ, {"ENABLE_MODEL_DECISION_VERIFIER": "1"}, clear=False),
            patch.object(
                model_decision_agent,
                "call_deepseek_text_with_audit",
                return_value=("short evidence exists but size should be conservative", {"status": "parsed"}),
            ),
            patch.object(
                model_decision_agent,
                "call_deepseek_json_with_audit",
                side_effect=[
                    (formatter_decision, {"status": "parsed", "model": "deepseek-chat"}),
                    (verifier_result, {"status": "parsed", "model": "deepseek-chat"}),
                ],
            ),
        ):
            decision = model_decision_agent.build_model_decision({"symbol": "ETH-USDT"})

        self.assertEqual("SELL", decision["action"])
        self.assertEqual("SHORT", decision["direction"])
        self.assertFalse(decision["verifier"]["veto"])
        self.assertEqual("REDUCE_SIZE", decision["verifier"]["risk_adjustment"])
        self.assertEqual("short evidence is valid but not clean", decision["verifier"]["adjustment_reason"])

    def test_model_decision_verifier_keeps_real_veto_after_filtering_missing_data(self):
        formatter_decision = {
            "action": "SELL",
            "direction": "SHORT",
            "confidence": 0.86,
            "setup_type": "trend_breakdown",
            "risk_level": "MEDIUM",
            "horizon": "SWING",
            "reason_codes": ["qlib_downside"],
            "invalid_if": ["momentum reverses"],
            "summary": "downside setup",
        }
        verifier_veto = {
            "veto": True,
            "veto_reasons": [
                "Missing exchange netflow and large transfer count weaken onchain confirmation",
                "Williams %R oversold condition contradicts new short entry",
            ],
            "missing_data": [],
            "risk_notes": [],
        }

        with (
            patch.dict(os.environ, {"ENABLE_MODEL_DECISION_VERIFIER": "1"}, clear=False),
            patch.object(
                model_decision_agent,
                "call_deepseek_text_with_audit",
                return_value=("short evidence exists, but verifier must check conflicts", {"status": "parsed"}),
            ),
            patch.object(
                model_decision_agent,
                "call_deepseek_json_with_audit",
                side_effect=[
                    (formatter_decision, {"status": "parsed", "model": "deepseek-chat"}),
                    (verifier_veto, {"status": "parsed", "model": "deepseek-chat"}),
                ],
            ),
        ):
            decision = model_decision_agent.build_model_decision(
                {
                    "symbol": "ETH-USDT",
                    "onchain": {"flow_data_available": True, "flow_composite_semantic": "SHORT_SUPPORT"},
                }
            )

        self.assertEqual("WAIT", decision["action"])
        self.assertEqual("FLAT", decision["direction"])
        self.assertEqual(
            ["verifier_veto", "Williams %R oversold condition contradicts new short entry"],
            decision["reason_codes"],
        )
        self.assertEqual(["Williams %R oversold condition contradicts new short entry"], decision["verifier"]["veto_reasons"])
        self.assertEqual([verifier_veto["veto_reasons"][0]], decision["verifier"]["missing_data"])

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
        self.assertIsNone(eth_context["drawdown_120d_pct"])

    def test_chart_feature_context_computes_model_decision_features(self):
        rows = []
        base_time = pd.Timestamp("2025-01-01 00:00:00")
        for idx in range(730):
            close = 100 + idx
            rows.append(
                {
                    "datetime": base_time + pd.Timedelta(hours=4 * idx),
                    "instrument": "ETH",
                    "open": close - 2,
                    "high": close + 10,
                    "low": close - 10,
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

            with (
                patch.object(dp, "QLOB_FEATURES_PATH", csv_path),
                patch.object(dp, "_current_4h_bar_start_utc", return_value=base_time + pd.Timedelta(hours=4 * 730)),
            ):
                context = dp._load_chart_feature_context_map()

        eth_context = context["ETH"]
        self.assertAlmostEqual(-30.303, eth_context["williams_r14"], places=3)
        self.assertEqual(0.0, eth_context["drawdown_120d_pct"])

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
            {"qlib_score": 0.001, "rank": 2, "p_up_8h": 0.52, "p_down_8h": 0.24, "p_flat_8h": 0.24, "market_data": {"atr_14": 35, "close": 2400, "ma_20": 2350}},
            {"positions": [], "total_equity": 10000},
            "cycle_test",
        )

        self.assertEqual(snapshot["onchain_snapshot"]["token_flow_semantic"], "DISTRIBUTION_PRESSURE")
        self.assertEqual(snapshot["onchain_snapshot"]["stablecoin_flow_semantic"], "BUYING_POWER")
        self.assertEqual(snapshot["onchain_snapshot"]["flow_composite_semantic"], "MIXED")
        self.assertFalse(snapshot["decision_ready_features"]["flow_support_long"])
        self.assertFalse(snapshot["decision_ready_features"]["flow_support_short"])
        self.assertTrue(snapshot["decision_ready_features"]["flow_signal_mixed"])
        self.assertEqual(2350, snapshot["market_snapshot"]["sma20_4h"])

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
             patch.object(dp, "_qlib_freshness_report", return_value=self._fresh_qlib_report()), \
             patch.object(dp, "run_post_trade_review", return_value={"evaluated_count": 0, "record_count": 0}), \
             patch.dict(os.environ, {"ENABLE_V2_EXECUTION": "1"}, clear=False):
            result = dp.run_deterministic_cycle(executor=FakeExecutor())

        self.assertIn("executions", result)
        self.assertIn("records", result)
        self.assertEqual(result["record_count"], 5)
        self.assertEqual(len(result["executions"]), 5)
        self.assertEqual(len(result["records"]), 5)
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
             patch.object(dp, "_qlib_freshness_report", return_value=self._fresh_qlib_report()), \
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

    def test_vwap_fields_are_mirrored_for_downstream_context(self):
        whale_analysis = {
            "fear_greed": {"value": 50, "value_classification": "Neutral"},
            "macro": {},
            "news": {},
            "btc": {"market": {"price": 78000}},
        }
        vwap = {
            "vwap_available": True,
            "vwap_bar": "5m",
            "vwap_source": "HLC3",
            "vwap_latest_price": 78077.1,
            "vwap_4h": 78021.658,
            "vwap_std_4h": 180.0,
            "price_vs_vwap_4h_pct": 0.0711,
            "price_vwap_zscore_4h": 0.3085,
            "vwap_4h_zone": "ABOVE_VWAP_BELOW_UPPER_1",
            "vwap_16h": 78415.274,
            "vwap_std_16h": 440.0,
            "price_vs_vwap_16h_pct": -0.4313,
            "price_vwap_zscore_16h": -0.766,
            "vwap_16h_zone": "BELOW_VWAP_ABOVE_LOWER_1",
        }
        snapshot = dp._build_decision_snapshot(
            "BTC",
            whale_analysis,
            {"rank": 1, "p_up_8h": 0.2, "p_down_8h": 0.6, "p_flat_8h": 0.2, "market_data": {"close": 78000}},
            {"positions": [], "total_equity": 10000},
            "cycle_test",
            chart_context={"vwap": vwap},
        )

        market = snapshot["market_snapshot"]
        features = snapshot["decision_ready_features"]
        self.assertTrue(features["vwap_available"])
        self.assertEqual(market["vwap_bar"], features["vwap_bar"])
        self.assertEqual(market["vwap_source"], features["vwap_source"])
        self.assertEqual(market["vwap_4h"], features["vwap_4h"])
        self.assertEqual(market["price_vs_vwap_4h_pct"], features["price_vs_vwap_4h_pct"])
        self.assertEqual(market["vwap_4h_zone"], features["vwap_4h_zone"])
        self.assertEqual(market["vwap_16h"], features["vwap_16h"])
        self.assertEqual(market["price_vwap_zscore_16h"], features["price_vwap_zscore_16h"])
        self.assertEqual(market["vwap_16h_zone"], features["vwap_16h_zone"])

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
        self.assertEqual(risk_review["approved_position_size_usd"], 400.0)
        self.assertIn("same-direction resonance increased size", risk_review["review_note"])
        self.assertEqual(risk_review["candidate_structure"]["overall_state"], "same_direction_resonance")

    def test_macro_permission_conflict_reduces_risk_without_blocking_candidate(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "is_decision_eligible": True,
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {"macro_mode": "RISK_OFF", "macro_permission": "ALLOW_SHORT"},
        }
        candidate = {
            "strategy_family": "DIRECTIONAL",
            "decision_intent": "LONG",
            "trigger_source": "Blueprint_F1",
            "entry_type": "MARKET",
            "rationale": "technical long",
            "proposed_entry_price": 100,
            "proposed_sl_price": 95,
            "proposed_tp_price": 112,
            "reference_values": {},
            "invalidation_basis": "long invalid",
            "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
        }
        rule_evaluation = dp._evaluate_rules(snapshot, {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "candidate_proposals": [candidate],
        })

        self.assertTrue(rule_evaluation["passed"])
        self.assertNotIn("BEAR_MARKET_LONG_BLOCKED", rule_evaluation["reason_codes"])
        self.assertEqual("LONG", rule_evaluation["approved_candidates"][0]["decision_intent"])

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(200.0, risk_review["approved_position_size_usd"])
        self.assertEqual(2.0, risk_review["leverage"])
        self.assertIn("macro conflict reduced size", risk_review["review_note"])

    def test_major_trend_conflict_reduces_risk_without_blocking_candidate(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "timeframe": "4h",
            "snapshot_timestamp": 1712743200,
            "is_decision_eligible": True,
            "position_snapshot": {"position_side": "NONE"},
            "decision_ready_features": {
                "macro_mode": "MIXED",
                "macro_permission": "ALLOW_BOTH",
                "major_trend_1d": "BEAR",
            },
        }
        candidate = {
            "strategy_family": "DIRECTIONAL",
            "decision_intent": "LONG",
            "trigger_source": "Blueprint_F1",
            "entry_type": "MARKET",
            "rationale": "short-term technical long",
            "proposed_entry_price": 100,
            "proposed_sl_price": 95,
            "proposed_tp_price": 112,
            "reference_values": {},
            "invalidation_basis": "long invalid",
            "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
        }
        rule_evaluation = dp._evaluate_rules(snapshot, {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "candidate_proposals": [candidate],
        })

        self.assertTrue(rule_evaluation["passed"])
        self.assertEqual("LONG", rule_evaluation["approved_candidates"][0]["decision_intent"])
        self.assertIn(
            "MAJOR_TREND_SIZING_CONTEXT",
            [trace["rule"] for trace in rule_evaluation["rule_trace"]],
        )

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(300.0, risk_review["approved_position_size_usd"])
        self.assertEqual(2.5, risk_review["leverage"])
        self.assertEqual(3, risk_review["max_holding_bars"])
        self.assertIn("major trend conflict lightly reduced size", risk_review["review_note"])

    def test_risk_review_applies_verifier_reduce_size_recommendation(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "decision_ready_features": {"macro_mode": "MIXED", "macro_permission": "ALLOW_BOTH", "major_trend_1d": "BEAR"},
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {"overall_state": "single_signal"},
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "short setup",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 105,
                    "proposed_tp_price": 90,
                    "reference_values": {
                        "model_verifier": {
                            "risk_adjustment": "REDUCE_SIZE",
                            "adjustment_reason": "valid but noisy evidence",
                        }
                    },
                    "invalidation_basis": "model",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                }
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(200.0, risk_review["approved_position_size_usd"])
        self.assertEqual(2.0, risk_review["leverage"])
        self.assertEqual(1, risk_review["max_holding_bars"])
        self.assertIn("verifier recommended size reduction: valid but noisy evidence", risk_review["review_note"])

    def test_risk_review_blocks_short_when_bull_regime_lacks_short_flow_support(self):
        snapshot = {
            "symbol": "BTC-USDT",
            "cycleId": "cycle_test",
            "decision_ready_features": {
                "regime_1d": "BULL",
                "flow_support_long": True,
                "flow_support_short": False,
                "macro_permission": "ALLOW_BOTH",
            },
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {"overall_state": "single_signal"},
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "short setup",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 105,
                    "proposed_tp_price": 90,
                    "reference_values": {},
                    "invalidation_basis": "model",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                }
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}) as load_portfolio:
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        load_portfolio.assert_not_called()
        self.assertFalse(risk_review["approved"])
        self.assertEqual("NO_TRADE", risk_review["final_intent"])
        self.assertEqual("DO_NOTHING", risk_review["execution_action"])
        self.assertIn("pre_entry_bull_regime_without_flow_support", risk_review["review_note"])

    def test_risk_review_blocks_long_when_bear_regime_lacks_long_flow_support(self):
        snapshot = {
            "symbol": "DOGE-USDT",
            "cycleId": "cycle_test",
            "decision_ready_features": {
                "regime_1d": "BEAR",
                "flow_support_long": False,
                "flow_support_short": True,
                "macro_permission": "ALLOW_BOTH",
            },
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {"overall_state": "single_signal"},
            "approved_candidates": [
                {
                    "decision_intent": "LONG",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "long setup",
                    "proposed_entry_price": 0.1,
                    "proposed_sl_price": 0.095,
                    "proposed_tp_price": 0.11,
                    "reference_values": {},
                    "invalidation_basis": "model",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                }
            ],
        }

        risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertFalse(risk_review["approved"])
        self.assertEqual("DO_NOTHING", risk_review["execution_action"])
        self.assertIn("pre_entry_bear_regime_without_flow_support", risk_review["review_note"])

    def test_risk_review_blocks_doge_directional_trade_without_qlib_trend_and_volume(self):
        snapshot = {
            "symbol": "DOGE-USDT",
            "cycleId": "cycle_test",
            "market_snapshot": {
                "price": 0.103,
                "volume_ratio": 0.72,
                "price_vs_vwap_16h_pct": -0.4,
            },
            "onchain_snapshot": {
                "p_up_8h": 0.18,
                "p_down_8h": 0.20,
                "p_flat_8h": 0.62,
            },
            "decision_ready_features": {
                "regime_1d": "BEAR",
                "major_trend_1d": "BEAR",
                "flow_support_short": True,
                "macro_permission": "ALLOW_BOTH",
            },
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {"overall_state": "single_signal"},
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "doge short",
                    "proposed_entry_price": 0.103,
                    "proposed_sl_price": 0.108,
                    "proposed_tp_price": 0.095,
                    "reference_values": {},
                    "invalidation_basis": "model",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                }
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}) as load_portfolio:
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        load_portfolio.assert_not_called()
        self.assertFalse(risk_review["approved"])
        self.assertEqual("DO_NOTHING", risk_review["execution_action"])
        self.assertIn("pre_entry_doge_qlib_flat_or_not_aligned", risk_review["review_note"])

    def test_risk_review_blocks_high_qlib_flat_short_without_breakdown_confirmation(self):
        snapshot = {
            "symbol": "BTC-USDT",
            "cycleId": "cycle_test",
            "market_snapshot": {
                "price": 77500.0,
                "price_vs_vwap_16h_pct": 0.68,
                "price_vs_vwap_4h_pct": 0.22,
                "structure_support_12bar_volume_confirmed": 76018.0,
            },
            "onchain_snapshot": {"p_up_8h": 0.18, "p_down_8h": 0.12, "p_flat_8h": 0.70},
            "decision_ready_features": {
                "regime_1d": "BEAR",
                "major_trend_1d": "BEAR",
                "flow_support_short": True,
                "macro_permission": "ALLOW_BOTH",
            },
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {"overall_state": "single_signal"},
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "macro short while qlib flat",
                    "proposed_entry_price": 77500.0,
                    "proposed_sl_price": 78500.0,
                    "proposed_tp_price": 75500.0,
                    "reference_values": {},
                    "invalidation_basis": "model",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                }
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}) as load_portfolio:
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        load_portfolio.assert_not_called()
        self.assertFalse(risk_review["approved"])
        self.assertEqual("DO_NOTHING", risk_review["execution_action"])
        self.assertIn("pre_entry_high_qlib_flat_short_without_vwap_or_structure_break", risk_review["review_note"])

    def test_risk_review_allows_high_qlib_flat_short_after_vwap_breakdown(self):
        snapshot = {
            "symbol": "BTC-USDT",
            "cycleId": "cycle_test",
            "market_snapshot": {
                "price": 75500.0,
                "price_vs_vwap_16h_pct": -0.35,
                "price_vs_vwap_4h_pct": -0.22,
                "structure_support_12bar_volume_confirmed": 76018.0,
            },
            "onchain_snapshot": {"p_up_8h": 0.18, "p_down_8h": 0.12, "p_flat_8h": 0.70},
            "decision_ready_features": {
                "regime_1d": "BEAR",
                "major_trend_1d": "BEAR",
                "flow_support_short": True,
                "macro_permission": "ALLOW_BOTH",
            },
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {"overall_state": "single_signal"},
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "short after vwap breakdown",
                    "proposed_entry_price": 75500.0,
                    "proposed_sl_price": 76500.0,
                    "proposed_tp_price": 73500.0,
                    "reference_values": {},
                    "invalidation_basis": "model",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                }
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual("OPEN_SHORT", risk_review["execution_action"])

    def test_risk_review_can_apply_verifier_modest_size_increase(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "decision_ready_features": {"macro_mode": "MIXED", "macro_permission": "ALLOW_BOTH", "major_trend_1d": "BEAR"},
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {"overall_state": "single_signal"},
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "clean short setup",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 105,
                    "proposed_tp_price": 90,
                    "reference_values": {
                        "model_verifier": {
                            "risk_adjustment": "INCREASE_SIZE",
                            "adjustment_reason": "multi-source alignment",
                        }
                    },
                    "invalidation_basis": "model",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                }
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(400.0, risk_review["approved_position_size_usd"])
        self.assertIn("verifier recommended modest size increase: multi-source alignment", risk_review["review_note"])

    def test_risk_review_ignores_verifier_increase_when_direction_conflicts(self):
        snapshot = {
            "symbol": "ETH-USDT",
            "cycleId": "cycle_test",
            "decision_ready_features": {"macro_mode": "RISK_OFF", "macro_permission": "ALLOW_SHORT", "major_trend_1d": "BEAR"},
        }
        rule_evaluation = {
            "passed": True,
            "candidate_structure": {"overall_state": "single_signal"},
            "approved_candidates": [
                {
                    "decision_intent": "LONG",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "long setup with conflicts",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 95,
                    "proposed_tp_price": 110,
                    "reference_values": {
                        "model_verifier": {
                            "risk_adjustment": "INCREASE_SIZE",
                            "adjustment_reason": "model says strong",
                        }
                    },
                    "invalidation_basis": "model",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                }
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(150.0, risk_review["approved_position_size_usd"])
        self.assertIn("verifier increase ignored due to conflict or low thesis", risk_review["review_note"])

    def test_risk_review_caps_max_loss_at_two_percent_of_equity_and_uses_five_x_default_leverage(self):
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
        self.assertEqual(risk_review["leverage"], 5.0)
        self.assertEqual(risk_review["approved_position_size_usd"], 40.0)
        self.assertEqual(abs(100 - 150) / 100 * risk_review["approved_position_size_usd"], 20.0)

    def test_risk_review_caps_new_trade_by_total_portfolio_exposure(self):
        snapshot = {
            "symbol": "SOL-USDT",
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
                "resonance_groups": {"LONG": [], "SHORT": ["ModelDecision_LLM"]},
                "approved_groups": {"LONG": [], "SHORT": ["ModelDecision_LLM"]},
                "approved_resonance_strength": 1,
            },
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "model short",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 95,
                    "proposed_tp_price": 110,
                    "reference_values": {},
                    "invalidation_basis": "invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
            ],
        }
        portfolio_state = {
            "total_equity": 1000.0,
            "positions": [{"symbol": "ETH", "amount": "7", "currentPrice": 100}],
        }

        with patch.object(dp, "_load_portfolio_state", return_value=portfolio_state):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertTrue(risk_review["approved"])
        self.assertEqual(50.0, risk_review["approved_position_size_usd"])
        self.assertIn("total exposure limit", risk_review["review_note"])

    def test_risk_review_rejects_when_total_portfolio_exposure_is_full(self):
        snapshot = {
            "symbol": "SOL-USDT",
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
                "resonance_groups": {"LONG": [], "SHORT": ["ModelDecision_LLM"]},
                "approved_groups": {"LONG": [], "SHORT": ["ModelDecision_LLM"]},
                "approved_resonance_strength": 1,
            },
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "model short",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 95,
                    "proposed_tp_price": 110,
                    "reference_values": {},
                    "invalidation_basis": "invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
            ],
        }
        portfolio_state = {
            "total_equity": 1000.0,
            "positions": [{"symbol": "ETH", "notionalUsd": 800}],
        }

        with patch.object(dp, "_load_portfolio_state", return_value=portfolio_state):
            risk_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)

        self.assertFalse(risk_review["approved"])
        self.assertEqual("NO_TRADE", risk_review["final_intent"])
        self.assertIn("portfolio total exposure cap reached", risk_review["review_note"])

    def test_directional_holding_bars_are_capped_by_thesis_strength(self):
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
                "resonance_groups": {"LONG": [], "SHORT": ["ModelDecision_LLM"]},
                "approved_groups": {"LONG": [], "SHORT": ["ModelDecision_LLM"]},
                "approved_resonance_strength": 1,
            },
            "approved_candidates": [
                {
                    "decision_intent": "SHORT",
                    "trigger_source": "ModelDecision_LLM",
                    "entry_type": "MARKET",
                    "rationale": "model short",
                    "proposed_entry_price": 100,
                    "proposed_sl_price": 105,
                    "proposed_tp_price": 90,
                    "reference_values": {},
                    "invalidation_basis": "invalid",
                    "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
                },
            ],
        }

        with patch.object(dp, "_load_portfolio_state", return_value={"total_equity": 1000.0}):
            default_review = dp._build_risk_review_with_research(snapshot, rule_evaluation, None)
            medium_review = dp._build_risk_review_with_research(
                snapshot,
                rule_evaluation,
                {"selected_intent": "SHORT", "thesis_strength": "MEDIUM"},
            )
            low_review = dp._build_risk_review_with_research(
                snapshot,
                rule_evaluation,
                {"selected_intent": "SHORT", "thesis_strength": "LOW"},
            )

        self.assertEqual(3, default_review["max_holding_bars"])
        self.assertEqual(2, medium_review["max_holding_bars"])
        self.assertEqual(1, low_review["max_holding_bars"])
        self.assertEqual(5.0, default_review["leverage"])
        self.assertEqual(3.0, medium_review["leverage"])
        self.assertEqual(2.0, low_review["leverage"])

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
            "decision_id": "cycle_test_ETH",
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
             patch.object(dp, "_qlib_freshness_report", return_value=self._fresh_qlib_report()), \
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

        fake_db = FakeDB({"portfolio_state": {"positions": []}})
        with patch.dict(os.environ, {"TRADING_MODE": "DEMO"}, clear=False), patch.object(dp, "db", fake_db):
            os.environ.pop("ENABLE_V2_EXECUTION", None)
            result = dp._execute_if_enabled(MiniExecutor(), execution, risk_review)

        self.assertEqual(result["order_status"], "SUBMITTED")
        self.assertIsNone(result.get("failure_reason"))
        self.assertEqual(result["exchange_order_id"], "demo-order-1")

    def test_execution_request_includes_okx_order_provenance(self):
        snapshot = {
            "decision_id": "cycle_2026-05-12_1200_DOGE",
            "cycleId": "cycle_2026-05-12_1200",
            "symbol": "DOGE-USDT",
        }
        risk_review = {
            "approved": True,
            "strategy_family": "DIRECTIONAL",
            "execution_action": "OPEN_SHORT",
            "approved_position_size_usd": 278.27,
            "leverage": 2,
            "final_intent": "SHORT",
            "approved_candidate": {
                "entry_type": "MARKET",
                "proposed_entry_price": 0.10934,
                "proposed_sl_price": 0.1136,
                "proposed_tp_price": 0.10083,
            },
        }

        execution = dp._build_execution_request(snapshot, risk_review)

        self.assertTrue(execution["client_order_id"].startswith("ww2605121200DOGES"))
        self.assertLessEqual(len(execution["client_order_id"]), 32)
        self.assertEqual("WWV2", execution["order_tag"])
        self.assertEqual(
            {
                "decisionId": "cycle_2026-05-12_1200_DOGE",
                "cycleId": "cycle_2026-05-12_1200",
                "symbol": "DOGE-USDT",
                "intent": "SHORT",
                "execution_action": "OPEN_SHORT",
            },
            execution["order_provenance"],
        )

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
                test_case.assertEqual(
                    pending["opening_thesis_snapshot"]["invalidation_conditions"],
                    candidate["invalidation_conditions"],
                )
                return "order-f2-1"

        with patch.object(dp, "db", fake_db), \
             patch.object(dp, "TRACKED_SYMBOLS", ["BNB-USDT"]), \
             patch.object(dp, "_load_whale_analysis", return_value={}), \
             patch.object(dp, "_load_qlib_payload", return_value={}), \
             patch.object(dp, "_qlib_coin_map", return_value={}), \
             patch.object(dp, "_load_chart_feature_context_map", return_value={}), \
             patch.object(dp, "_load_vwap_feature_context_map", return_value={}), \
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
        self.assertEqual(final_record["opening_thesis_snapshot"]["source"], "pre_execution_decision_record")

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
