import json
import math
import os
from typing import Any, Dict, List, Optional

from llm_client import call_deepseek_json_with_audit, call_deepseek_text_with_audit


ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD", "WAIT"}
ALLOWED_DIRECTIONS = {"LONG", "SHORT", "FLAT"}
ALLOWED_SETUP_TYPES = {
    "bottom_reversal",
    "top_distribution",
    "trend_following",
    "trend_breakdown",
    "range_rotation",
    "no_edge",
}
ALLOWED_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_HORIZONS = {"SHORT", "SWING", "MULTI_DAY"}
ALLOWED_VERIFIER_RISK_ADJUSTMENTS = {"REDUCE_SIZE", "NEUTRAL", "INCREASE_SIZE"}

OPTIONAL_ONCHAIN_MISSING_TERMS = (
    "onchain",
    "on-chain",
    "chain flow",
    "flow data",
    "exchange netflow",
    "exchange_netflow",
    "large transfer",
    "large_transfer",
    "whale bias",
    "whale_bias",
    "flow bias",
    "flow_bias",
    "token flow",
    "token_net_flow",
    "stablecoin",
    "stablecoin_net_flow",
)
OPTIONAL_MISSING_WORDS = (
    "missing",
    "unavailable",
    "absent",
    "incomplete",
    "lack",
    "lacks",
    "null",
    "none",
    "not available",
    "not provided",
)
REQUIRED_DATA_TERMS = (
    "qlib",
    "price",
    "technical",
    "rsi",
    "williams",
    "sma",
    "atr",
    "volume",
    "freshness",
)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        parsed = float(value)
        if math.isnan(parsed):
            return None
        return parsed
    except Exception:
        return None


def _pct_distance(price: Optional[float], reference: Optional[float]) -> Optional[float]:
    if price is None or reference in (None, 0):
        return None
    return round((price - reference) / reference * 100, 4)


def _compact_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return None


def _compact_list(value: Any, limit: int = 6) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text[:120])
        if len(out) >= limit:
            break
    return out


def _compact_text(value: Any, limit: int = 160) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _compact_rule_list(value: Any, limit: int = 8) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rule = {
            "field": str(item.get("field") or "").strip(),
            "op": str(item.get("op") or "").strip(),
            "reason": str(item.get("reason") or "").strip()[:160],
        }
        if item.get("value_ref") is not None:
            rule["value_ref"] = str(item.get("value_ref") or "").strip()
        elif item.get("value") is not None:
            rule["value"] = item.get("value")
        try:
            rule["persistence"] = max(1, min(6, int(item.get("persistence") or 1)))
        except (TypeError, ValueError):
            rule["persistence"] = 1
        if rule["field"] and rule["op"] and ("value_ref" in rule or "value" in rule):
            out.append(rule)
        if len(out) >= limit:
            break
    return out


def _env_flag_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes"}


def build_market_state(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    market = _compact_dict(snapshot.get("market_snapshot"))
    features = _compact_dict(snapshot.get("decision_ready_features"))
    onchain = _compact_dict(snapshot.get("onchain_snapshot"))
    qlib = _compact_dict(snapshot.get("qlib_snapshot"))
    macro = _compact_dict(snapshot.get("macro_snapshot"))
    qlib_freshness = _compact_dict(snapshot.get("qlib_freshness"))
    price = _safe_float(market.get("price") or market.get("close"))

    technical = {
        "current_price": price,
        "rsi14": _safe_float(_first_present(market.get("rsi_14"), market.get("rsi_4h"))),
        "rsi_source": "rsi_14" if market.get("rsi_14") is not None else "rsi_4h",
        "williams_r14": _safe_float(market.get("williams_r14")),
        "vix": _safe_float(_first_present(macro.get("vix"), macro.get("vix_level"), features.get("vix_level"))),
        "bollinger_position": _safe_float(_first_present(market.get("bb_pos_20"), market.get("bb_pct_b"), features.get("bb_pos_20"))),
        "relative_sma20_pct": _pct_distance(price, _safe_float(_first_present(market.get("sma20_1d"), market.get("sma20_4h")))),
        "relative_sma50_pct": _pct_distance(price, _safe_float(_first_present(market.get("sma50_1d"), market.get("sma50_4h")))),
        "relative_sma200_pct": _pct_distance(price, _safe_float(_first_present(market.get("sma200_1d"), features.get("sma200_1d")))),
        "relative_volume_20": _safe_float(_first_present(market.get("rel_volume_20"), market.get("volume_ratio"), market.get("rel_volume_60"))),
        "prior_120d_drawdown_pct": _safe_float(_first_present(market.get("drawdown_120d_pct"), features.get("drawdown_120d_pct"))),
        "atr14": _safe_float(market.get("atr_14")),
        "major_trend_1d": features.get("major_trend_1d"),
        "regime_1d": features.get("regime_1d"),
        "vwap_available": bool(market.get("vwap_available")),
        "vwap_bar": market.get("vwap_bar"),
        "vwap_source": market.get("vwap_source"),
        "vwap_band_method": market.get("vwap_band_method"),
        "vwap_band_multipliers": market.get("vwap_band_multipliers") or [],
        "vwap_4h": _safe_float(market.get("vwap_4h")),
        "vwap_std_4h": _safe_float(market.get("vwap_std_4h")),
        "vwap_upper_1_4h": _safe_float(market.get("vwap_upper_1_4h")),
        "vwap_lower_1_4h": _safe_float(market.get("vwap_lower_1_4h")),
        "price_vs_vwap_4h_pct": _safe_float(market.get("price_vs_vwap_4h_pct")),
        "price_vwap_zscore_4h": _safe_float(market.get("price_vwap_zscore_4h")),
        "vwap_4h_zone": market.get("vwap_4h_zone"),
        "vwap_16h": _safe_float(market.get("vwap_16h")),
        "vwap_std_16h": _safe_float(market.get("vwap_std_16h")),
        "vwap_upper_1_16h": _safe_float(market.get("vwap_upper_1_16h")),
        "vwap_lower_1_16h": _safe_float(market.get("vwap_lower_1_16h")),
        "vwap_upper_2_16h": _safe_float(market.get("vwap_upper_2_16h")),
        "vwap_lower_2_16h": _safe_float(market.get("vwap_lower_2_16h")),
        "vwap_upper_3_16h": _safe_float(market.get("vwap_upper_3_16h")),
        "vwap_lower_3_16h": _safe_float(market.get("vwap_lower_3_16h")),
        "price_vs_vwap_16h_pct": _safe_float(market.get("price_vs_vwap_16h_pct")),
        "price_vs_vwap_upper_1_16h_pct": _safe_float(market.get("price_vs_vwap_upper_1_16h_pct")),
        "price_vs_vwap_lower_1_16h_pct": _safe_float(market.get("price_vs_vwap_lower_1_16h_pct")),
        "price_vs_vwap_upper_2_16h_pct": _safe_float(market.get("price_vs_vwap_upper_2_16h_pct")),
        "price_vs_vwap_lower_2_16h_pct": _safe_float(market.get("price_vs_vwap_lower_2_16h_pct")),
        "price_vs_vwap_upper_3_16h_pct": _safe_float(market.get("price_vs_vwap_upper_3_16h_pct")),
        "price_vs_vwap_lower_3_16h_pct": _safe_float(market.get("price_vs_vwap_lower_3_16h_pct")),
        "price_vwap_zscore_16h": _safe_float(market.get("price_vwap_zscore_16h")),
        "vwap_16h_zone": market.get("vwap_16h_zone"),
    }

    data_availability = {
        "has_rsi14": technical["rsi14"] is not None,
        "has_williams_r14": technical["williams_r14"] is not None,
        "has_vix": technical["vix"] is not None,
        "has_sma20_distance": technical["relative_sma20_pct"] is not None,
        "has_sma50_distance": technical["relative_sma50_pct"] is not None,
        "has_sma200_distance": technical["relative_sma200_pct"] is not None,
        "has_relative_volume_20": technical["relative_volume_20"] is not None,
        "has_prior_120d_drawdown": technical["prior_120d_drawdown_pct"] is not None,
        "has_vwap_4h": technical["vwap_4h"] is not None,
        "has_vwap_16h": technical["vwap_16h"] is not None,
        "has_onchain_flow_data": bool(onchain.get("flow_data_available")),
        "has_token_net_flow": onchain.get("token_net_flow") is not None,
        "has_stablecoin_net_flow": onchain.get("stablecoin_net_flow") is not None,
        "has_flow_semantics": bool(onchain.get("flow_composite_semantic")),
        "has_exchange_netflow_24h": onchain.get("exchange_netflow_24h") is not None,
        "has_large_transfer_count_24h": onchain.get("large_transfer_count_24h") is not None,
    }

    return {
        "schema_version": "model_market_state_v1",
        "symbol": snapshot.get("symbol"),
        "cycleId": snapshot.get("cycleId"),
        "timeframe": snapshot.get("timeframe"),
        "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
        "technical": technical,
        "qlib": {
            "rank": _first_present(qlib.get("rank"), onchain.get("qlib_rank_8h")),
            "qlib_percentile": _safe_float(_first_present(qlib.get("qlib_percentile"), onchain.get("qlib_percentile_8h"), features.get("qlib_percentile_8h"))),
            "p_up_8h": _safe_float(_first_present(qlib.get("p_up_8h"), onchain.get("p_up_8h"), features.get("p_up_8h"))),
            "p_down_8h": _safe_float(_first_present(qlib.get("p_down_8h"), onchain.get("p_down_8h"), features.get("p_down_8h"))),
            "p_flat_8h": _safe_float(_first_present(qlib.get("p_flat_8h"), onchain.get("p_flat_8h"), features.get("p_flat_8h"))),
            "direction": features.get("qlib_direction"),
            "direction_confident": features.get("qlib_direction_confident"),
            "relative_score_8h": _safe_float(_first_present(qlib.get("qlib_relative_score_8h"), qlib.get("qlib_score"), onchain.get("qlib_relative_score_8h"))),
            "data_fresh": features.get("qlib_data_fresh"),
            "freshness": qlib_freshness,
        },
        "onchain": {
            "whale_bias": onchain.get("whale_bias"),
            "flow_bias": onchain.get("flow_bias"),
            "flow_data_available": bool(onchain.get("flow_data_available")),
            "token_net_flow": _safe_float(onchain.get("token_net_flow")),
            "stablecoin_net_flow": _safe_float(onchain.get("stablecoin_net_flow")),
            "token_flow_semantic": onchain.get("token_flow_semantic"),
            "stablecoin_flow_semantic": onchain.get("stablecoin_flow_semantic"),
            "flow_composite_semantic": onchain.get("flow_composite_semantic"),
            "flow_signal_mixed": onchain.get("flow_signal_mixed"),
            "funding_rate": onchain.get("funding_rate"),
            "funding_zscore": onchain.get("funding_zscore"),
            "open_interest": _safe_float(_first_present(onchain.get("oi_now"), onchain.get("open_interest"))),
            "delta_oi_24h_percent": _safe_float(onchain.get("delta_oi_24h_percent")),
            "liquidation_long_usd": _safe_float(onchain.get("liquidation_long_usd")),
            "liquidation_short_usd": _safe_float(onchain.get("liquidation_short_usd")),
            "liquidation_long_to_volume_4h": _safe_float(onchain.get("liquidation_long_to_volume_4h")),
            "liquidation_short_to_volume_4h": _safe_float(onchain.get("liquidation_short_to_volume_4h")),
            "sentiment_score": _safe_float(onchain.get("sentiment_score")),
            "exchange_netflow_24h": onchain.get("exchange_netflow_24h"),
            "large_transfer_count_24h": onchain.get("large_transfer_count_24h"),
        },
        "macro": {
            "macro_mode": macro.get("macro_mode"),
            "macro_permission": macro.get("macro_permission"),
            "macro_bias_tier": macro.get("macro_bias_tier"),
            "macro_impact_score": macro.get("macro_impact_score"),
            "macro_horizon": macro.get("macro_horizon"),
            "final_macro_decision": macro.get("final_macro_decision"),
            "macro_decision_source": macro.get("macro_decision_source"),
            "prediction_market": macro.get("prediction_market"),
            "marginal_tags": macro.get("marginal_tags") or macro.get("key_tags") or [],
        },
        "position": snapshot.get("position_snapshot") or {},
        "data_availability": data_availability,
    }


def _fallback_decision(market_state: Dict[str, Any], audit: Optional[Dict[str, Any]] = None, reason: str = "llm_unavailable") -> Dict[str, Any]:
    return {
        "schema_version": "model_decision_v1",
        "action": "WAIT",
        "direction": "FLAT",
        "confidence": 0.0,
        "setup_type": "no_edge",
        "risk_level": "HIGH",
        "horizon": "SHORT",
        "reason_codes": [reason],
        "invalid_if": [],
        "invalidation_rules": [],
        "summary": "model decision unavailable or invalid; no trade",
        "model_role": "direction_only",
        "program_controls": ["entry", "stop_loss", "take_profit", "position_size", "leverage", "execution"],
        "llm_audit": audit or {},
    }


def _model_decision_json_contract() -> Dict[str, Any]:
    return {
        "action": sorted(ALLOWED_ACTIONS),
        "direction": sorted(ALLOWED_DIRECTIONS),
        "confidence": "number from 0.0 to 1.0",
        "setup_type": sorted(ALLOWED_SETUP_TYPES),
        "risk_level": sorted(ALLOWED_RISK_LEVELS),
        "horizon": sorted(ALLOWED_HORIZONS),
        "reason_codes": "array of short strings; evidence tags only",
        "invalid_if": "array of short strings; directional thesis invalidation only",
        "invalidation_rules": (
            "array of executable invalidation rule objects. Allowed shape: "
            "{\"field\": string, \"op\": one of >= <= > < == !=, \"value_ref\" or \"value\": string/number/bool, "
            "\"persistence\": integer 1..6, \"reason\": short string}. Use only fields present in market_state."
        ),
        "summary": "short human-readable evidence summary",
    }


def _compact_audit(
    reasoning_audit: Dict[str, Any],
    formatter_audit: Dict[str, Any],
    verifier_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    verifier_ran = bool(verifier_audit)
    return {
        "provider": "deepseek",
        "pipeline": "reasoner_then_json_formatter_then_verifier" if verifier_ran else "reasoner_then_json_formatter",
        "reasoner": reasoning_audit or {},
        "formatter": formatter_audit or {},
        "verifier": verifier_audit or {},
    }


def _verifier_contract() -> Dict[str, Any]:
    return {
        "veto": "boolean; true means reject the proposed directional decision",
        "veto_reasons": "array of short strings explaining only rejection reasons",
        "missing_data": "array of short strings for missing/stale data that weakens the trade",
        "risk_notes": "array of short strings for risk context; no sizing or execution instructions",
        "risk_adjustment": sorted(ALLOWED_VERIFIER_RISK_ADJUSTMENTS),
        "adjustment_reason": "short reason for REDUCE_SIZE or INCREASE_SIZE; risk review makes the final sizing decision",
    }


def _decision_needs_verifier(decision: Dict[str, Any]) -> bool:
    action = str(decision.get("action") or "").upper()
    direction = str(decision.get("direction") or "").upper()
    confidence = _safe_float(decision.get("confidence")) or 0.0
    min_confidence = _safe_float(os.getenv("MODEL_DECISION_MIN_CONFIDENCE")) or 0.65
    return (
        ((action == "BUY" and direction == "LONG") or (action == "SELL" and direction == "SHORT"))
        and confidence >= min_confidence
    )


def _is_optional_onchain_missing_reason(reason: str) -> bool:
    text = str(reason or "").strip().lower()
    if not text:
        return False
    if not any(term in text for term in OPTIONAL_MISSING_WORDS):
        return False
    if not any(term in text for term in OPTIONAL_ONCHAIN_MISSING_TERMS):
        return False
    return not any(term in text for term in REQUIRED_DATA_TERMS)


def _normalize_verifier_result(verifier_raw: Dict[str, Any]) -> Dict[str, Any]:
    veto_reasons = _compact_list(verifier_raw.get("veto_reasons"), limit=6)
    missing_data = _compact_list(verifier_raw.get("missing_data"), limit=6)
    risk_notes = _compact_list(verifier_raw.get("risk_notes"), limit=6)
    risk_adjustment = str(verifier_raw.get("risk_adjustment") or "NEUTRAL").upper()
    if risk_adjustment not in ALLOWED_VERIFIER_RISK_ADJUSTMENTS:
        risk_adjustment = "NEUTRAL"

    hard_veto_reasons: List[str] = []
    optional_missing_reasons: List[str] = []
    for reason in veto_reasons:
        if _is_optional_onchain_missing_reason(reason):
            optional_missing_reasons.append(reason)
        else:
            hard_veto_reasons.append(reason)

    for reason in optional_missing_reasons:
        if reason not in missing_data and len(missing_data) < 6:
            missing_data.append(reason)

    veto = bool(verifier_raw.get("veto")) and bool(hard_veto_reasons)
    if bool(verifier_raw.get("veto")) and optional_missing_reasons and not hard_veto_reasons:
        note = "optional_onchain_missing_data_downgraded"
        if note not in risk_notes and len(risk_notes) < 6:
            risk_notes.append(note)

    return {
        "veto": veto,
        "veto_reasons": hard_veto_reasons[:6],
        "missing_data": missing_data[:6],
        "risk_notes": risk_notes[:6],
        "risk_adjustment": "NEUTRAL" if veto else risk_adjustment,
        "adjustment_reason": _compact_text(verifier_raw.get("adjustment_reason")),
    }


def _verify_model_decision(
    market_state: Dict[str, Any],
    decision: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    verifier_system_prompt = (
        "You are a conservative trade verifier. Your job is to find reasons to reject a proposed directional "
        "crypto trade. If the trade is not bad enough to reject, you may recommend REDUCE_SIZE, NEUTRAL, or "
        "INCREASE_SIZE for the downstream deterministic risk review. Do not choose exact position size, leverage, "
        "entry, stop loss, take profit, or execution. Return only JSON."
    )
    verifier_prompt = (
        "Review the proposed model decision against the market state. Be skeptical. Veto if evidence is "
        "contradictory, required data is stale/missing, direction conflicts with technical context, or confidence "
        "is not well supported. Do not veto solely because optional onchain fields are unavailable. For symbols "
        "where market_state.onchain.flow_data_available=false or flow_composite_semantic=UNAVAILABLE, absence of "
        "exchange_netflow_24h, large_transfer_count_24h, whale_bias, flow_bias, token flow, or stablecoin flow is "
        "expected coverage limitation; put it in missing_data or risk_notes, not veto_reasons. Treat Qlib freshness, "
        "current price, technical indicators, and risk/invalidation facts as required data. If there is no clear "
        "non-missing-data rejection reason, set veto=false. Use risk_adjustment only as a sizing recommendation: "
        "REDUCE_SIZE for meaningful but non-fatal risks, INCREASE_SIZE only when evidence is unusually clean and "
        "multi-source aligned, otherwise NEUTRAL. Output only JSON matching this contract.\n\n"
        f"contract={json.dumps(_verifier_contract(), ensure_ascii=False, sort_keys=True)}\n\n"
        f"market_state={json.dumps(market_state, ensure_ascii=False, sort_keys=True)}\n\n"
        f"proposed_decision={json.dumps(decision, ensure_ascii=False, sort_keys=True)}"
    )
    return call_deepseek_json_with_audit(
        verifier_prompt,
        system_prompt=verifier_system_prompt,
        temperature=0.0,
        enable_env_flag="ENABLE_MODEL_DECISION_VERIFIER",
        model_env="MODEL_DECISION_VERIFIER_MODEL",
        default_model="deepseek-chat",
    )


def _normalize_decision(raw: Dict[str, Any], market_state: Dict[str, Any], audit: Dict[str, Any]) -> Dict[str, Any]:
    action = str(raw.get("action") or "WAIT").upper()
    direction = str(raw.get("direction") or "FLAT").upper()
    setup_type = str(raw.get("setup_type") or "no_edge").lower()
    risk_level = str(raw.get("risk_level") or "HIGH").upper()
    horizon = str(raw.get("horizon") or "SHORT").upper()

    if action not in ALLOWED_ACTIONS:
        return _fallback_decision(market_state, audit, f"invalid_action_{action}")
    if direction not in ALLOWED_DIRECTIONS:
        return _fallback_decision(market_state, audit, f"invalid_direction_{direction}")
    if (action == "BUY" and direction != "LONG") or (action == "SELL" and direction != "SHORT"):
        return _fallback_decision(market_state, audit, f"inconsistent_action_direction_{action}_{direction}")
    if action in {"HOLD", "WAIT"} and direction != "FLAT":
        return _fallback_decision(market_state, audit, f"inconsistent_action_direction_{action}_{direction}")
    if setup_type not in ALLOWED_SETUP_TYPES:
        setup_type = "no_edge"
    if risk_level not in ALLOWED_RISK_LEVELS:
        risk_level = "HIGH"
    if horizon not in ALLOWED_HORIZONS:
        horizon = "SHORT"

    confidence = _safe_float(raw.get("confidence"))
    if confidence is None:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "schema_version": "model_decision_v1",
        "action": action,
        "direction": direction,
        "confidence": round(confidence, 4),
        "setup_type": setup_type,
        "risk_level": risk_level,
        "horizon": horizon,
        "reason_codes": _compact_list(raw.get("reason_codes"), limit=8),
        "invalid_if": _compact_list(raw.get("invalid_if"), limit=6),
        "invalidation_rules": _compact_rule_list(raw.get("invalidation_rules"), limit=8),
        "summary": str(raw.get("summary") or "")[:500],
        "model_role": "direction_only",
        "program_controls": ["entry", "stop_loss", "take_profit", "position_size", "leverage", "execution"],
        "llm_audit": audit,
    }


def build_model_decision(market_state: Dict[str, Any]) -> Dict[str, Any]:
    reasoning_system_prompt = (
        "You are a crypto trading decision analyst using DeepSeek reasoning. Decide only whether the setup "
        "deserves a directional trade. Do not choose position size, leverage, exact order placement, stop loss, "
        "or take profit. The deterministic program controls risk and execution. Return only a concise decision "
        "brief with evidence bullets, contradictions, data gaps, and thesis invalidation. Do not expose hidden "
        "chain-of-thought. Before finalizing, explicitly self-criticize the trade idea by checking evidence for "
        "LONG, evidence for SHORT, evidence for WAIT/FLAT, stale or missing data, and what would invalidate the "
        "directional view. If evidence conflicts, prefer WAIT/FLAT."
    )
    reasoning_prompt = (
        "Use the supplied market state only. Produce a concise decision brief, not JSON. "
        "Allowed final directional meanings: BUY+LONG for an opening long idea, SELL+SHORT for an opening "
        "short idea, and HOLD/WAIT+FLAT for no new trade. Missing data should reduce confidence. "
        "The brief must not include position size, leverage, exact order placement, stop loss, or take profit.\n\n"
        "Self-criticism checklist to apply before the final brief:\n"
        "1. What supports LONG?\n"
        "2. What supports SHORT?\n"
        "3. What supports WAIT/FLAT?\n"
        "4. What data is missing or stale?\n"
        "5. What would invalidate this view?\n"
        "6. If evidence conflicts, choose WAIT/FLAT.\n\n"
        f"market_state={json.dumps(market_state, ensure_ascii=False, sort_keys=True)}"
    )
    reasoning_draft, reasoning_audit = call_deepseek_text_with_audit(
        reasoning_prompt,
        system_prompt=reasoning_system_prompt,
        temperature=0.0,
        enable_env_flag="ENABLE_MODEL_DECISION_LLM",
    )
    if not reasoning_draft:
        status = str((reasoning_audit or {}).get("status") or "reasoner_unavailable")
        return _fallback_decision(market_state, _compact_audit(reasoning_audit or {}, {}), f"reasoner_{status}")

    formatter_system_prompt = (
        "You are a deterministic JSON formatter for a crypto trading system. Convert the supplied DeepSeek "
        "reasoning brief into one JSON object. Do not add new market judgments. Do not output markdown. "
        "Use only the allowed contract. If the brief is uncertain, contradictory, or asks for unsupported fields, "
        "return WAIT/FLAT with low confidence."
    )
    formatter_prompt = (
        "Return one JSON object matching this contract. This is JSON mode, so output only JSON.\n\n"
        f"contract={json.dumps(_model_decision_json_contract(), ensure_ascii=False, sort_keys=True)}\n\n"
        "Consistency rules:\n"
        "- BUY must pair with LONG.\n"
        "- SELL must pair with SHORT.\n"
        "- HOLD or WAIT must pair with FLAT.\n"
        "- The model controls only direction and confidence; program controls entry, stop_loss, take_profit, "
        "position_size, leverage, and execution.\n"
        "- For invalidation_rules, output only simple executable comparisons over observable fields. "
        "Do not invent fields. Use value_ref when comparing price to a known reference such as recent_swing_high, "
        "recent_swing_low, sma50_4h, sma200_1d, model_stop_price, p_up_8h, p_down_8h, p_flat_8h, macro_permission, or macro_mode.\n"
        "- For macro invalidation, use macro_permission == ALLOW_SHORT to invalidate LONG, or macro_permission == ALLOW_LONG to invalidate SHORT.\n"
        "- If confidence is weak or data is missing, prefer WAIT/FLAT.\n\n"
        f"market_state={json.dumps(market_state, ensure_ascii=False, sort_keys=True)}\n\n"
        f"reasoning_brief={reasoning_draft[:3000]}"
    )
    raw, formatter_audit = call_deepseek_json_with_audit(
        formatter_prompt,
        system_prompt=formatter_system_prompt,
        temperature=0.0,
        enable_env_flag="ENABLE_MODEL_DECISION_LLM",
    )
    audit = _compact_audit(reasoning_audit or {}, formatter_audit or {})
    if not isinstance(raw, dict):
        status = str((formatter_audit or {}).get("status") or "formatter_unavailable")
        return _fallback_decision(market_state, audit, f"formatter_{status}")
    decision = _normalize_decision(raw, market_state, audit)
    if not _decision_needs_verifier(decision):
        return decision

    verifier_raw, verifier_audit = _verify_model_decision(market_state, decision)
    audit = _compact_audit(reasoning_audit or {}, formatter_audit or {}, verifier_audit or {})
    if not isinstance(verifier_raw, dict):
        status = str((verifier_audit or {}).get("status") or "verifier_unavailable")
        return _fallback_decision(market_state, audit, f"verifier_{status}")

    verifier_result = _normalize_verifier_result(verifier_raw)
    if verifier_result["veto"]:
        fallback = _fallback_decision(market_state, audit, "verifier_veto")
        fallback["reason_codes"] = ["verifier_veto", *verifier_result["veto_reasons"]][:8]
        fallback["summary"] = "model decision vetoed by conservative verifier"
        fallback["verifier"] = verifier_result
        return fallback

    decision["llm_audit"] = audit
    decision["verifier"] = verifier_result
    return decision
