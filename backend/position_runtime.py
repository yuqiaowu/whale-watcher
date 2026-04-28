from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from db_client import db
from okx_executor import OKXExecutor


BREAK_EVEN_TRIGGER_PNL = 1.0
TRAILING_TRIGGER_PNL = 2.0
TRAILING_STOP_BUFFER = 0.01
LIQ_REDUCE_THRESHOLD = 0.10
LIQ_CLOSE_THRESHOLD = 0.05
THESIS_WEAKENED_REDUCE_RATIO = 0.25
DEFENSIVE_TIMEOUT_BARS = 3
BAR_HOURS = 4


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
    execution["history"] = history[-50:]


def _latest_snapshot_map() -> Dict[str, Dict[str, Any]]:
    latest_cycle = db.get_data("latest_decision_cycle_v2", {})
    snapshots = latest_cycle.get("snapshots", []) if isinstance(latest_cycle, dict) else []
    result: Dict[str, Dict[str, Any]] = {}
    for snapshot in snapshots:
        result[str(snapshot.get("symbol"))] = snapshot
    return result


def _load_positions() -> List[Dict[str, Any]]:
    portfolio_state = db.get_data("portfolio_state", {})
    positions = portfolio_state.get("positions", []) if isinstance(portfolio_state, dict) else []
    return positions if isinstance(positions, list) else []


def _estimate_distance_to_liq(live_position: Dict[str, Any]) -> Optional[float]:
    explicit = live_position.get("distance_to_liq")
    try:
        if explicit is not None:
            return float(explicit)
    except Exception:
        pass

    current = _safe_float(live_position.get("currentPrice"))
    entry = _safe_float(live_position.get("entryPrice"))
    leverage = max(_safe_float(live_position.get("leverage"), 1.0), 1.0)
    if current <= 0 or entry <= 0:
        return None
    adverse_move = abs(current - entry) / current if current else 0.0
    base_buffer = max(0.03, min(0.80, 1.0 / leverage))
    return max(0.0, round(base_buffer - adverse_move, 4))


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


def _resolve_runtime_field(field: str, snapshot: Dict[str, Any], live_position: Dict[str, Any], reference_values: Dict[str, Any]) -> Any:
    if field == "price":
        return _safe_float(live_position.get("currentPrice"))
    if field in reference_values:
        return reference_values[field]
    for source in (
        snapshot.get("decision_ready_features", {}),
        snapshot.get("market_snapshot", {}),
        snapshot.get("onchain_snapshot", {}),
        snapshot.get("macro_snapshot", {}),
        snapshot.get("position_snapshot", {}),
    ):
        if field in source:
            return source[field]
    return None


def _candidate_trigger_source(record: Dict[str, Any]) -> str:
    approved_candidate = (record.get("riskReview") or {}).get("approved_candidate", {}) or {}
    return str(approved_candidate.get("trigger_source") or "")


def _is_f_blueprint(record: Dict[str, Any]) -> bool:
    return _candidate_trigger_source(record) in {"Blueprint_F1", "Blueprint_F2"}


def _f_runtime_exit(record: Dict[str, Any], snapshot: Dict[str, Any], live_position: Dict[str, Any], side: str) -> Optional[Tuple[str, str]]:
    if not _is_f_blueprint(record):
        return None
    market = snapshot.get("market_snapshot", {}) or {}
    current_price = _safe_float(live_position.get("currentPrice"))
    rsi_4h = _safe_float(market.get("rsi_4h"))
    sma50_4h = _safe_float(market.get("sma50_4h"))
    macd_cross_up = bool(market.get("macd_cross_up_4h"))
    macd_cross_down = bool(market.get("macd_cross_down_4h"))
    bearish_divergence = bool(market.get("bearish_divergence_4h"))
    bullish_divergence = bool(market.get("bullish_divergence_4h"))
    approved_candidate = (record.get("riskReview") or {}).get("approved_candidate", {}) or {}
    reference_values = approved_candidate.get("reference_values", {}) or {}

    if side == "LONG":
        structure_stop = _safe_float(reference_values.get("structure_support_stop_long"), _safe_float(market.get("structure_support_stop_long")))
        if structure_stop > 0 and current_price <= structure_stop and sma50_4h > 0 and current_price < sma50_4h:
            return "CLOSE_POSITION", "f_structure_support_broken"
        if rsi_4h > 70 and (macd_cross_down or bearish_divergence):
            return "CLOSE_POSITION", "f_overbought_momentum_reversal"
    else:
        structure_stop = _safe_float(reference_values.get("structure_resistance_stop_short"), _safe_float(market.get("structure_resistance_stop_short")))
        if structure_stop > 0 and current_price >= structure_stop and sma50_4h > 0 and current_price > sma50_4h:
            return "CLOSE_POSITION", "f_structure_resistance_broken"
        if rsi_4h < 30 and (macd_cross_up or bullish_divergence):
            return "CLOSE_POSITION", "f_oversold_momentum_reversal"
    return None


def _evaluate_invalidation(record: Dict[str, Any], snapshot: Dict[str, Any], live_position: Dict[str, Any]) -> bool:
    approved_candidate = (record.get("riskReview") or {}).get("approved_candidate", {}) or {}
    conditions = approved_candidate.get("invalidation_conditions", {}) or {}
    rules = conditions.get("rules", []) or []
    operator = str(conditions.get("operator", "OR")).upper()
    reference_values = approved_candidate.get("reference_values", {}) or {}
    if not rules:
        return False

    results: List[bool] = []
    for rule in rules:
        field = rule.get("field")
        op = rule.get("op")
        left = _resolve_runtime_field(field, snapshot, live_position, reference_values)
        if "value_ref" in rule:
            right = reference_values.get(rule.get("value_ref"))
        else:
            right = rule.get("value")
        if left is None or right is None:
            results.append(False)
            continue
        try:
            if op == "<=":
                results.append(float(left) <= float(right))
            elif op == ">=":
                results.append(float(left) >= float(right))
            elif op == "==":
                results.append(str(left) == str(right))
            elif op == "<":
                results.append(float(left) < float(right))
            elif op == ">":
                results.append(float(left) > float(right))
            else:
                results.append(False)
        except Exception:
            results.append(False)

    return any(results) if operator == "OR" else all(results)


def _existing_stop_loss(live_position: Dict[str, Any], record: Dict[str, Any]) -> Optional[float]:
    execution = record.get("execution", {}) or {}
    candidates = [
        live_position.get("stopLoss"),
        execution.get("active_stop_loss"),
        execution.get("proposed_sl_price"),
        execution.get("filled_stop_loss"),
    ]
    for item in candidates:
        if item is None:
            continue
        try:
            return float(item)
        except Exception:
            continue
    return None


def _apply_adjustment(
    executor: OKXExecutor,
    symbol: str,
    side: str,
    stop_loss: Optional[float],
    take_profit: Optional[float],
) -> Optional[str]:
    return executor.execute_trade(
        symbol=symbol,
        action="adjust_sl_tp" if stop_loss is not None or take_profit is not None else "adjust_sl",
        amount_usd=0.0,
        leverage=1.0,
        stop_loss=stop_loss,
        take_profit=take_profit,
        pos_side=side.lower(),
    )


def _apply_close(executor: OKXExecutor, symbol: str, side: str, live_position: Dict[str, Any]) -> Optional[str]:
    margin = _safe_float(live_position.get("margin"))
    leverage = max(_safe_float(live_position.get("leverage"), 1.0), 1.0)
    notional = margin * leverage if margin > 0 else _safe_float(live_position.get("amount")) * _safe_float(live_position.get("currentPrice"))
    action = "close_long" if side == "LONG" else "close_short"
    return executor.execute_trade(
        symbol=symbol,
        action=action,
        amount_usd=max(notional, 1.0),
        leverage=leverage,
        pos_side=side.lower(),
    )


def _apply_reduce(executor: OKXExecutor, symbol: str, side: str, ratio: float, live_position: Dict[str, Any]) -> Optional[str]:
    margin = _safe_float(live_position.get("margin"))
    leverage = max(_safe_float(live_position.get("leverage"), 1.0), 1.0)
    notional = margin * leverage if margin > 0 else _safe_float(live_position.get("amount")) * _safe_float(live_position.get("currentPrice"))
    if ratio >= 0.75:
        action = "reduce_75_long" if side == "LONG" else "reduce_75_short"
    elif ratio >= 0.50:
        action = "reduce_50_long" if side == "LONG" else "reduce_50_short"
    else:
        action = "reduce_25_long" if side == "LONG" else "reduce_25_short"
    return executor.execute_trade(
        symbol=symbol,
        action=action,
        amount_usd=max(notional, 1.0),
        leverage=leverage,
        pos_side=side.lower(),
    )


def _apply_stop_grid(executor: OKXExecutor, symbol: str, algo_id: Optional[str]) -> Optional[str]:
    if hasattr(executor, "stop_grid_bot"):
        return executor.stop_grid_bot(symbol=symbol, algo_id=algo_id)
    return None


def _bars_since(timestamp: Any) -> Optional[int]:
    dt = _parse_dt(timestamp)
    if dt is None:
        return None
    delta = datetime.now(timezone.utc) - dt
    if delta.total_seconds() < 0:
        return 0
    return int(delta.total_seconds() // (BAR_HOURS * 3600))


def _holding_bars(record: Dict[str, Any], live_position: Dict[str, Any]) -> Optional[int]:
    execution = record.get("execution") or {}
    candidates = [
        execution.get("executed_at"),
        live_position.get("timestamp"),
        record.get("created_at"),
    ]
    for candidate in candidates:
        bars = _bars_since(candidate)
        if bars is not None:
            return bars
    return None


def _thesis_weakened(record: Dict[str, Any], snapshot: Dict[str, Any], live_position: Dict[str, Any], side: str) -> Tuple[bool, str]:
    research = record.get("researchOutput") or {}
    if research.get("thesis_change") == "WEAKENED":
        return True, "research_thesis_weakened"
    if research.get("thesis_change") == "REVERSED":
        return True, "research_thesis_reversed"
    if research.get("thesis_strength") == "LOW":
        return True, "research_thesis_low"

    features = snapshot.get("decision_ready_features", {}) or {}
    macro_permission = features.get("macro_permission")
    flow_support = bool(features.get("flow_support_long")) if side == "LONG" else bool(features.get("flow_support_short"))
    regime = features.get("regime_1d")

    if side == "LONG":
        if macro_permission == "ALLOW_SHORT":
            return True, "macro_permission_against_long"
        if regime == "BEAR" and not flow_support:
            return True, "bear_regime_without_flow_support"
    else:
        if macro_permission == "ALLOW_LONG":
            return True, "macro_permission_against_short"
        if regime == "BULL" and not flow_support:
            return True, "bull_regime_without_flow_support"
    return False, ""


def _grid_runtime_signal(record: Dict[str, Any], snapshot: Dict[str, Any], held_bars: Optional[int]) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    execution = record.get("execution") or {}
    risk_review = record.get("riskReview") or {}
    approved_candidate = risk_review.get("approved_candidate", {}) or {}
    reference_values = approved_candidate.get("reference_values", {}) or execution.get("grid_config", {}) or {}
    features = snapshot.get("decision_ready_features", {}) or {}
    market = snapshot.get("market_snapshot", {}) or {}

    current_price = _safe_float(market.get("price"))
    lower_bound = _safe_float(reference_values.get("range_lower_bound"))
    upper_bound = _safe_float(reference_values.get("range_upper_bound"))
    p_flat_8h = _safe_float(features.get("p_flat_8h"), _safe_float(reference_values.get("p_flat_8h")))
    p_up_8h = _safe_float(features.get("p_up_8h"), _safe_float(reference_values.get("p_up_8h")))
    p_down_8h = _safe_float(features.get("p_down_8h"), _safe_float(reference_values.get("p_down_8h")))
    max_holding_bars = int((risk_review or {}).get("max_holding_bars") or 0)
    review_after_bars = max(1, int(_safe_float(reference_values.get("review_after_hours"), 36) / 4))
    extension_step_bars = max(1, int(_safe_float(reference_values.get("extension_step_hours"), 12) / 4))

    if features.get("macro_mode") == "EVENT_DRIVEN":
        return "STOP_GRID_BOT", "grid_event_window", {"macro_mode": "EVENT_DRIVEN"}
    if features.get("grid_macro_trend_ok") is False:
        return "STOP_GRID_BOT", "grid_macro_trend_blocked", {
            "macro_block_reasons": features.get("grid_macro_block_reasons") or [],
            "ma5_cross_up_ma10_1d": bool(features.get("ma5_cross_up_ma10_1d")),
            "ma5_cross_down_ma10_1d": bool(features.get("ma5_cross_down_ma10_1d")),
        }
    if lower_bound > 0 and current_price > 0 and current_price <= lower_bound:
        return "STOP_GRID_BOT", "grid_range_breakdown", {"current_price": current_price, "range_lower_bound": lower_bound}
    if upper_bound > 0 and current_price > 0 and current_price >= upper_bound:
        return "STOP_GRID_BOT", "grid_range_breakout", {"current_price": current_price, "range_upper_bound": upper_bound}
    if p_flat_8h < 0.45 and max(p_up_8h, p_down_8h) >= 0.55:
        return "STOP_GRID_BOT", "grid_regime_deterioration", {
            "p_flat_8h": p_flat_8h,
            "p_up_8h": p_up_8h,
            "p_down_8h": p_down_8h,
        }
    if (
        held_bars is not None
        and held_bars >= review_after_bars
        and (held_bars - review_after_bars) % extension_step_bars == 0
    ):
        if p_flat_8h < max(p_up_8h, p_down_8h):
            return "STOP_GRID_BOT", "grid_extension_rejected", {
                "held_bars": held_bars,
                "review_after_bars": review_after_bars,
                "p_flat_8h": p_flat_8h,
                "p_up_8h": p_up_8h,
                "p_down_8h": p_down_8h,
            }
    if max_holding_bars > 0 and held_bars is not None and held_bars >= max_holding_bars:
        return "STOP_GRID_BOT", "grid_max_lifetime_stop", {"held_bars": held_bars, "max_holding_bars": max_holding_bars}
    return None


def run_in_position_runtime(executor: Optional[OKXExecutor] = None) -> Dict[str, Any]:
    executor = executor or OKXExecutor()
    records = db.get_data("trade_decision_records", [])
    if not isinstance(records, list) or not records:
        return {"updated_count": 0, "record_count": 0, "actions": []}

    positions = _load_positions()
    snapshot_map = _latest_snapshot_map()
    updated_count = 0
    actions: List[Dict[str, Any]] = []

    for record in records:
        risk_review = record.get("riskReview") or {}
        execution = record.get("execution") or {}
        if risk_review.get("approved") is not True:
            continue
        if record.get("positionState") == "closed" or execution.get("order_status") == "CLOSED":
            continue
        if execution.get("execution_action") not in {"OPEN_LONG", "OPEN_SHORT", "START_GRID_BOT"}:
            continue

        if execution.get("execution_action") == "START_GRID_BOT":
            snapshot = snapshot_map.get(record.get("symbol"), record.get("snapshot", {}))
            held_bars = _bars_since(execution.get("executed_at") or record.get("created_at"))
            signal = _grid_runtime_signal(record, snapshot, held_bars)
            if signal is None:
                continue
            runtime_action, runtime_reason, runtime_detail = signal
            stop_order_id = _apply_stop_grid(executor, _normalize_symbol(record.get("symbol")), execution.get("exchange_algo_id"))
            execution["runtime_action"] = runtime_action
            execution["last_runtime_order_id"] = stop_order_id
            execution["runtime_reason"] = runtime_reason
            execution["sync_status"] = "STOP_REQUESTED"
            record["positionState"] = "exit_pending"
            _append_execution_event(record, "GRID_RUNTIME_EXIT_TRIGGERED", {
                **runtime_detail,
                "order_id": stop_order_id,
                "reason": runtime_reason,
            })
            actions.append({"decisionId": record.get("decisionId"), "action": runtime_action})
            record["execution"] = execution
            record["updated_at"] = _iso_now()
            updated_count += 1
            continue

        side = _normalize_side(risk_review.get("final_intent"))
        symbol = _normalize_symbol(record.get("symbol"))
        live_position = _match_live_position(record, positions)
        if live_position is None:
            continue

        changed = False
        current_price = _safe_float(live_position.get("currentPrice"))
        pnl_pct = _safe_float(live_position.get("pnlPercent"))
        entry_price = _safe_float(live_position.get("entryPrice"))
        distance_to_liq = _estimate_distance_to_liq(live_position)
        current_state = str(record.get("positionState") or "entered")

        if execution.get("order_status") != "FILLED":
            execution["order_status"] = "FILLED"
            execution["sync_status"] = "FILLED"
            execution["avg_fill_price"] = entry_price or execution.get("avg_fill_price")
            execution["filled_size"] = _safe_float(live_position.get("amount"))
            execution["filled_stop_loss"] = live_position.get("stopLoss")
            execution["filled_take_profit"] = live_position.get("takeProfit")
            execution["position_side"] = side
            _append_execution_event(record, "POSITION_FILLED", {
                "entry_price": entry_price,
                "amount": live_position.get("amount"),
            })
            changed = True

        snapshot = snapshot_map.get(record.get("symbol"), record.get("snapshot", {}))
        add_blocked = current_state in {"trailing", "defensive", "exit_pending"}
        if execution.get("add_allowed") != (not add_blocked):
            execution["add_allowed"] = not add_blocked
            _append_execution_event(record, "ADD_PERMISSION_UPDATED", {
                "add_allowed": not add_blocked,
                "position_state": current_state,
            })
            changed = True

        if distance_to_liq is not None:
            execution["distance_to_liq"] = distance_to_liq

        proposed_sl = execution.get("proposed_sl_price")
        proposed_tp = execution.get("proposed_tp_price")
        protection_status = str(execution.get("protection_status") or "")
        if (
            protection_status == "MISSING"
            and execution.get("runtime_action") != "REPAIR_PROTECTION"
            and (proposed_sl is not None or proposed_tp is not None)
        ):
            order_id = _apply_adjustment(executor, symbol, side, proposed_sl, proposed_tp)
            execution["runtime_action"] = "REPAIR_PROTECTION"
            execution["last_runtime_order_id"] = order_id
            execution["runtime_reason"] = "missing_protection_orders"
            execution["protection_status"] = "PENDING_SYNC"
            _append_execution_event(record, "PROTECTION_REPAIR_TRIGGERED", {
                "stop_loss": proposed_sl,
                "take_profit": proposed_tp,
                "order_id": order_id,
            })
            actions.append({"decisionId": record.get("decisionId"), "action": "REPAIR_PROTECTION"})
            changed = True

        weakened, weakened_reason = _thesis_weakened(record, snapshot, live_position, side)
        defensive_since = execution.get("defensive_since")
        defensive_bars = _bars_since(defensive_since) if defensive_since else None
        max_holding_bars = int((risk_review or {}).get("max_holding_bars") or 0)
        held_bars = _holding_bars(record, live_position)

        if execution.get("runtime_action") == "REPAIR_PROTECTION":
            pass
        elif distance_to_liq is not None and distance_to_liq <= LIQ_CLOSE_THRESHOLD:
            close_order_id = _apply_close(executor, symbol, side, live_position)
            execution["runtime_action"] = "CLOSE_POSITION"
            execution["last_runtime_order_id"] = close_order_id
            execution["runtime_reason"] = "liq_close_threshold"
            record["positionState"] = "exit_pending"
            _append_execution_event(record, "LIQUIDATION_CLOSE_TRIGGERED", {
                "distance_to_liq": distance_to_liq,
                "order_id": close_order_id,
            })
            actions.append({"decisionId": record.get("decisionId"), "action": "CLOSE_POSITION"})
            changed = True
        elif distance_to_liq is not None and distance_to_liq <= LIQ_REDUCE_THRESHOLD:
            reduce_order_id = _apply_reduce(executor, symbol, side, 0.50, live_position)
            execution["runtime_action"] = "REDUCE_50"
            execution["last_runtime_order_id"] = reduce_order_id
            execution["runtime_reason"] = "liq_reduce_threshold"
            record["positionState"] = "defensive"
            execution["defensive_since"] = execution.get("defensive_since") or _iso_now()
            _append_execution_event(record, "LIQUIDATION_REDUCE_TRIGGERED", {
                "distance_to_liq": distance_to_liq,
                "order_id": reduce_order_id,
            })
            actions.append({"decisionId": record.get("decisionId"), "action": "REDUCE_50"})
            changed = True
        elif weakened and current_state not in {"defensive", "exit_pending"}:
            reduce_order_id = _apply_reduce(executor, symbol, side, THESIS_WEAKENED_REDUCE_RATIO, live_position)
            execution["runtime_action"] = "REDUCE_25"
            execution["last_runtime_order_id"] = reduce_order_id
            execution["runtime_reason"] = weakened_reason
            record["positionState"] = "defensive"
            execution["defensive_since"] = execution.get("defensive_since") or _iso_now()
            _append_execution_event(record, "THESIS_WEAKENED_TRIGGERED", {
                "reason": weakened_reason,
                "order_id": reduce_order_id,
            })
            actions.append({"decisionId": record.get("decisionId"), "action": "REDUCE_25"})
            changed = True
        elif current_state == "defensive" and defensive_bars is not None and defensive_bars >= DEFENSIVE_TIMEOUT_BARS:
            close_order_id = _apply_close(executor, symbol, side, live_position)
            execution["runtime_action"] = "CLOSE_POSITION"
            execution["last_runtime_order_id"] = close_order_id
            execution["runtime_reason"] = "defensive_timeout"
            record["positionState"] = "exit_pending"
            _append_execution_event(record, "DEFENSIVE_TIMEOUT_TRIGGERED", {
                "defensive_bars": defensive_bars,
                "order_id": close_order_id,
            })
            actions.append({"decisionId": record.get("decisionId"), "action": "CLOSE_POSITION"})
            changed = True
        elif _is_f_blueprint(record):
            f_exit = _f_runtime_exit(record, snapshot, live_position, side)
            if f_exit is not None:
                runtime_action, runtime_reason = f_exit
                close_order_id = _apply_close(executor, symbol, side, live_position)
                execution["runtime_action"] = runtime_action
                execution["last_runtime_order_id"] = close_order_id
                execution["runtime_reason"] = runtime_reason
                record["positionState"] = "exit_pending"
                _append_execution_event(record, "F_RUNTIME_EXIT_TRIGGERED", {
                    "reason": runtime_reason,
                    "current_price": current_price,
                    "order_id": close_order_id,
                })
                actions.append({"decisionId": record.get("decisionId"), "action": runtime_action})
                changed = True
        elif _evaluate_invalidation(record, snapshot, live_position):
            close_order_id = _apply_close(executor, symbol, side, live_position)
            execution["runtime_action"] = "CLOSE_POSITION"
            execution["last_runtime_order_id"] = close_order_id
            execution["runtime_reason"] = "candidate_invalidation"
            record["positionState"] = "exit_pending"
            _append_execution_event(record, "INVALIDATION_TRIGGERED", {
                "current_price": current_price,
                "order_id": close_order_id,
            })
            actions.append({"decisionId": record.get("decisionId"), "action": "CLOSE_POSITION"})
            changed = True
        elif max_holding_bars > 0 and held_bars is not None and held_bars >= max_holding_bars:
            close_order_id = _apply_close(executor, symbol, side, live_position)
            execution["runtime_action"] = "CLOSE_POSITION"
            execution["last_runtime_order_id"] = close_order_id
            execution["runtime_reason"] = "max_holding_bars_exceeded"
            record["positionState"] = "exit_pending"
            _append_execution_event(record, "MAX_HOLDING_BARS_TRIGGERED", {
                "held_bars": held_bars,
                "max_holding_bars": max_holding_bars,
                "order_id": close_order_id,
            })
            actions.append({"decisionId": record.get("decisionId"), "action": "CLOSE_POSITION"})
            changed = True
        else:
            current_sl = _existing_stop_loss(live_position, record)
            proposed_tp = execution.get("proposed_tp_price")

            if pnl_pct >= TRAILING_TRIGGER_PNL:
                if side == "LONG":
                    new_sl = round(current_price * (1 - TRAILING_STOP_BUFFER), 4)
                    should_update = current_sl is None or new_sl > current_sl
                else:
                    new_sl = round(current_price * (1 + TRAILING_STOP_BUFFER), 4)
                    should_update = current_sl is None or new_sl < current_sl
                if should_update:
                    order_id = _apply_adjustment(executor, symbol, side, new_sl, proposed_tp)
                    execution["active_stop_loss"] = new_sl
                    execution["last_runtime_order_id"] = order_id
                    execution["runtime_reason"] = "trailing_stop_rule"
                    record["positionState"] = "trailing"
                    _append_execution_event(record, "TRAILING_STOP_UPDATED", {
                        "new_stop_loss": new_sl,
                        "order_id": order_id,
                        "pnl_percent": pnl_pct,
                    })
                    actions.append({"decisionId": record.get("decisionId"), "action": "TRAILING_STOP_UPDATED"})
                    changed = True
            elif pnl_pct >= BREAK_EVEN_TRIGGER_PNL and entry_price > 0:
                if side == "LONG":
                    new_sl = entry_price
                    should_update = current_sl is None or new_sl > current_sl
                else:
                    new_sl = entry_price
                    should_update = current_sl is None or new_sl < current_sl
                if should_update:
                    order_id = _apply_adjustment(executor, symbol, side, new_sl, proposed_tp)
                    execution["active_stop_loss"] = new_sl
                    execution["last_runtime_order_id"] = order_id
                    execution["runtime_reason"] = "break_even_switch"
                    record["positionState"] = "entered"
                    _append_execution_event(record, "BREAK_EVEN_SWITCHED", {
                        "new_stop_loss": new_sl,
                        "order_id": order_id,
                        "pnl_percent": pnl_pct,
                    })
                    actions.append({"decisionId": record.get("decisionId"), "action": "BREAK_EVEN_SWITCHED"})
                    changed = True

        if changed:
            record["execution"] = execution
            record["updated_at"] = _iso_now()
            updated_count += 1

    db.save_data("trade_decision_records", records)
    if isinstance(records, list) and records:
        db.save_data("latest_trade_decision_record", records[0])

    return {
        "updated_count": updated_count,
        "record_count": len(records),
        "actions": actions[-50:],
    }
