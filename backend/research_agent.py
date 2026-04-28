import os
import json
from typing import Any, Dict, List, Optional, Tuple

from db_client import db
from llm_client import call_llm_json_with_audit


ALLOWED_SELECTED_INTENTS = {"LONG", "SHORT", "GRID_NEUTRAL", "NO_TRADE", "WAIT_FOR_CONFIRMATION"}
ALLOWED_MACRO_BIAS = {"LONG_BIAS", "SHORT_BIAS", "NEUTRAL"}
ALLOWED_MACRO_HORIZON = {"INTRADAY", "SWING", "MULTI_DAY", "NOISE"}
ALLOWED_MACRO_MODE = {"RISK_ON", "RISK_OFF", "EVENT_DRIVEN", "MIXED", "NO_CLEAR_IMPACT"}
ALLOWED_MACRO_PERMISSION = {"ALLOW_LONG", "ALLOW_SHORT", "ALLOW_BOTH", "ALLOW_NEITHER"}
ALLOWED_CONFLICT_STATE = {"none", "candidate_conflict", "macro_vs_onchain", "macro_vs_technical"}
ALLOWED_SCENARIO_LABELS = {"trend_following", "range_rotation", "countertrend_rebound", "trend_breakdown", "wait_no_trade"}
ALLOWED_ALIGNMENT = {"SUPPORT", "NEUTRAL", "CONFLICT", "UNAVAILABLE"}
ALLOWED_TECH = {"STRONG", "WEAK", "NONE"}
ALLOWED_STRENGTH = {"HIGH", "MEDIUM", "LOW"}
ALLOWED_HOLDING = {"SHORT", "SWING", "MULTI_DAY"}
ALLOWED_THESIS_CHANGE = {"UNCHANGED", "STRENGTHENED", "WEAKENED", "REVERSED"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _flow_alignment_for_intent(intent: str, features: Dict[str, Any], onchain: Dict[str, Any]) -> Tuple[str, bool]:
    flow_data_available = bool(
        features.get("flow_data_available")
        or onchain.get("flow_data_available")
    )
    if not flow_data_available:
        return "UNAVAILABLE", False

    composite_semantic = str(
        features.get("flow_composite_semantic")
        or onchain.get("flow_composite_semantic")
        or ""
    ).upper()
    if intent == "GRID_NEUTRAL":
        if composite_semantic in {"LONG_SUPPORT", "SHORT_SUPPORT"}:
            return "CONFLICT", False
        if composite_semantic in {"MIXED", "NEUTRAL"}:
            return "NEUTRAL", False
        return "UNAVAILABLE", False
    if composite_semantic == "LONG_SUPPORT":
        return ("SUPPORT", True) if intent == "LONG" else ("CONFLICT", False)
    if composite_semantic == "SHORT_SUPPORT":
        return ("SUPPORT", True) if intent == "SHORT" else ("CONFLICT", False)
    if composite_semantic == "MIXED":
        return "NEUTRAL", False
    if composite_semantic == "NEUTRAL":
        return "NEUTRAL", False

    token_flow = _safe_float(onchain.get("token_net_flow"))
    stablecoin_flow = _safe_float(onchain.get("stablecoin_net_flow"))
    if intent == "LONG":
        if token_flow > 0 or stablecoin_flow > 0:
            return "SUPPORT", True
        if token_flow < 0 or stablecoin_flow < 0:
            return "CONFLICT", False
        return "NEUTRAL", False

    if token_flow < 0 or stablecoin_flow < 0:
        return "SUPPORT", True
    if token_flow > 0 or stablecoin_flow > 0:
        return "CONFLICT", False
    return "NEUTRAL", False


def _find_previous_research_output(symbol: str, cycle_id: str) -> Optional[Dict[str, Any]]:
    records = db.get_data("trade_decision_records", [])
    if not isinstance(records, list):
        return None
    for record in records:
        if str(record.get("symbol")) != str(symbol):
            continue
        if str(record.get("cycleId")) == str(cycle_id):
            continue
        research = record.get("researchOutput")
        if isinstance(research, dict) and research:
            return research
    return None


def _strategy_family_for_intent(intent: str) -> str:
    return "GRID" if intent == "GRID_NEUTRAL" else "DIRECTIONAL"


def _build_onchain_derivatives_context(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    onchain = snapshot.get("onchain_snapshot", {}) or {}
    market = snapshot.get("market_snapshot", {}) or {}

    token_flow = _safe_float(onchain.get("token_net_flow"))
    stablecoin_flow = _safe_float(onchain.get("stablecoin_net_flow"))
    token_semantic = str(onchain.get("token_flow_semantic") or "UNAVAILABLE")
    stable_semantic = str(onchain.get("stablecoin_flow_semantic") or "UNAVAILABLE")
    composite_semantic = str(onchain.get("flow_composite_semantic") or "UNAVAILABLE")
    short_liq_ratio = _safe_float(onchain.get("liquidation_short_to_volume_4h"))
    long_liq_ratio = _safe_float(onchain.get("liquidation_long_to_volume_4h"))
    funding_zscore = _safe_float(market.get("funding_zscore"))
    oi_change = _safe_float(market.get("delta_oi_24h_percent"))

    onchain_bias = "NEUTRAL"
    if composite_semantic == "LONG_SUPPORT":
        onchain_bias = "LONG_SUPPORT"
    elif composite_semantic == "SHORT_SUPPORT":
        onchain_bias = "SHORT_SUPPORT"
    elif composite_semantic == "MIXED":
        onchain_bias = "MIXED_FLOW"
    elif stable_semantic == "BUYING_POWER":
        onchain_bias = "BUYING_POWER"
    elif stable_semantic == "CAPITAL_WITHDRAWAL":
        onchain_bias = "CAPITAL_WITHDRAWAL"

    derivatives_bias = "NEUTRAL"
    if funding_zscore <= -1.5 and short_liq_ratio >= long_liq_ratio:
        derivatives_bias = "SHORT_CROWDING"
    elif funding_zscore >= 1.5 and long_liq_ratio >= short_liq_ratio:
        derivatives_bias = "LONG_CROWDING"
    elif short_liq_ratio > long_liq_ratio:
        derivatives_bias = "SHORT_SQUEEZE_RISK"
    elif long_liq_ratio > short_liq_ratio:
        derivatives_bias = "LONG_FLUSH_RISK"

    context_summary = (
        f"onchain={onchain_bias}, derivatives={derivatives_bias}, "
        f"token_flow={round(token_flow, 2)}[{token_semantic}], "
        f"stablecoin_flow={round(stablecoin_flow, 2)}[{stable_semantic}], "
        f"funding_z={round(funding_zscore, 2)}, oi_change={round(oi_change, 4)}, "
        f"short_liq_ratio={round(short_liq_ratio, 4)}, long_liq_ratio={round(long_liq_ratio, 4)}"
    )

    return {
        "onchain_context": {
            "token_net_flow": token_flow,
            "stablecoin_net_flow": stablecoin_flow,
            "token_flow_semantic": token_semantic,
            "stablecoin_flow_semantic": stable_semantic,
            "flow_composite_semantic": composite_semantic,
            "bias": onchain_bias,
        },
        "derivatives_context": {
            "funding_zscore": funding_zscore,
            "delta_oi_24h_percent": oi_change,
            "liquidation_short_to_volume_4h": short_liq_ratio,
            "liquidation_long_to_volume_4h": long_liq_ratio,
            "bias": derivatives_bias,
        },
        "context_summary": context_summary,
    }


def _fallback_candidate_structure(approved_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    long_sources = [str(c.get("trigger_source") or "") for c in approved_candidates if c.get("decision_intent") == "LONG" and c.get("trigger_source")]
    short_sources = [str(c.get("trigger_source") or "") for c in approved_candidates if c.get("decision_intent") == "SHORT" and c.get("trigger_source")]
    has_long = bool(long_sources)
    has_short = bool(short_sources)
    if has_long and has_short:
        overall_state = "directional_conflict"
    elif len(long_sources) >= 2 or len(short_sources) >= 2:
        overall_state = "same_direction_resonance"
    elif has_long or has_short:
        overall_state = "single_signal"
    else:
        overall_state = "no_candidate"
    return {
        "overall_state": overall_state,
        "has_directional_conflict": has_long and has_short,
        "long_count": len(long_sources),
        "short_count": len(short_sources),
        "resonance_groups": {"LONG": long_sources, "SHORT": short_sources},
        "approved_groups": {"LONG": long_sources, "SHORT": short_sources},
        "approved_resonance_strength": max(len(long_sources), len(short_sources), 0),
    }


def _deterministic_research_output(
    snapshot: Dict[str, Any],
    candidate_batch: Dict[str, Any],
    rule_evaluation: Dict[str, Any],
    previous_research: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    approved_candidates = rule_evaluation.get("approved_candidates", []) or []
    if not rule_evaluation.get("passed") or not approved_candidates:
        return None

    features = snapshot.get("decision_ready_features", {}) or {}
    position_snapshot = snapshot.get("position_snapshot", {}) or {}
    market = snapshot.get("market_snapshot", {}) or {}
    macro_snapshot = snapshot.get("macro_snapshot", {}) or {}
    onchain_snapshot = snapshot.get("onchain_snapshot", {}) or {}
    candidate_structure = rule_evaluation.get("candidate_structure", {}) or _fallback_candidate_structure(approved_candidates)

    macro_permission = features.get("macro_permission", "ALLOW_BOTH")
    macro_mode = features.get("macro_mode", macro_snapshot.get("macro_mode", "MIXED"))
    macro_horizon = features.get("macro_horizon", macro_snapshot.get("macro_horizon", "INTRADAY"))
    regime_1d = features.get("regime_1d", "CHOP")
    position_side = position_snapshot.get("position_side", "NONE")

    long_candidates = [c for c in approved_candidates if c.get("decision_intent") == "LONG"]
    short_candidates = [c for c in approved_candidates if c.get("decision_intent") == "SHORT"]
    grid_candidates = [c for c in approved_candidates if c.get("decision_intent") == "GRID_NEUTRAL"]
    technical_confirmation = "STRONG" if _safe_float(market.get("adx_14"), 0.0) >= 25 else "WEAK"

    def _scenario_for_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
        intent = candidate["decision_intent"]
        flow_alignment, flow_support = _flow_alignment_for_intent(intent, features, onchain_snapshot)
        flow_data_available = flow_alignment != "UNAVAILABLE"
        breakdown = {
            "rrr_component": 0.0,
            "macro_component": 0.0,
            "technical_component": 0.0,
            "flow_component": 0.0,
            "event_component": 0.0,
        }

        if intent == "GRID_NEUTRAL":
            macro_alignment = "CONFLICT" if macro_mode == "EVENT_DRIVEN" else "NEUTRAL"
        elif macro_permission == "ALLOW_SHORT" and intent == "LONG":
            macro_alignment = "CONFLICT"
        elif macro_permission == "ALLOW_LONG" and intent == "SHORT":
            macro_alignment = "CONFLICT"
        elif macro_permission == "ALLOW_BOTH":
            macro_alignment = "NEUTRAL"
        elif macro_permission == "ALLOW_NEITHER":
            macro_alignment = "CONFLICT"
        else:
            macro_alignment = "SUPPORT"
        if intent == "GRID_NEUTRAL":
            scenario_label = "range_rotation"
        elif macro_alignment == "CONFLICT":
            scenario_label = "countertrend_rebound" if intent == "LONG" else "trend_breakdown"
        elif technical_confirmation == "STRONG" and flow_support:
            scenario_label = "trend_following"
        else:
            scenario_label = "range_rotation"

        score = 0.0
        support_reasons: List[str] = []
        risk_reasons: List[str] = []
        rrr = _safe_float(candidate.get("rrr"), 0.0)
        if intent == "GRID_NEUTRAL":
            breakdown["rrr_component"] = 0.10
            score += breakdown["rrr_component"]
            support_reasons.append("grid_inventory_rotation")
        elif rrr >= 2.2:
            breakdown["rrr_component"] = 0.20
            score += breakdown["rrr_component"]
            support_reasons.append("strong_rrr")
        elif rrr >= 1.8:
            breakdown["rrr_component"] = 0.10
            score += breakdown["rrr_component"]
            support_reasons.append("acceptable_rrr")
        else:
            breakdown["rrr_component"] = -0.25
            score += breakdown["rrr_component"]
            risk_reasons.append("low_rrr")

        if macro_alignment == "SUPPORT":
            breakdown["macro_component"] = 0.35
            score += breakdown["macro_component"]
            support_reasons.append("macro_support")
        elif macro_alignment == "NEUTRAL":
            breakdown["macro_component"] = 0.10
            score += breakdown["macro_component"]
        else:
            breakdown["macro_component"] = -0.35
            score += breakdown["macro_component"]
            risk_reasons.append("macro_conflict")

        if intent == "GRID_NEUTRAL":
            breakdown["technical_component"] = 0.10 if _safe_float(features.get("p_flat_8h")) >= 0.55 else -0.10
            score += breakdown["technical_component"]
            if breakdown["technical_component"] > 0:
                support_reasons.append("range_regime_confirmed")
            else:
                risk_reasons.append("range_regime_weakening")
        elif technical_confirmation == "STRONG":
            breakdown["technical_component"] = 0.20
            score += breakdown["technical_component"]
            support_reasons.append("technical_confirmation")
        else:
            breakdown["technical_component"] = -0.05
            score += breakdown["technical_component"]
            risk_reasons.append("weak_technical_confirmation")

        if flow_support:
            breakdown["flow_component"] = 0.20
            score += breakdown["flow_component"]
            support_reasons.append("flow_support")
        elif flow_alignment == "CONFLICT":
            breakdown["flow_component"] = -0.10
            score += breakdown["flow_component"]
            risk_reasons.append("flow_conflict")
        elif flow_alignment == "NEUTRAL":
            support_reasons.append("flow_neutral")
        else:
            risk_reasons.append("flow_unavailable")

        if macro_mode == "EVENT_DRIVEN":
            breakdown["event_component"] = -0.10
            score += breakdown["event_component"]
            risk_reasons.append("event_driven_noise")

        return {
            "trigger_source": candidate.get("trigger_source"),
            "intent": intent,
            "scenario_label": scenario_label,
            "macro_alignment": macro_alignment,
            "technical_confirmation": technical_confirmation,
            "flow_alignment": flow_alignment,
            "flow_data_available": flow_data_available,
            "support_reasons": support_reasons,
            "risk_reasons": risk_reasons,
            "score_breakdown": {k: round(v, 2) for k, v in breakdown.items()},
            "score": round(score, 2),
        }

    scenario_candidates = [_scenario_for_candidate(candidate) for candidate in approved_candidates]
    scenario_candidates.sort(key=lambda item: item["score"], reverse=True)

    selected_scenario = scenario_candidates[0]
    selected = next(
        (candidate for candidate in approved_candidates if candidate.get("trigger_source") == selected_scenario.get("trigger_source")),
        approved_candidates[0],
    )

    conflict_state = "none"
    if long_candidates and short_candidates:
        conflict_state = "candidate_conflict"

    selected_intent = selected["decision_intent"]
    if macro_permission == "ALLOW_NEITHER":
        selected_intent = "NO_TRADE"
    elif selected_intent == "GRID_NEUTRAL" and macro_mode == "EVENT_DRIVEN":
        selected_intent = "WAIT_FOR_CONFIRMATION"
    elif conflict_state == "candidate_conflict" and macro_permission == "ALLOW_BOTH":
        selected_intent = "WAIT_FOR_CONFIRMATION"
    elif conflict_state == "candidate_conflict" and macro_permission == "ALLOW_SHORT":
        selected_intent = "SHORT"
    elif conflict_state == "candidate_conflict" and macro_permission == "ALLOW_LONG":
        selected_intent = "LONG"

    macro_alignment = selected_scenario["macro_alignment"]
    flow_alignment = selected_scenario["flow_alignment"]
    flow_data_available = bool(selected_scenario.get("flow_data_available"))
    scenario_label = selected_scenario["scenario_label"]
    if selected_intent in {"NO_TRADE", "WAIT_FOR_CONFIRMATION"}:
        scenario_label = "wait_no_trade"

    if conflict_state == "none" and macro_alignment == "CONFLICT" and flow_alignment == "SUPPORT":
        conflict_state = "macro_vs_onchain"
    elif conflict_state == "none" and macro_alignment == "CONFLICT" and technical_confirmation == "STRONG":
        conflict_state = "macro_vs_technical"

    if selected_intent == "GRID_NEUTRAL":
        holding_horizon = "SHORT"
    elif macro_mode == "EVENT_DRIVEN":
        holding_horizon = "SHORT"
    elif scenario_label == "trend_following" and macro_alignment != "CONFLICT":
        holding_horizon = "SWING"
    else:
        holding_horizon = "SHORT"

    scenario_score = selected_scenario["score"]
    thesis_strength = "HIGH"
    if scenario_score < 0.45 or macro_alignment == "CONFLICT" or technical_confirmation == "WEAK":
        thesis_strength = "MEDIUM"
    if scenario_score < 0.10 or (macro_alignment == "CONFLICT" and flow_alignment == "CONFLICT"):
        thesis_strength = "LOW"

    risk_note = ""
    if selected_intent == "GRID_NEUTRAL":
        risk_note = "grid valid only while range and event conditions remain stable"
    elif macro_alignment == "CONFLICT":
        risk_note = "macro headwind limits size and duration"
    elif position_side != "NONE":
        risk_note = "existing position requires conservative sizing"
    elif macro_mode == "EVENT_DRIVEN":
        risk_note = "event risk requires shorter holding horizon"

    previous_intent = (previous_research or {}).get("selected_intent")
    previous_strength = (previous_research or {}).get("thesis_strength")
    thesis_change = "UNCHANGED"
    change_reason = "first deterministic research output"
    if previous_research:
        if previous_intent and selected_intent != previous_intent:
            thesis_change = "REVERSED"
            change_reason = f"selected intent changed from {previous_intent} to {selected_intent}"
        elif previous_strength and previous_strength != thesis_strength:
            order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
            thesis_change = "STRENGTHENED" if order.get(thesis_strength, 0) > order.get(previous_strength, 0) else "WEAKENED"
            change_reason = f"thesis strength changed from {previous_strength} to {thesis_strength}"
        else:
            change_reason = "core thesis remains materially consistent with previous cycle"

    flow_support = flow_alignment == "SUPPORT"
    context = _build_onchain_derivatives_context(snapshot)
    summary = (
        f"{selected.get('trigger_source')} selected with {scenario_label}; "
        f"macro={macro_mode}, regime={regime_1d}, flow_alignment={flow_alignment}."
    )
    if selected_intent == "WAIT_FOR_CONFIRMATION":
        summary = "approved candidates remain conflicted; wait for confirmation before allocating risk."
    elif selected_intent == "NO_TRADE":
        summary = "macro permission denies current candidate set; no trade is allowed."
    elif selected_intent == "GRID_NEUTRAL":
        summary = "range regime remains intact; prefer neutral grid rotation over directional breakout trades."

    return {
        "symbol": snapshot["symbol"],
        "cycleId": snapshot["cycleId"],
        "strategy_family": _strategy_family_for_intent(selected_intent),
        "selected_intent": selected_intent,
        "selected_trigger_sources": [selected.get("trigger_source")],
        "macro_direction_bias": "LONG_BIAS" if macro_permission == "ALLOW_LONG" else "SHORT_BIAS" if macro_permission == "ALLOW_SHORT" else "NEUTRAL",
        "macro_horizon": macro_horizon,
        "macro_mode": macro_mode,
        "macro_permission": macro_permission,
        "scenario_label": scenario_label,
        "conflict_state": conflict_state,
        "primary_driver": "technical_confirmation" if technical_confirmation == "STRONG" else "macro_filter",
        "secondary_driver": "flow_support" if flow_support else "flow_unavailable" if not flow_data_available else "macro_headwind",
        "macro_alignment": macro_alignment,
        "technical_confirmation": technical_confirmation,
        "flow_alignment": flow_alignment,
        "flow_data_available": flow_data_available,
        "thesis_strength": thesis_strength,
        "holding_horizon": holding_horizon,
        "thesis_change": thesis_change,
        "change_reason": change_reason,
        "risk_note": risk_note,
        "summary": summary,
        "scenario_candidates": scenario_candidates[:4],
        "candidate_structure": candidate_structure,
        "onchain_context": context["onchain_context"],
        "derivatives_context": context["derivatives_context"],
        "context_summary": context["context_summary"],
        "provenance": {
            "generation_mode": "deterministic_only",
            "llm_enabled": os.getenv("ENABLE_RESEARCH_LLM", "").strip() == "1",
            "llm_attempted": False,
            "llm_applied": False,
            "llm_override_fields": [],
        },
    }


def _llm_refine_research_output(
    snapshot: Dict[str, Any],
    candidate_batch: Dict[str, Any],
    rule_evaluation: Dict[str, Any],
    deterministic_output: Dict[str, Any],
    previous_research: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    approved_candidates = rule_evaluation.get("approved_candidates", []) or []
    allowed_sources = [c.get("trigger_source") for c in approved_candidates if c.get("trigger_source")]
    allowed_intents = sorted({c.get("decision_intent") for c in approved_candidates if c.get("decision_intent")})
    payload = {
        "snapshot": {
            "symbol": snapshot.get("symbol"),
            "market_snapshot": snapshot.get("market_snapshot", {}),
            "onchain_snapshot": snapshot.get("onchain_snapshot", {}),
            "macro_snapshot": snapshot.get("macro_snapshot", {}),
            "position_snapshot": snapshot.get("position_snapshot", {}),
            "decision_ready_features": snapshot.get("decision_ready_features", {}),
        },
        "approved_candidates": approved_candidates,
        "deterministic_output": deterministic_output,
        "previous_research": previous_research,
    }
    few_shot_examples = [
        {
            "case": {
                "macro_permission": "ALLOW_SHORT",
                "approved_candidates": [
                    {"decision_intent": "LONG", "trigger_source": "Blueprint_A1", "rrr": 2.0},
                    {"decision_intent": "SHORT", "trigger_source": "Blueprint_A2", "rrr": 2.1},
                ],
                "note": "macro and candidate directions conflict",
            },
            "expected_output": {
                "selected_intent": "SHORT",
                "selected_trigger_sources": ["Blueprint_A2"],
                "scenario_label": "trend_breakdown",
                "conflict_state": "candidate_conflict",
                "primary_driver": "macro_filter",
                "secondary_driver": "flow_support",
                "macro_alignment": "SUPPORT",
                "technical_confirmation": "WEAK",
                "flow_alignment": "SUPPORT",
                "flow_data_available": True,
                "thesis_strength": "MEDIUM",
                "holding_horizon": "SHORT",
                "thesis_change": "WEAKENED",
                "change_reason": "macro permission restricts long candidate",
                "risk_note": "macro headwind limits size and duration",
                "summary": "Short candidate selected because macro permission restricts longs and downside flow remains valid.",
            },
        },
        {
            "case": {
                "macro_permission": "ALLOW_LONG",
                "approved_candidates": [
                    {"decision_intent": "LONG", "trigger_source": "Blueprint_A1", "rrr": 2.4},
                ],
                "note": "single aligned long candidate",
            },
            "expected_output": {
                "selected_intent": "LONG",
                "selected_trigger_sources": ["Blueprint_A1"],
                "scenario_label": "trend_following",
                "conflict_state": "none",
                "primary_driver": "technical_confirmation",
                "secondary_driver": "flow_support",
                "macro_alignment": "SUPPORT",
                "technical_confirmation": "STRONG",
                "flow_alignment": "SUPPORT",
                "flow_data_available": True,
                "thesis_strength": "HIGH",
                "holding_horizon": "SWING",
                "thesis_change": "STRENGTHENED",
                "change_reason": "macro and setup align with previous thesis",
                "risk_note": "",
                "summary": "Long candidate selected because macro, technical structure, and flow align.",
            },
        },
        {
            "case": {
                "macro_permission": "ALLOW_BOTH",
                "approved_candidates": [
                    {"decision_intent": "LONG", "trigger_source": "Blueprint_A1", "rrr": 2.0},
                    {"decision_intent": "SHORT", "trigger_source": "Blueprint_E2", "rrr": 2.0},
                ],
                "note": "ambiguous macro and balanced candidate conflict",
            },
            "expected_output": {
                "selected_intent": "WAIT_FOR_CONFIRMATION",
                "selected_trigger_sources": ["Blueprint_A1"],
                "scenario_label": "wait_no_trade",
                "conflict_state": "candidate_conflict",
                "primary_driver": "macro_filter",
                "secondary_driver": "flow_unavailable",
                "macro_alignment": "NEUTRAL",
                "technical_confirmation": "WEAK",
                "flow_alignment": "UNAVAILABLE",
                "flow_data_available": False,
                "thesis_strength": "LOW",
                "holding_horizon": "SHORT",
                "thesis_change": "UNCHANGED",
                "change_reason": "conflict remains unresolved",
                "risk_note": "wait for confirmation before allocating risk",
                "summary": "Approved candidates remain conflicted; wait for confirmation before allocating risk.",
            },
        },
    ]
    prompt = (
        "You are a constrained research/thesis agent. "
        "Do not invent new trade directions or trigger sources outside the approved candidates. "
        "Do not produce leverage or position size. "
        "Use fixed reasoning order: macro -> technical -> onchain -> conflict -> continuity -> final output. "
        "If candidates conflict, internally compare at least three scenarios: trend_following, countertrend, wait_no_trade, then return one final structured answer only. "
        "Return only valid JSON with keys: selected_intent, selected_trigger_sources, scenario_label, "
        "conflict_state, primary_driver, secondary_driver, macro_alignment, technical_confirmation, "
        "flow_alignment, flow_data_available, thesis_strength, holding_horizon, thesis_change, change_reason, risk_note, summary.\n\n"
        f"FEW_SHOT_EXAMPLES: {json.dumps(few_shot_examples, ensure_ascii=False)}\n"
        f"ALLOWED_SELECTED_INTENTS: {json.dumps(sorted(set(allowed_intents) | {'NO_TRADE', 'WAIT_FOR_CONFIRMATION'}))}\n"
        f"ALLOWED_TRIGGER_SOURCES: {json.dumps(allowed_sources)}\n"
        f"INPUT: {json.dumps(payload, ensure_ascii=False)}"
    )
    llm_enabled = os.getenv("ENABLE_RESEARCH_LLM", "").strip() == "1"
    result, llm_audit = call_llm_json_with_audit(
        prompt,
        system_prompt="Use fixed reasoning order: macro -> technical -> onchain -> conflict -> continuity -> final output.",
        temperature=0.0,
        enable_env_flag="ENABLE_RESEARCH_LLM",
    )
    if not isinstance(result, dict):
        merged = dict(deterministic_output)
        merged["provenance"] = {
            "generation_mode": "deterministic_only",
            "llm_enabled": llm_enabled,
            "llm_attempted": llm_enabled,
            "llm_applied": False,
            "llm_override_fields": [],
            "llm_audit": llm_audit,
        }
        return merged

    merged = dict(deterministic_output)
    override_fields: List[str] = []
    selected_intent = result.get("selected_intent")
    if isinstance(selected_intent, str) and selected_intent in ALLOWED_SELECTED_INTENTS and (
        selected_intent in allowed_intents or selected_intent in {"NO_TRADE", "WAIT_FOR_CONFIRMATION"}
    ):
        if merged.get("selected_intent") != selected_intent:
            override_fields.append("selected_intent")
        merged["selected_intent"] = selected_intent

    trigger_sources = result.get("selected_trigger_sources")
    if isinstance(trigger_sources, list):
        safe_sources = [s for s in trigger_sources if isinstance(s, str) and s in allowed_sources]
        if safe_sources:
            if merged.get("selected_trigger_sources") != safe_sources:
                override_fields.append("selected_trigger_sources")
            merged["selected_trigger_sources"] = safe_sources

    enum_fields = {
        "macro_direction_bias": ALLOWED_MACRO_BIAS,
        "macro_horizon": ALLOWED_MACRO_HORIZON,
        "macro_mode": ALLOWED_MACRO_MODE,
        "macro_permission": ALLOWED_MACRO_PERMISSION,
        "scenario_label": ALLOWED_SCENARIO_LABELS,
        "conflict_state": ALLOWED_CONFLICT_STATE,
        "macro_alignment": ALLOWED_ALIGNMENT,
        "technical_confirmation": ALLOWED_TECH,
        "flow_alignment": ALLOWED_ALIGNMENT,
        "thesis_strength": ALLOWED_STRENGTH,
        "holding_horizon": ALLOWED_HOLDING,
        "thesis_change": ALLOWED_THESIS_CHANGE,
    }
    for field, allowed in enum_fields.items():
        value = result.get(field)
        if isinstance(value, str) and value in allowed:
            if merged.get(field) != value:
                override_fields.append(field)
            merged[field] = value

    for field in ["primary_driver", "secondary_driver", "change_reason", "risk_note", "summary"]:
        value = result.get(field)
        if isinstance(value, str) and value.strip():
            cleaned = value.strip()
            if merged.get(field) != cleaned:
                override_fields.append(field)
            merged[field] = cleaned

    flow_data_available = result.get("flow_data_available")
    if isinstance(flow_data_available, bool):
        if merged.get("flow_data_available") != flow_data_available:
            override_fields.append("flow_data_available")
        merged["flow_data_available"] = flow_data_available

    merged["provenance"] = {
        "generation_mode": "llm_refined" if override_fields else "llm_noop",
        "llm_enabled": llm_enabled,
        "llm_attempted": llm_enabled,
        "llm_applied": bool(override_fields),
        "llm_override_fields": sorted(set(override_fields)),
        "llm_audit": llm_audit,
    }

    return merged


def build_research_output(
    snapshot: Dict[str, Any],
    candidate_batch: Dict[str, Any],
    rule_evaluation: Dict[str, Any],
    previous_research: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if previous_research is None:
        previous_research = _find_previous_research_output(snapshot.get("symbol"), snapshot.get("cycleId"))
    deterministic = _deterministic_research_output(snapshot, candidate_batch, rule_evaluation, previous_research)
    if deterministic is None:
        return None
    return _llm_refine_research_output(snapshot, candidate_batch, rule_evaluation, deterministic, previous_research)
