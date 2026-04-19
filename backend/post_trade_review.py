import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from db_client import db
from llm_client import call_llm_json


ALLOWED_RESULT_LABELS = {
    "REJECTED_PRE_TRADE",
    "RESEARCH_HOLD",
    "RISK_REJECTED",
    "EXECUTION_FAILED",
    "OPEN_MONITORING",
    "WIN",
    "LOSS",
    "BREAKEVEN",
}
ALLOWED_PRIMARY_CAUSES = {
    "RULE_BLOCK",
    "RESEARCH_CONSERVATIVE",
    "RISK_REVIEW_REJECTED",
    "EXECUTION_FAILURE",
    "TRADE_STILL_OPEN",
    "THESIS_CONFIRMED",
    "RESEARCH_WEAK_THESIS",
    "CANDIDATE_OR_MARKET_MISS",
    "RISK_REVIEW_TOO_LOOSE",
    "EXECUTION_SLIPPAGE_OR_SYNC",
}
ALLOWED_IMPROVEMENT_TARGETS = {"data", "candidate", "rule", "research", "risk", "execution"}


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def replay_builder(record: Dict[str, Any], matched_trade: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "decisionId": record.get("decisionId"),
        "symbol": record.get("symbol"),
        "created_at": record.get("created_at"),
        "snapshot": record.get("snapshot", {}),
        "candidate": record.get("candidate", {}),
        "ruleEvaluation": record.get("ruleEvaluation", {}),
        "researchOutput": record.get("researchOutput"),
        "riskReview": record.get("riskReview", {}),
        "execution": record.get("execution", {}),
        "matched_trade": matched_trade,
    }


def _build_traceability_context(replay_context: Dict[str, Any]) -> Dict[str, Any]:
    candidate = replay_context.get("candidate", {}) or {}
    rule_evaluation = replay_context.get("ruleEvaluation", {}) or {}
    research_output = replay_context.get("researchOutput") or {}
    risk_review = replay_context.get("riskReview", {}) or {}

    proposals = candidate.get("candidate_proposals", []) or []
    approved_candidates = rule_evaluation.get("approved_candidates", []) or []
    selected_trigger_sources = research_output.get("selected_trigger_sources", []) or []
    approved_trigger_sources = [str(item.get("trigger_source") or "") for item in approved_candidates if item.get("trigger_source")]
    proposed_trigger_sources = [str(item.get("trigger_source") or "") for item in proposals if item.get("trigger_source")]

    return {
        "candidate_structure": (
            research_output.get("candidate_structure")
            or rule_evaluation.get("candidate_structure")
            or {}
        ),
        "proposed_trigger_sources": proposed_trigger_sources,
        "approved_trigger_sources": approved_trigger_sources,
        "selected_trigger_sources": selected_trigger_sources,
        "selected_intent": research_output.get("selected_intent"),
        "thesis_strength": research_output.get("thesis_strength"),
        "conflict_state": research_output.get("conflict_state"),
        "risk_review_note": risk_review.get("review_note"),
        "execution_action": risk_review.get("execution_action"),
    }


def attribution_rules(replay_context: Dict[str, Any]) -> Dict[str, Any]:
    rule_evaluation = replay_context.get("ruleEvaluation", {}) or {}
    research_output = replay_context.get("researchOutput") or {}
    risk_review = replay_context.get("riskReview", {}) or {}
    execution = replay_context.get("execution", {}) or {}
    matched_trade = replay_context.get("matched_trade")

    if not rule_evaluation.get("passed"):
        return {
            "result_label": "REJECTED_PRE_TRADE",
            "primary_cause": "RULE_BLOCK",
            "layer_attribution": {
                "data": 0.0,
                "candidate": 0.1,
                "rule": 0.9,
                "research": 0.0,
                "risk": 0.0,
                "execution": 0.0,
            },
            "improvement_targets": ["rule"] if rule_evaluation.get("reason_codes") else [],
            "improvement_note": "candidate rejected during pre-trade rule evaluation",
        }

    if research_output and research_output.get("selected_intent") in {"NO_TRADE", "WAIT_FOR_CONFIRMATION"}:
        return {
            "result_label": "RESEARCH_HOLD",
            "primary_cause": "RESEARCH_CONSERVATIVE",
            "layer_attribution": {
                "data": 0.0,
                "candidate": 0.0,
                "rule": 0.1,
                "research": 0.9,
                "risk": 0.0,
                "execution": 0.0,
            },
            "improvement_targets": [],
            "improvement_note": "research intentionally withheld risk deployment",
        }

    if not risk_review.get("approved"):
        return {
            "result_label": "RISK_REJECTED",
            "primary_cause": "RISK_REVIEW_REJECTED",
            "layer_attribution": {
                "data": 0.0,
                "candidate": 0.0,
                "rule": 0.2,
                "research": 0.2,
                "risk": 0.6,
                "execution": 0.0,
            },
            "improvement_targets": [],
            "improvement_note": "risk review withheld final approval",
        }

    order_status = execution.get("order_status")
    if order_status in {"FAILED"}:
        return {
            "result_label": "EXECUTION_FAILED",
            "primary_cause": "EXECUTION_FAILURE",
            "layer_attribution": {
                "data": 0.0,
                "candidate": 0.0,
                "rule": 0.0,
                "research": 0.0,
                "risk": 0.0,
                "execution": 1.0,
            },
            "improvement_targets": ["execution"],
            "improvement_note": execution.get("failure_reason", "execution failed"),
        }

    if matched_trade is None:
        return {
            "result_label": "OPEN_MONITORING",
            "primary_cause": "TRADE_STILL_OPEN",
            "layer_attribution": {
                "data": 0.0,
                "candidate": 0.0,
                "rule": 0.0,
                "research": 0.0,
                "risk": 0.0,
                "execution": 0.0,
            },
            "improvement_targets": [],
            "improvement_note": "execution submitted or simulated; no closed trade matched yet",
        }

    pnl = float(matched_trade.get("pnl", 0.0))
    pnl_pct = float(matched_trade.get("pnlPercent", 0.0))
    thesis_strength = (research_output or {}).get("thesis_strength", "MEDIUM")
    result_label = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"

    if pnl < 0:
        if thesis_strength == "LOW":
            primary_cause = "RESEARCH_WEAK_THESIS"
            layer_attribution = {"data": 0.1, "candidate": 0.15, "rule": 0.1, "research": 0.45, "risk": 0.15, "execution": 0.05}
            improvement_targets = ["research", "candidate"]
        else:
            primary_cause = "CANDIDATE_OR_MARKET_MISS"
            layer_attribution = {"data": 0.1, "candidate": 0.35, "rule": 0.1, "research": 0.2, "risk": 0.15, "execution": 0.1}
            improvement_targets = ["candidate", "research"]
        improvement_note = "closed trade finished negative; review thesis quality and setup quality"
    else:
        primary_cause = "THESIS_CONFIRMED"
        layer_attribution = {"data": 0.1, "candidate": 0.25, "rule": 0.1, "research": 0.25, "risk": 0.15, "execution": 0.15}
        improvement_targets = []
        improvement_note = "closed trade aligned with approved thesis and exited positive"

    return {
        "result_label": result_label,
        "primary_cause": primary_cause,
        "layer_attribution": layer_attribution,
        "improvement_targets": improvement_targets,
        "improvement_note": improvement_note,
        "pnl": round(pnl, 2),
        "pnl_percent": round(pnl_pct, 2),
    }


def feedback_generator(evaluation: Dict[str, Any]) -> List[Dict[str, Any]]:
    packets: List[Dict[str, Any]] = []
    for target in evaluation.get("improvement_targets", []) or []:
        if target == "data":
            packets.append({
                "target_layer": "data",
                "packet_type": "FEATURE_GAP_REVIEW",
                "message": "review missing or coarse upstream features and event tags",
            })
        elif target == "candidate":
            packets.append({
                "target_layer": "candidate",
                "packet_type": "BLUEPRINT_REVIEW",
                "message": "review setup quality, invalidation template, and entry/SL/TP formulation",
            })
        elif target == "rule":
            packets.append({
                "target_layer": "rule",
                "packet_type": "RULE_TUNING_REVIEW",
                "message": "review pre-trade or in-position threshold sensitivity",
            })
        elif target == "research":
            packets.append({
                "target_layer": "research",
                "packet_type": "PROMPT_AND_CONFLICT_REVIEW",
                "message": "review prompt constraints, conflict handling, and no-trade examples",
            })
        elif target == "execution":
            packets.append({
                "target_layer": "execution",
                "packet_type": "EXECUTION_RELIABILITY_REVIEW",
                "message": "review adapter errors, retries, sizing translation, and sync consistency",
            })
    return packets


def _needs_llm_review(replay_context: Dict[str, Any], base_evaluation: Dict[str, Any]) -> bool:
    result_label = base_evaluation.get("result_label")
    if result_label not in {"LOSS", "BREAKEVEN", "EXECUTION_FAILED"}:
        return False

    research_output = replay_context.get("researchOutput") or {}
    rule_evaluation = replay_context.get("ruleEvaluation") or {}
    execution = replay_context.get("execution") or {}

    if result_label == "EXECUTION_FAILED":
        return True
    if research_output.get("conflict_state") not in {None, "", "none"}:
        return True
    if len(rule_evaluation.get("approved_candidates", []) or []) > 1:
        return True
    if execution.get("protection_status") in {"MISSING", "FAILED"}:
        return True
    return False


def _llm_refine_evaluation(replay_context: Dict[str, Any], base_evaluation: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "snapshot": (replay_context.get("snapshot") or {}),
        "candidate": (replay_context.get("candidate") or {}),
        "ruleEvaluation": (replay_context.get("ruleEvaluation") or {}),
        "researchOutput": (replay_context.get("researchOutput") or {}),
        "riskReview": (replay_context.get("riskReview") or {}),
        "execution": (replay_context.get("execution") or {}),
        "matched_trade": replay_context.get("matched_trade"),
        "base_evaluation": base_evaluation,
    }
    prompt = (
        "You are a constrained post-trade evaluation agent.\n"
        "Use fixed reasoning order: replay facts -> rule path -> research path -> risk path -> execution path -> final attribution.\n"
        "For complex losses or execution failures, internally compare multiple attribution paths before returning one final answer.\n"
        "Do not output prose outside JSON. Return only keys: result_label, primary_cause, improvement_targets, improvement_note.\n"
        f"ALLOWED_RESULT_LABELS: {json.dumps(sorted(ALLOWED_RESULT_LABELS))}\n"
        f"ALLOWED_PRIMARY_CAUSES: {json.dumps(sorted(ALLOWED_PRIMARY_CAUSES))}\n"
        f"ALLOWED_IMPROVEMENT_TARGETS: {json.dumps(sorted(ALLOWED_IMPROVEMENT_TARGETS))}\n"
        f"INPUT: {json.dumps(payload, ensure_ascii=False)}"
    )
    result = call_llm_json(
        prompt,
        system_prompt="Use fixed reasoning order: replay facts -> rule -> research -> risk -> execution -> final attribution. Return JSON only.",
        temperature=0.0,
        enable_env_flag="ENABLE_EVALUATION_LLM",
    )
    if not isinstance(result, dict):
        return base_evaluation

    merged = copy.deepcopy(base_evaluation)
    result_label = result.get("result_label")
    if isinstance(result_label, str) and result_label in ALLOWED_RESULT_LABELS:
        merged["result_label"] = result_label

    primary_cause = result.get("primary_cause")
    if isinstance(primary_cause, str) and primary_cause in ALLOWED_PRIMARY_CAUSES:
        merged["primary_cause"] = primary_cause

    targets = result.get("improvement_targets")
    if isinstance(targets, list):
        safe_targets = [t for t in targets if isinstance(t, str) and t in ALLOWED_IMPROVEMENT_TARGETS]
        merged["improvement_targets"] = list(dict.fromkeys(safe_targets))

    improvement_note = result.get("improvement_note")
    if isinstance(improvement_note, str) and improvement_note.strip():
        merged["improvement_note"] = improvement_note.strip()

    return merged


def evaluation_agent(replay_context: Dict[str, Any], base_evaluation: Dict[str, Any]) -> Dict[str, Any]:
    matched_trade = replay_context.get("matched_trade")
    evaluation = copy.deepcopy(base_evaluation)
    if _needs_llm_review(replay_context, evaluation):
        evaluation = _llm_refine_evaluation(replay_context, evaluation)
    if matched_trade:
        evaluation["matched_trade_id"] = matched_trade.get("id")
        evaluation["matched_trade_exit_time"] = matched_trade.get("exitTime")
    evaluation["traceability"] = _build_traceability_context(replay_context)
    evaluation["feedback_packets"] = feedback_generator(evaluation)
    evaluation["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return evaluation


def _normalize_symbol(text: Any) -> str:
    return str(text or "").replace("-USDT", "").replace("-SWAP", "").upper()


def _normalize_side(text: Any) -> str:
    raw = str(text or "").lower()
    if raw in {"long", "buy"}:
        return "LONG"
    if raw in {"short", "sell"}:
        return "SHORT"
    return raw.upper()


def _match_closed_trade(record: Dict[str, Any], trade_history: List[Dict[str, Any]], used_trade_ids: Set[str]) -> Optional[Dict[str, Any]]:
    record_dt = _parse_dt(record.get("created_at"))
    if record_dt is None:
        return None

    symbol = _normalize_symbol(record.get("symbol"))
    final_intent = _normalize_side((record.get("riskReview") or {}).get("final_intent"))
    execution = record.get("execution") or {}
    if execution.get("order_status") not in {"SUBMITTED", "FILLED", "SKIPPED"}:
        return None
    if (record.get("riskReview") or {}).get("approved") is not True:
        return None

    candidates: List[Dict[str, Any]] = []
    for trade in trade_history:
        trade_id = str(trade.get("id", ""))
        if not trade_id or trade_id in used_trade_ids:
            continue
        if _normalize_symbol(trade.get("symbol")) != symbol:
            continue
        if final_intent and _normalize_side(trade.get("type")) != final_intent:
            continue
        exit_dt = _parse_dt(trade.get("exitTime"))
        if exit_dt is None or exit_dt < record_dt:
            continue
        candidates.append(trade)

    if not candidates:
        return None

    candidates.sort(key=lambda item: _parse_dt(item.get("exitTime")) or datetime.max.replace(tzinfo=timezone.utc))
    chosen = candidates[0]
    used_trade_ids.add(str(chosen.get("id")))
    return chosen


def run_post_trade_review() -> Dict[str, Any]:
    records = db.get_data("trade_decision_records", [])
    if not isinstance(records, list) or not records:
        return {"evaluated_count": 0, "record_count": 0}

    trade_history = db.get_data("trade_history", [])
    if not isinstance(trade_history, list):
        trade_history = []

    ordered_records = sorted(records, key=lambda item: _parse_dt(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc))
    updated_records: List[Dict[str, Any]] = []
    used_trade_ids: Set[str] = set()
    evaluated_count = 0

    for record in ordered_records:
        matched_trade = _match_closed_trade(record, trade_history, used_trade_ids)
        replay_context = replay_builder(record, matched_trade)
        base_evaluation = attribution_rules(replay_context)
        new_evaluation = evaluation_agent(replay_context, base_evaluation)

        current_evaluation = record.get("evaluation")
        if current_evaluation != new_evaluation:
            record = copy.deepcopy(record)
            record["evaluation"] = new_evaluation
            record["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            evaluated_count += 1
        updated_records.append(record)

    updated_records.sort(key=lambda item: _parse_dt(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    db.save_data("trade_decision_records", updated_records)
    if updated_records:
        db.save_data("latest_trade_decision_record", updated_records[0])

    return {
        "evaluated_count": evaluated_count,
        "record_count": len(updated_records),
    }
