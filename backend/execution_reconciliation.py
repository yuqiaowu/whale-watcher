from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from db_client import db
from okx_executor import OKXExecutor


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _trade_time_iso(value: Any) -> Optional[str]:
    dt = _parse_dt(value)
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ms_to_iso(value: Any) -> Optional[str]:
    try:
        if value is None or value == "":
            return None
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _normalize_symbol(value: Any) -> str:
    return str(value or "").replace("-USDT", "").replace("-SWAP", "").upper()


def _normalize_side(value: Any) -> str:
    raw = str(value or "").lower()
    if raw in {"long", "buy"}:
        return "LONG"
    if raw in {"short", "sell"}:
        return "SHORT"
    return raw.upper()


def _append_execution_event(record: Dict[str, Any], event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
    execution = record.setdefault("execution", {})
    history = execution.setdefault("history", [])
    history.append({
        "type": event_type,
        "at": _iso_now(),
        "payload": payload or {},
    })
    execution["history"] = history[-80:]


def _update_protection_state(execution: Dict[str, Any], live_position: Optional[Dict[str, Any]] = None) -> None:
    stop_loss = None
    take_profit = None
    if isinstance(live_position, dict):
        stop_loss = live_position.get("stopLoss")
        take_profit = live_position.get("takeProfit")
    execution["filled_stop_loss"] = stop_loss
    execution["filled_take_profit"] = take_profit
    execution["protection_last_synced_at"] = _iso_now()
    if stop_loss or take_profit:
        execution["protection_status"] = "OPEN"
    elif execution.get("order_status") == "FILLED":
        execution["protection_status"] = "MISSING"
    else:
        execution["protection_status"] = "NONE"


def _load_positions() -> List[Dict[str, Any]]:
    portfolio_state = db.get_data("portfolio_state", {})
    positions = portfolio_state.get("positions", []) if isinstance(portfolio_state, dict) else []
    return positions if isinstance(positions, list) else []


def _position_key(position: Dict[str, Any]) -> tuple:
    return (
        _normalize_symbol(position.get("symbol") or position.get("instId")),
        _normalize_side(position.get("type") or position.get("posSide")),
    )


def _position_open_timestamp(position: Dict[str, Any]) -> Tuple[str, str]:
    for field in ("positionOpenedAt", "openTime", "opened_at", "timestamp"):
        iso_value = _trade_time_iso(position.get(field))
        if iso_value:
            return iso_value, field
    for field in ("rawPositionCreatedTime", "cTime", "posCtime"):
        iso_value = _ms_to_iso(position.get(field))
        if iso_value:
            return iso_value, field
    return _iso_now(), "adoption_time"


def _match_live_position(record: Dict[str, Any], positions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    symbol = _normalize_symbol(record.get("symbol"))
    final_intent = _normalize_side((record.get("riskReview") or {}).get("final_intent"))
    for position in positions:
        if _normalize_symbol(position.get("symbol")) != symbol:
            continue
        if final_intent and _normalize_side(position.get("type")) != final_intent:
            continue
        return position
    return None


def _match_closed_trade(record: Dict[str, Any], trade_history: List[Dict[str, Any]], used_trade_ids: Set[str]) -> Optional[Dict[str, Any]]:
    record_dt = _parse_dt(record.get("created_at"))
    if record_dt is None:
        return None

    symbol = _normalize_symbol(record.get("symbol"))
    final_intent = _normalize_side((record.get("riskReview") or {}).get("final_intent"))
    execution = record.get("execution") or {}
    if execution.get("execution_action") not in {"OPEN_LONG", "OPEN_SHORT"}:
        return None

    candidates: List[Dict[str, Any]] = []
    for trade in trade_history:
        trade_id = str(trade.get("id", ""))
        if not trade_id or trade_id in used_trade_ids:
            continue
        if _normalize_symbol(trade.get("symbol")) != symbol:
            continue
        if _normalize_side(trade.get("type")) != final_intent:
            continue
        exit_dt = _parse_dt(trade.get("exitTime"))
        if exit_dt is None or exit_dt < record_dt:
            continue
        candidates.append(trade)

    if not candidates:
        return None
    candidates.sort(key=lambda item: _parse_dt(item.get("exitTime")) or datetime.max.replace(tzinfo=timezone.utc))
    return candidates[0]


def _closed_reason_from_execution(execution: Dict[str, Any]) -> Tuple[str, str]:
    runtime_reason = str(execution.get("runtime_reason") or "").strip()
    if runtime_reason:
        return runtime_reason, "position_runtime"
    failure_reason = str(execution.get("failure_reason") or "").strip()
    if failure_reason:
        return failure_reason, "execution_failure"
    if execution.get("runtime_action") == "CLOSE_POSITION":
        return "runtime_close_without_reason", "position_runtime"
    return "exchange_or_external_close", "trade_history_reconciliation"


def _maybe_backfill_position_open_time(record: Dict[str, Any], live_position: Dict[str, Any]) -> bool:
    timestamp, timestamp_source = _position_open_timestamp(live_position)
    if timestamp_source == "adoption_time":
        return False

    execution = record.setdefault("execution", {})
    current_executed_at = execution.get("executed_at")
    detected_at = execution.get("live_position_detected_at")
    created_at = record.get("created_at")
    if current_executed_at == timestamp and created_at == timestamp:
        return False
    if current_executed_at and current_executed_at != detected_at and current_executed_at != created_at:
        return False

    execution["executed_at"] = timestamp
    record["created_at"] = timestamp
    provenance = record.setdefault("provenance", {})
    provenance["position_open_time_source"] = timestamp_source
    _append_execution_event(record, "POSITION_OPEN_TIME_BACKFILLED", {
        "executed_at": timestamp,
        "source": timestamp_source,
        "previous_executed_at": current_executed_at,
        "previous_created_at": created_at,
    })
    return True


def _trade_id_set(records: List[Dict[str, Any]]) -> Set[str]:
    trade_ids: Set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        execution = record.get("execution") or {}
        for key in ("closed_trade_id", "exchange_order_id"):
            value = execution.get(key)
            if value:
                trade_ids.add(str(value))
        for event in execution.get("history", []) or []:
            payload = event.get("payload") or {}
            value = payload.get("trade_id")
            if value:
                trade_ids.add(str(value))
    return trade_ids


def _recent_unmatched_closed_trade(trade: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    exit_dt = _parse_dt(trade.get("exitTime"))
    if exit_dt is None:
        return False
    now = now or datetime.now(timezone.utc)
    return 0 <= (now - exit_dt).total_seconds() <= 72 * 3600


def _record_sort_dt(record: Dict[str, Any]) -> datetime:
    return (
        _parse_dt(record.get("created_at"))
        or _parse_dt((record.get("execution") or {}).get("executed_at"))
        or _parse_dt((record.get("execution") or {}).get("closed_at"))
        or datetime.min.replace(tzinfo=timezone.utc)
    )


def _closed_trade_decision_id(trade: Dict[str, Any]) -> str:
    trade_id = str(trade.get("id") or "unknown")
    symbol = _normalize_symbol(trade.get("symbol"))
    side = _normalize_side(trade.get("type")).lower() or "unknown"
    return f"unmatched_closed_{symbol}_{side}_{trade_id}"


def _adopt_closed_trade(trade: Dict[str, Any]) -> Dict[str, Any]:
    symbol_base = _normalize_symbol(trade.get("symbol"))
    side = _normalize_side(trade.get("type"))
    symbol = f"{symbol_base}-USDT"
    entry_time = _trade_time_iso(trade.get("entryTime")) or _trade_time_iso(trade.get("exitTime")) or _iso_now()
    exit_time = _trade_time_iso(trade.get("exitTime")) or trade.get("exitTime")
    entry_price = _safe_float(trade.get("entryPrice"))
    exit_price = _safe_float(trade.get("exitPrice"))
    amount = _safe_float(trade.get("amount"))
    trade_id = str(trade.get("id") or "")
    execution_action = "OPEN_LONG" if side == "LONG" else "OPEN_SHORT"
    close_reason = "unmatched_okx_closed_trade"
    return {
        "decisionId": _closed_trade_decision_id(trade),
        "cycleId": "unmatched_closed_trade",
        "symbol": symbol,
        "timeframe": "4h",
        "snapshot_timestamp": None,
        "positionState": "closed",
        "snapshot": {
            "symbol": symbol,
            "cycleId": "unmatched_closed_trade",
            "timeframe": "4h",
            "market_snapshot": {"price": exit_price},
            "position_snapshot": {"position_side": side},
        },
        "candidate": {
            "symbol": symbol,
            "cycleId": "unmatched_closed_trade",
            "timeframe": "4h",
            "candidate_proposals": [{
                "strategy_family": "DIRECTIONAL",
                "decision_intent": side,
                "trigger_source": "UNMATCHED_CLOSED_TRADE",
                "rationale": "OKX closed trade reconciled without a matching local decision record",
                "entry_type": "MARKET",
                "proposed_entry_price": entry_price,
                "proposed_sl_price": None,
                "proposed_tp_price": None,
                "reference_values": {},
                "invalidation_basis": "historical closed trade; original decision record unavailable",
                "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
            }],
        },
        "ruleEvaluation": {
            "symbol": symbol,
            "cycleId": "unmatched_closed_trade",
            "stage": "closed_trade_reconciliation",
            "passed": True,
            "reason_codes": ["UNMATCHED_CLOSED_TRADE"],
            "approved_candidates": [],
            "rule_trace": [{"rule": "UNMATCHED_CLOSED_TRADE", "passed": True}],
        },
        "researchOutput": {
            "symbol": symbol,
            "cycleId": "unmatched_closed_trade",
            "strategy_family": "DIRECTIONAL",
            "selected_intent": side,
            "selected_trigger_sources": ["UNMATCHED_CLOSED_TRADE"],
            "thesis_strength": "UNKNOWN",
            "holding_horizon": "UNKNOWN",
            "thesis_change": "UNKNOWN",
            "summary": "Closed OKX trade was found, but the matching local decision record was unavailable.",
            "provenance": {
                "generation_mode": "closed_trade_reconciliation",
                "llm_enabled": False,
                "llm_attempted": False,
                "llm_applied": False,
            },
        },
        "riskReview": {
            "symbol": symbol,
            "cycleId": "unmatched_closed_trade",
            "strategy_family": "DIRECTIONAL",
            "approved": True,
            "final_intent": side,
            "approved_risk_fraction": 0.0,
            "approved_position_size_usd": round(entry_price * amount, 2) if entry_price and amount else 0.0,
            "leverage": _safe_float(trade.get("leverage"), 1.0),
            "max_holding_bars": 0,
            "execution_action": execution_action,
            "next_position_state": "closed",
            "review_note": "closed OKX trade reconciled without matching local decision record; not a new model approval",
        },
        "execution": {
            "symbol": symbol,
            "cycleId": "unmatched_closed_trade",
            "strategy_family": "DIRECTIONAL",
            "execution_action": execution_action,
            "order_status": "CLOSED",
            "sync_status": "CLOSED",
            "closed_trade_id": trade_id,
            "entry_type": "MARKET",
            "proposed_entry_price": entry_price,
            "avg_fill_price": entry_price,
            "avg_exit_price": exit_price,
            "filled_size": amount,
            "requested_leverage": _safe_float(trade.get("leverage"), 1.0),
            "executed_at": entry_time,
            "closed_at": exit_time,
            "realized_pnl": round(_safe_float(trade.get("pnl")), 2),
            "realized_pnl_percent": round(_safe_float(trade.get("pnlPercent")), 2),
            "position_side": side,
            "protection_status": "CLOSED",
            "runtime_reason": close_reason,
            "close_reason": close_reason,
            "close_reason_source": "unmatched_trade_history",
            "history": [{
                "type": "EXECUTION_CLOSED_UNMATCHED_RECONCILED",
                "at": _iso_now(),
                "payload": {
                    "trade_id": trade_id,
                    "reason": close_reason,
                    "source": trade.get("reason") or "OKX trade_history",
                    "entry_time": trade.get("entryTime"),
                    "exit_time": trade.get("exitTime"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl": round(_safe_float(trade.get("pnl")), 2),
                    "pnl_percent": round(_safe_float(trade.get("pnlPercent")), 2),
                },
            }],
        },
        "evaluation": None,
        "created_at": entry_time,
        "updated_at": _iso_now(),
        "provenance": {"source": "execution_reconciliation", "unmatched_closed_trade": True},
    }


def _normalize_grid_state(value: Any) -> str:
    return str(value or "").strip().lower()


def _reconcile_grid_execution(record: Dict[str, Any], executor: OKXExecutor) -> bool:
    execution = record.get("execution") or {}
    algo_id = execution.get("exchange_algo_id")
    if not algo_id or not hasattr(executor, "get_grid_bot_details"):
        return False

    details = executor.get_grid_bot_details(algo_id, algo_ord_type="contract_grid")
    if not isinstance(details, dict) or details.get("code") != "0":
        return False
    data = details.get("data") or []
    if not isinstance(data, list) or not data:
        return False

    detail = data[0] if isinstance(data[0], dict) else {}
    state = _normalize_grid_state(detail.get("state"))
    if not state:
        return False

    changed = False
    execution["grid_state"] = state
    execution["grid_last_synced_at"] = _iso_now()
    execution["avg_fill_price"] = _safe_float(detail.get("avgPx"), execution.get("avg_fill_price"))
    execution["filled_size"] = _safe_float(detail.get("sz"), execution.get("filled_size"))

    if state in {"running", "effective", "live"}:
        if execution.get("order_status") != "FILLED":
            execution["order_status"] = "FILLED"
            changed = True
        if execution.get("sync_status") != "RUNNING":
            execution["sync_status"] = "RUNNING"
            changed = True
        if record.get("positionState") != "entered":
            record["positionState"] = "entered"
            changed = True
        if changed:
            _append_execution_event(record, "GRID_EXECUTION_RUNNING_SYNCED", {
                "algo_id": algo_id,
                "state": state,
            })
    elif state in {"stopping", "stop_pending"}:
        if execution.get("sync_status") != "STOP_REQUESTED":
            execution["sync_status"] = "STOP_REQUESTED"
            changed = True
            _append_execution_event(record, "GRID_EXECUTION_STOP_PENDING_SYNCED", {
                "algo_id": algo_id,
                "state": state,
            })
    elif state in {"stopped", "cancelled", "canceled", "closed"}:
        if execution.get("order_status") != "CLOSED":
            execution["order_status"] = "CLOSED"
            changed = True
        if execution.get("sync_status") != "CLOSED":
            execution["sync_status"] = "CLOSED"
            changed = True
        if execution.get("protection_status") != "CLOSED":
            execution["protection_status"] = "CLOSED"
            changed = True
        if record.get("positionState") != "closed":
            record["positionState"] = "closed"
            changed = True
        if changed:
            _append_execution_event(record, "GRID_EXECUTION_CLOSED_SYNCED", {
                "algo_id": algo_id,
                "state": state,
            })
    elif state in {"failed", "pause_failed"}:
        if execution.get("order_status") != "FAILED":
            execution["order_status"] = "FAILED"
            changed = True
        if execution.get("sync_status") != "FAILED":
            execution["sync_status"] = "FAILED"
            changed = True
        if changed:
            _append_execution_event(record, "GRID_EXECUTION_FAILED_SYNCED", {
                "algo_id": algo_id,
                "state": state,
            })

    record["execution"] = execution
    return changed


def _latest_snapshot_for_symbol(symbol: str) -> Dict[str, Any]:
    latest_cycle = db.get_data("latest_decision_cycle_v2", {})
    snapshots = latest_cycle.get("snapshots", []) if isinstance(latest_cycle, dict) else []
    normalized = _normalize_symbol(symbol)
    for snapshot in snapshots:
        if _normalize_symbol(snapshot.get("symbol")) == normalized:
            return snapshot if isinstance(snapshot, dict) else {}
    return {}


def _adopt_live_position(position: Dict[str, Any]) -> Dict[str, Any]:
    symbol_base, side = _position_key(position)
    symbol = f"{symbol_base}-USDT"
    now_iso = _iso_now()
    entry_price = _safe_float(position.get("entryPrice"))
    current_price = _safe_float(position.get("currentPrice"), entry_price)
    amount = _safe_float(position.get("amount") or position.get("pos") or position.get("size"))
    leverage = max(_safe_float(position.get("leverage"), 1.0), 1.0)
    timestamp, timestamp_source = _position_open_timestamp(position)
    snapshot = _latest_snapshot_for_symbol(symbol)
    if not snapshot:
        snapshot = {
            "symbol": symbol,
            "cycleId": "adopted_live_position",
            "timeframe": "4h",
            "snapshot_timestamp": None,
            "market_snapshot": {"price": current_price},
            "onchain_snapshot": {},
            "macro_snapshot": {},
            "position_snapshot": {"position_side": side},
            "decision_ready_features": {},
        }

    stop_loss = position.get("stopLoss")
    take_profit = position.get("takeProfit")
    execution_action = "OPEN_LONG" if side == "LONG" else "OPEN_SHORT"
    timestamp_key = str(timestamp).replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
    decision_id = f"adopted_{symbol_base}_{side.lower()}_{str(entry_price).replace('.', '_')}_{timestamp_key}"
    approved_candidate = {
        "strategy_family": "DIRECTIONAL",
        "decision_intent": side,
        "trigger_source": "ADOPTED_LIVE_POSITION",
        "rationale": "live exchange position adopted into V2 ledger for runtime management",
        "entry_type": "MARKET",
        "proposed_entry_price": entry_price,
        "proposed_sl_price": stop_loss,
        "proposed_tp_price": take_profit,
        "reference_values": {},
        "invalidation_basis": "manual or external live position; no original candidate invalidation available",
        "invalidation_conditions": {"operator": "OR", "rules": [], "persistence": 1},
    }
    return {
        "decisionId": decision_id,
        "cycleId": snapshot.get("cycleId") or "adopted_live_position",
        "symbol": symbol,
        "timeframe": snapshot.get("timeframe") or "4h",
        "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
        "positionState": "entered",
        "snapshot": snapshot,
        "candidate": {
            "symbol": symbol,
            "cycleId": snapshot.get("cycleId") or "adopted_live_position",
            "timeframe": snapshot.get("timeframe") or "4h",
            "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
            "candidate_proposals": [approved_candidate],
        },
        "ruleEvaluation": {
            "symbol": symbol,
            "cycleId": snapshot.get("cycleId") or "adopted_live_position",
            "stage": "live_position_adoption",
            "passed": True,
            "reason_codes": [],
            "approved_candidates": [approved_candidate],
            "rule_trace": [{"rule": "LIVE_POSITION_ADOPTION", "passed": True}],
            "candidate_structure": {
                "overall_state": "single_signal",
                "has_directional_conflict": False,
                "long_count": 1 if side == "LONG" else 0,
                "short_count": 1 if side == "SHORT" else 0,
                "grid_count": 0,
                "resonance_groups": {"LONG": ["ADOPTED_LIVE_POSITION"] if side == "LONG" else [], "SHORT": ["ADOPTED_LIVE_POSITION"] if side == "SHORT" else [], "GRID_NEUTRAL": []},
                "approved_groups": {"LONG": ["ADOPTED_LIVE_POSITION"] if side == "LONG" else [], "SHORT": ["ADOPTED_LIVE_POSITION"] if side == "SHORT" else [], "GRID_NEUTRAL": []},
                "approved_resonance_strength": 1,
            },
        },
        "researchOutput": {
            "symbol": symbol,
            "cycleId": snapshot.get("cycleId") or "adopted_live_position",
            "strategy_family": "DIRECTIONAL",
            "selected_intent": side,
            "selected_trigger_sources": ["ADOPTED_LIVE_POSITION"],
            "thesis_strength": "MEDIUM",
            "holding_horizon": "SHORT",
            "thesis_change": "UNCHANGED",
            "summary": "Existing live exchange position adopted for monitoring; original pre-trade thesis is unavailable.",
            "provenance": {
                "generation_mode": "adopted_live_position",
                "llm_enabled": False,
                "llm_attempted": False,
                "llm_applied": False,
                "llm_override_fields": [],
            },
        },
        "riskReview": {
            "symbol": symbol,
            "cycleId": snapshot.get("cycleId") or "adopted_live_position",
            "strategy_family": "DIRECTIONAL",
            "approved": True,
            "final_intent": side,
            "approved_risk_fraction": 0.0,
            "approved_position_size_usd": round(entry_price * amount, 2) if entry_price and amount else 0.0,
            "leverage": leverage,
            "max_holding_bars": 3,
            "execution_action": execution_action,
            "next_position_state": "entered",
            "review_note": "adopted existing live position for runtime management; not a new model approval",
            "approved_candidate": approved_candidate,
        },
        "execution": {
            "symbol": symbol,
            "cycleId": snapshot.get("cycleId") or "adopted_live_position",
            "strategy_family": "DIRECTIONAL",
            "execution_action": execution_action,
            "order_status": "FILLED",
            "requested_size_usd": round(entry_price * amount, 2) if entry_price and amount else 0.0,
            "requested_leverage": leverage,
            "entry_type": "MARKET",
            "proposed_entry_price": entry_price,
            "proposed_sl_price": stop_loss,
            "proposed_tp_price": take_profit,
            "avg_fill_price": entry_price,
            "filled_size": amount,
            "exchange_order_id": position.get("ordId") or position.get("orderId"),
            "executed_at": timestamp,
            "sync_status": "OPEN",
            "failure_reason": None,
            "position_side": side,
            "live_position_detected_at": now_iso,
            "protection_status": "OPEN" if stop_loss or take_profit else "MISSING",
            "filled_stop_loss": stop_loss,
            "filled_take_profit": take_profit,
            "history": [{
                "type": "LIVE_POSITION_ADOPTED",
                "at": now_iso,
                "payload": {
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "amount": amount,
                    "source": "portfolio_state.positions",
                    "position_open_time_source": timestamp_source,
                },
            }],
        },
        "evaluation": None,
        "created_at": timestamp,
        "updated_at": now_iso,
        "provenance": {
            "source": "execution_reconciliation",
            "adopted_live_position": True,
            "position_open_time_source": timestamp_source,
        },
    }


def run_execution_reconciliation() -> Dict[str, Any]:
    records = db.get_data("trade_decision_records", [])
    if not isinstance(records, list):
        return {"updated_count": 0, "record_count": 0, "actions": []}

    positions = _load_positions()
    trade_history = db.get_data("trade_history", [])
    if not isinstance(trade_history, list):
        trade_history = []

    used_trade_ids: Set[str] = set()
    updated_count = 0
    actions: List[Dict[str, Any]] = []
    executor = OKXExecutor()
    managed_position_keys = set()

    for record in records:
        execution = record.get("execution") or {}
        risk_review = record.get("riskReview") or {}
        if risk_review.get("approved") is not True:
            continue
        if record.get("positionState") == "closed" or execution.get("order_status") == "CLOSED":
            continue
        if execution.get("execution_action") == "START_GRID_BOT":
            before = {
                "order_status": execution.get("order_status"),
                "sync_status": execution.get("sync_status"),
                "grid_state": execution.get("grid_state"),
                "exchange_algo_id": execution.get("exchange_algo_id"),
            }
            changed = _reconcile_grid_execution(record, executor)
            record["updated_at"] = _iso_now()
            after_execution = record.get("execution") or {}
            after = {
                "order_status": after_execution.get("order_status"),
                "sync_status": after_execution.get("sync_status"),
                "grid_state": after_execution.get("grid_state"),
                "exchange_algo_id": after_execution.get("exchange_algo_id"),
            }
            if changed and before != after:
                updated_count += 1
                actions.append({
                    "decisionId": record.get("decisionId"),
                    "symbol": record.get("symbol"),
                    "before": before,
                    "after": after,
                })
            continue
        if execution.get("execution_action") not in {"OPEN_LONG", "OPEN_SHORT"}:
            continue

        before = {
            "order_status": execution.get("order_status"),
            "sync_status": execution.get("sync_status"),
            "avg_fill_price": execution.get("avg_fill_price"),
            "filled_size": execution.get("filled_size"),
            "closed_trade_id": execution.get("closed_trade_id"),
            "protection_status": execution.get("protection_status"),
        }

        live_position = _match_live_position(record, positions)
        closed_trade = _match_closed_trade(record, trade_history, used_trade_ids)

        if live_position:
            managed_position_keys.add(_position_key(live_position))
            if _maybe_backfill_position_open_time(record, live_position):
                execution = record.get("execution") or execution
            if execution.get("order_status") != "FILLED":
                execution["order_status"] = "FILLED"
                execution["sync_status"] = "FILLED"
                execution["avg_fill_price"] = _safe_float(live_position.get("entryPrice"), execution.get("avg_fill_price"))
                execution["filled_size"] = _safe_float(live_position.get("amount"))
                execution["position_side"] = _normalize_side(live_position.get("type"))
                execution["live_position_detected_at"] = _iso_now()
                _update_protection_state(execution, live_position)
                _append_execution_event(record, "EXECUTION_FILLED_RECONCILED", {
                    "entry_price": execution.get("avg_fill_price"),
                    "filled_size": execution.get("filled_size"),
                    "position_side": execution.get("position_side"),
                    "protection_status": execution.get("protection_status"),
                })
            elif execution.get("sync_status") != "OPEN":
                execution["sync_status"] = "OPEN"
                _update_protection_state(execution, live_position)
                _append_execution_event(record, "EXECUTION_OPEN_POSITION_SYNCED", {
                    "symbol": record.get("symbol"),
                    "protection_status": execution.get("protection_status"),
                })
            else:
                prior_protection = execution.get("protection_status")
                _update_protection_state(execution, live_position)
                if execution.get("protection_status") != prior_protection:
                    _append_execution_event(record, "EXECUTION_PROTECTION_SYNCED", {
                        "protection_status": execution.get("protection_status"),
                        "stop_loss": execution.get("filled_stop_loss"),
                        "take_profit": execution.get("filled_take_profit"),
                    })

        elif closed_trade:
            trade_id = str(closed_trade.get("id", ""))
            used_trade_ids.add(trade_id)
            if execution.get("closed_trade_id") != trade_id or execution.get("order_status") != "CLOSED":
                close_reason, close_reason_source = _closed_reason_from_execution(execution)
                execution["order_status"] = "CLOSED"
                execution["sync_status"] = "CLOSED"
                execution["closed_trade_id"] = trade_id
                execution["closed_at"] = closed_trade.get("exitTime")
                execution["realized_pnl"] = round(_safe_float(closed_trade.get("pnl")), 2)
                execution["realized_pnl_percent"] = round(_safe_float(closed_trade.get("pnlPercent")), 2)
                execution["avg_exit_price"] = _safe_float(closed_trade.get("exitPrice"), None)
                execution["protection_status"] = "CLOSED"
                execution["close_reason"] = close_reason
                execution["close_reason_source"] = close_reason_source
                record["positionState"] = "closed"
                _append_execution_event(record, "EXECUTION_CLOSED_RECONCILED", {
                    "trade_id": trade_id,
                    "pnl": execution.get("realized_pnl"),
                    "pnl_percent": execution.get("realized_pnl_percent"),
                    "reason": close_reason,
                    "reason_source": close_reason_source,
                    "runtime_action": execution.get("runtime_action"),
                    "okx_reason": closed_trade.get("reason"),
                })

        elif execution.get("order_status") == "FILLED":
            execution["sync_status"] = "PENDING_CLOSE_SYNC"

        record["execution"] = execution
        record["updated_at"] = _iso_now()

        after = {
            "order_status": execution.get("order_status"),
            "sync_status": execution.get("sync_status"),
            "avg_fill_price": execution.get("avg_fill_price"),
            "filled_size": execution.get("filled_size"),
            "closed_trade_id": execution.get("closed_trade_id"),
            "protection_status": execution.get("protection_status"),
        }
        if before != after:
            updated_count += 1
            actions.append({
                "decisionId": record.get("decisionId"),
                "symbol": record.get("symbol"),
                "before": before,
                "after": after,
            })

    existing_decision_ids = {str(record.get("decisionId") or "") for record in records if isinstance(record, dict)}
    adopted_records: List[Dict[str, Any]] = []
    for position in positions:
        key = _position_key(position)
        symbol, side = key
        if not symbol or side not in {"LONG", "SHORT"}:
            continue
        if key in managed_position_keys:
            continue
        adopted = _adopt_live_position(position)
        if str(adopted.get("decisionId") or "") in existing_decision_ids:
            continue
        adopted_records.append(adopted)
        existing_decision_ids.add(str(adopted.get("decisionId") or ""))
        actions.append({
            "decisionId": adopted.get("decisionId"),
            "symbol": adopted.get("symbol"),
            "before": {"order_status": None, "sync_status": None},
            "after": {"order_status": "FILLED", "sync_status": "OPEN", "adopted_live_position": True},
        })

    if adopted_records:
        records = adopted_records + records
        updated_count += len(adopted_records)

    existing_trade_ids = _trade_id_set(records).union(used_trade_ids)
    unmatched_closed_records: List[Dict[str, Any]] = []
    existing_decision_ids = {str(record.get("decisionId") or "") for record in records if isinstance(record, dict)}
    for trade in trade_history:
        trade_id = str(trade.get("id") or "")
        if not trade_id or trade_id in existing_trade_ids:
            continue
        if not _recent_unmatched_closed_trade(trade):
            continue
        unmatched = _adopt_closed_trade(trade)
        decision_id = str(unmatched.get("decisionId") or "")
        if decision_id in existing_decision_ids:
            continue
        unmatched_closed_records.append(unmatched)
        existing_trade_ids.add(trade_id)
        existing_decision_ids.add(decision_id)
        actions.append({
            "decisionId": unmatched.get("decisionId"),
            "symbol": unmatched.get("symbol"),
            "before": {"order_status": None, "sync_status": None},
            "after": {
                "order_status": "CLOSED",
                "sync_status": "CLOSED",
                "closed_trade_id": trade_id,
                "unmatched_closed_trade": True,
            },
        })

    if unmatched_closed_records:
        records = unmatched_closed_records + records
        updated_count += len(unmatched_closed_records)

    if records:
        records = sorted(records, key=_record_sort_dt, reverse=True)
        db.save_data("trade_decision_records", records)
        db.save_data("latest_trade_decision_record", records[0])
    return {
        "updated_count": updated_count,
        "record_count": len(records),
        "actions": actions[-50:],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_execution_reconciliation(), indent=2, ensure_ascii=False))
