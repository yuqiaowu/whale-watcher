from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

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

    for record in records:
        execution = record.get("execution") or {}
        risk_review = record.get("riskReview") or {}
        if risk_review.get("approved") is not True:
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
                execution["order_status"] = "CLOSED"
                execution["sync_status"] = "CLOSED"
                execution["closed_trade_id"] = trade_id
                execution["closed_at"] = closed_trade.get("exitTime")
                execution["realized_pnl"] = round(_safe_float(closed_trade.get("pnl")), 2)
                execution["realized_pnl_percent"] = round(_safe_float(closed_trade.get("pnlPercent")), 2)
                execution["avg_exit_price"] = _safe_float(closed_trade.get("exitPrice"), None)
                execution["protection_status"] = "CLOSED"
                record["positionState"] = "closed"
                _append_execution_event(record, "EXECUTION_CLOSED_RECONCILED", {
                    "trade_id": trade_id,
                    "pnl": execution.get("realized_pnl"),
                    "pnl_percent": execution.get("realized_pnl_percent"),
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

    if records:
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
