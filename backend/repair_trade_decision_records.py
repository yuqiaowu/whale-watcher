import argparse
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from db_client import db
from execution_reconciliation import run_execution_reconciliation


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _symbol(item: Dict[str, Any]) -> Optional[str]:
    value = item.get("symbol")
    return str(value) if value else None


def _by_symbol(items: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        symbol = _symbol(item)
        if symbol:
            result[symbol] = item
    return result


def _record_from_cycle(cycle: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
    existing_records = _by_symbol(cycle.get("records") or [])
    if symbol in existing_records:
        return deepcopy(existing_records[symbol])

    snapshots = _by_symbol(cycle.get("snapshots") or [])
    snapshot = snapshots.get(symbol)
    if not snapshot:
        return None

    candidate = _by_symbol(cycle.get("candidate_batches") or []).get(symbol, {})
    rule_evaluation = _by_symbol(cycle.get("rule_evaluations") or []).get(symbol, {})
    research_output = _by_symbol(cycle.get("research_outputs") or []).get(symbol)
    risk_review = _by_symbol(cycle.get("risk_reviews") or []).get(symbol, {})
    execution = _by_symbol(cycle.get("executions") or []).get(symbol, {})
    market_state = candidate.get("market_state") if isinstance(candidate, dict) else None
    model_decision = None
    if isinstance(candidate, dict):
        model_decision = candidate.get("modelDecision") or candidate.get("model_decision")

    now = _iso_now()
    created_at = execution.get("executed_at") or snapshot.get("snapshot_time") or cycle.get("generated_at") or now
    return {
        "decisionId": snapshot.get("decision_id") or f"{cycle.get('cycleId')}_{symbol.replace('-USDT', '')}",
        "cycleId": cycle.get("cycleId"),
        "symbol": symbol,
        "timeframe": snapshot.get("timeframe") or cycle.get("timeframe") or "4h",
        "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
        "snapshot_time": snapshot.get("snapshot_time"),
        "snapshot_time_local": snapshot.get("snapshot_time_local"),
        "local_timezone": snapshot.get("local_timezone") or cycle.get("local_timezone"),
        "positionState": risk_review.get("next_position_state", "approved" if risk_review.get("approved") else "candidate"),
        "snapshot": snapshot,
        "marketState": market_state,
        "modelDecision": model_decision,
        "candidate": candidate,
        "ruleEvaluation": rule_evaluation,
        "researchOutput": research_output,
        "riskReview": risk_review,
        "execution": execution,
        "evaluation": None,
        "created_at": created_at,
        "created_at_local": execution.get("executed_at_local") or snapshot.get("snapshot_time_local"),
        "updated_at": now,
        "updated_at_local": now,
        "provenance": {"source": "repair_trade_decision_records", "cycle_reconstruction": True},
    }


def _fetch_cycles_by_id(cycle_ids: Iterable[str]) -> List[Dict[str, Any]]:
    cycles: List[Dict[str, Any]] = []
    if not (getattr(db, "is_connected", False) and getattr(db, "db", None) is not None):
        return cycles
    for cycle_id in cycle_ids:
        if not cycle_id:
            continue
        try:
            cycle = db.db["decision_cycles_v2"].find_one({"cycleId": cycle_id}, {"_id": 0})
        except Exception as exc:
            print(f"⚠️ direct query failed for {cycle_id}: {exc}")
            continue
        if isinstance(cycle, dict):
            cycles.append(cycle)
    return cycles


def rebuild_records(
    limit_cycles: int = 20,
    symbols: Optional[List[str]] = None,
    cycle_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    cycles: List[Dict[str, Any]] = []
    if cycle_ids:
        cycles = _fetch_cycles_by_id(cycle_ids)
    elif getattr(db, "is_connected", False) and getattr(db, "db", None) is not None:
        try:
            cursor = (
                db.db["decision_cycles_v2"]
                .find({}, {"_id": 0})
                .sort("generated_at", -1)
                .limit(limit_cycles)
            )
            cycles = [cycle for cycle in cursor if isinstance(cycle, dict)]
        except Exception as exc:
            print(f"⚠️ direct decision_cycles_v2 query failed: {exc}. Falling back to db.get_data().")
    if not cycles:
        cycles = db.get_data("decision_cycles_v2", [])
    if not isinstance(cycles, list):
        cycles = []
    latest = db.get_data("latest_decision_cycle_v2", {})
    if isinstance(latest, dict) and latest:
        cycles.insert(0, latest)

    cycles.sort(key=lambda item: _parse_dt(item.get("generated_at")), reverse=True)
    selected_symbols = {symbol.upper() for symbol in symbols or []}
    records: List[Dict[str, Any]] = []
    seen = set()

    for cycle in cycles[:limit_cycles]:
        cycle_symbols = set()
        for key in ("records", "snapshots", "risk_reviews", "executions"):
            cycle_symbols.update(_by_symbol(cycle.get(key) or []).keys())
        for symbol in sorted(cycle_symbols):
            if selected_symbols and symbol.upper() not in selected_symbols and symbol.replace("-USDT", "").upper() not in selected_symbols:
                continue
            record = _record_from_cycle(cycle, symbol)
            if not record:
                continue
            decision_id = str(record.get("decisionId") or "")
            if not decision_id or decision_id in seen:
                continue
            seen.add(decision_id)
            records.append(record)

    records.sort(key=lambda item: _parse_dt(item.get("created_at")), reverse=True)
    return records


def merge_records(records: List[Dict[str, Any]], drop_adopted_duplicates: bool = False) -> int:
    if not (getattr(db, "is_connected", False) and getattr(db, "db", None) is not None):
        raise RuntimeError("MongoDB is not connected; refusing direct merge")
    collection = db.db["trade_decision_records"]
    changed = 0
    for record in records:
        decision_id = record.get("decisionId")
        if not decision_id:
            continue
        safe_record = deepcopy(record)
        safe_record.pop("_id", None)
        collection.replace_one({"decisionId": decision_id}, safe_record, upsert=True)
        changed += 1

        if not drop_adopted_duplicates:
            continue
        execution = safe_record.get("execution") or {}
        if execution.get("execution_action") not in {"OPEN_LONG", "OPEN_SHORT"}:
            continue
        side = "LONG" if execution.get("execution_action") == "OPEN_LONG" else "SHORT"
        collection.delete_many({
            "symbol": safe_record.get("symbol"),
            "provenance.adopted_live_position": True,
            "riskReview.final_intent": side,
            "execution.sync_status": "OPEN",
        })

    if records:
        latest = sorted(records, key=lambda item: _parse_dt(item.get("created_at")), reverse=True)[0]
        db.save_data("latest_trade_decision_record", latest)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild trade_decision_records from persisted decision cycles.")
    parser.add_argument("--limit-cycles", type=int, default=20)
    parser.add_argument("--symbols", nargs="*", default=None, help="Optional symbols, e.g. SOL or SOL-USDT")
    parser.add_argument("--cycle-ids", nargs="*", default=None, help="Optional exact cycle IDs to rebuild from")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--merge", action="store_true", help="Upsert rebuilt records by decisionId without replacing the collection")
    parser.add_argument("--drop-adopted-duplicates", action="store_true")
    parser.add_argument("--reconcile", action="store_true")
    args = parser.parse_args()

    records = rebuild_records(limit_cycles=args.limit_cycles, symbols=args.symbols, cycle_ids=args.cycle_ids)
    print(f"rebuilt_records={len(records)}")
    print("top_decision_ids=", [record.get("decisionId") for record in records[:10]])
    if args.write:
        db.save_data("trade_decision_records", records)
        if records:
            db.save_data("latest_trade_decision_record", records[0])
        print("wrote trade_decision_records")
    if args.merge:
        changed = merge_records(records, drop_adopted_duplicates=args.drop_adopted_duplicates)
        print(f"merged trade_decision_records={changed}")
    if args.reconcile:
        summary = run_execution_reconciliation()
        print("reconciliation=", summary)


if __name__ == "__main__":
    main()
