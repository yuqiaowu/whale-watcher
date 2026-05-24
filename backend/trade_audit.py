import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional


AUDIT_COLLECTION = "trade_audit_ledger"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _execution_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    execution = _safe_dict(record.get("execution"))
    keys = [
        "execution_action",
        "order_status",
        "sync_status",
        "requested_size_usd",
        "requested_leverage",
        "entry_type",
        "proposed_entry_price",
        "proposed_sl_price",
        "proposed_tp_price",
        "avg_fill_price",
        "avg_exit_price",
        "filled_size",
        "exchange_order_id",
        "exchange_algo_id",
        "client_order_id",
        "order_tag",
        "executed_at",
        "closed_at",
        "closed_trade_id",
        "realized_pnl",
        "realized_pnl_percent",
        "runtime_action",
        "runtime_reason",
        "close_reason",
        "close_reason_source",
        "failure_reason",
        "protection_status",
        "filled_stop_loss",
        "filled_take_profit",
        "superseded_by_decision_id",
    ]
    return {key: deepcopy(execution.get(key)) for key in keys if key in execution}


def _risk_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    risk = _safe_dict(record.get("riskReview"))
    candidate = _safe_dict(risk.get("approved_candidate"))
    return {
        "approved": risk.get("approved"),
        "final_intent": risk.get("final_intent"),
        "strategy_family": risk.get("strategy_family"),
        "approved_risk_fraction": risk.get("approved_risk_fraction"),
        "approved_position_size_usd": risk.get("approved_position_size_usd"),
        "leverage": risk.get("leverage"),
        "max_holding_bars": risk.get("max_holding_bars"),
        "execution_action": risk.get("execution_action"),
        "review_note": risk.get("review_note"),
        "approved_candidate": {
            key: deepcopy(candidate.get(key))
            for key in [
                "strategy_family",
                "decision_intent",
                "trigger_source",
                "rationale",
                "entry_type",
                "proposed_entry_price",
                "proposed_sl_price",
                "proposed_tp_price",
                "invalidation_basis",
                "invalidation_conditions",
                "reference_values",
            ]
            if key in candidate
        },
    }


def _model_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    model = _safe_dict(record.get("modelDecision"))
    return {
        key: deepcopy(model.get(key))
        for key in [
            "action",
            "direction",
            "confidence",
            "risk_level",
            "horizon",
            "setup_type",
            "summary",
            "reason_codes",
            "invalid_if",
            "invalidation_rules",
        ]
        if key in model
    }


def _research_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    research = _safe_dict(record.get("researchOutput"))
    return {
        key: deepcopy(research.get(key))
        for key in [
            "selected_intent",
            "selected_trigger_sources",
            "scenario_label",
            "thesis_strength",
            "holding_horizon",
            "thesis_change",
            "summary",
            "provenance",
        ]
        if key in research
    }


def build_trade_audit_event(
    event_type: str,
    record: Dict[str, Any],
    *,
    source: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = deepcopy(payload or {})
    event_at = _iso_now()
    identity = {
        "event_type": event_type,
        "source": source,
        "decisionId": record.get("decisionId"),
        "cycleId": record.get("cycleId"),
        "symbol": record.get("symbol"),
        "positionState": record.get("positionState"),
        "execution": _execution_summary(record),
        "payload": payload,
    }
    event_id = hashlib.sha256(_stable_json(identity).encode("utf-8")).hexdigest()
    return {
        "_id": event_id,
        "event_id": event_id,
        "event_at": event_at,
        "event_type": event_type,
        "source": source,
        "decisionId": record.get("decisionId"),
        "cycleId": record.get("cycleId"),
        "symbol": record.get("symbol"),
        "positionState": record.get("positionState"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "execution": _execution_summary(record),
        "riskReview": _risk_summary(record),
        "modelDecision": _model_summary(record),
        "researchOutput": _research_summary(record),
        "opening_thesis_snapshot": deepcopy(record.get("opening_thesis_snapshot")),
        "provenance": deepcopy(record.get("provenance") or {}),
        "payload": payload,
    }


def append_trade_audit_event(
    db: Any,
    event_type: str,
    record: Dict[str, Any],
    *,
    source: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    event = build_trade_audit_event(event_type, record, source=source, payload=payload)
    append = getattr(db, "append_data", None)
    if callable(append):
        append(AUDIT_COLLECTION, event)
        return

    existing = db.get_data(AUDIT_COLLECTION, []) if hasattr(db, "get_data") else []
    if not isinstance(existing, list):
        existing = []
    event_id = event.get("event_id")
    if not any(isinstance(item, dict) and item.get("event_id") == event_id for item in existing):
        existing.append(event)
    if hasattr(db, "save_data"):
        db.save_data(AUDIT_COLLECTION, existing)
