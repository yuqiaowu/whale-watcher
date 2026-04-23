import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from db_client import db
from deterministic_pipeline import TRACKED_SYMBOLS, run_deterministic_cycle
from execution_reconciliation import run_execution_reconciliation
from okx_executor import OKXExecutor
from position_runtime import run_in_position_runtime
from post_trade_review import run_post_trade_review


REQUIRED_RECORD_SECTIONS = [
    "snapshot",
    "candidate",
    "ruleEvaluation",
    "researchOutput",
    "riskReview",
    "execution",
    "evaluation",
]


def _run_script(script_name: str) -> None:
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(backend_dir, script_name)
    subprocess.run([sys.executable, script_path], check=True, cwd=backend_dir)


def _refresh_qlib_if_enabled(refresh_qlib: Optional[bool] = None) -> bool:
    if refresh_qlib is None:
        refresh_qlib = os.getenv("REFRESH_QLIB_BEFORE_V2", "1").lower() in {"1", "true", "yes"}
    if not refresh_qlib:
        return False
    _run_script("update_qlib_data.py")
    _run_script("inference_qlib_model.py")
    return True


def _check(name: str, passed: bool, detail: Any) -> Dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "detail": detail,
    }


def _validate_record(record: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for key in REQUIRED_RECORD_SECTIONS:
        if key not in record or record.get(key) in (None, {}):
            if key == "researchOutput":
                continue
            issues.append(f"missing_{key}")

    snapshot = record.get("snapshot") or {}
    candidate = record.get("candidate") or {}
    rule_evaluation = record.get("ruleEvaluation") or {}
    research_output = record.get("researchOutput") or {}
    risk_review = record.get("riskReview") or {}
    execution = record.get("execution") or {}
    evaluation = record.get("evaluation") or {}

    if not record.get("decisionId"):
        issues.append("missing_decisionId")
    if snapshot.get("cycleId") != record.get("cycleId"):
        issues.append("cycle_mismatch")
    if snapshot.get("symbol") != record.get("symbol"):
        issues.append("symbol_mismatch")
    if candidate.get("cycleId") != record.get("cycleId"):
        issues.append("candidate_cycle_mismatch")
    if rule_evaluation.get("cycleId") != record.get("cycleId"):
        issues.append("rule_cycle_mismatch")
    if risk_review.get("cycleId") != record.get("cycleId"):
        issues.append("risk_cycle_mismatch")
    if execution.get("cycleId") != record.get("cycleId"):
        issues.append("execution_cycle_mismatch")

    if "history" not in execution or not isinstance(execution.get("history"), list):
        issues.append("execution_history_missing")

    if risk_review.get("approved"):
        if execution.get("execution_action") == "DO_NOTHING":
            issues.append("approved_without_execution_action")
        if execution.get("requested_size_usd", 0) <= 0:
            issues.append("approved_without_size")
        if execution.get("requested_leverage", 0) <= 0:
            issues.append("approved_without_leverage")

    if not evaluation.get("result_label"):
        issues.append("evaluation_result_label_missing")
    if not evaluation.get("primary_cause"):
        issues.append("evaluation_primary_cause_missing")
    if "feedback_packets" not in evaluation:
        issues.append("evaluation_feedback_missing")

    proposals = (candidate.get("candidate_proposals") or []) if isinstance(candidate, dict) else []
    approved_candidates = (rule_evaluation.get("approved_candidates") or []) if isinstance(rule_evaluation, dict) else []

    if proposals and approved_candidates and not research_output:
        issues.append("missing_researchOutput")
    if research_output and not research_output.get("selected_intent"):
        issues.append("research_selected_intent_missing")
    if research_output:
        flow_alignment = research_output.get("flow_alignment")
        if flow_alignment not in {"SUPPORT", "NEUTRAL", "CONFLICT", "UNAVAILABLE"}:
            issues.append("research_flow_alignment_invalid")
        if not isinstance(research_output.get("flow_data_available"), bool):
            issues.append("research_flow_data_available_missing")

    return issues


def run_acceptance_check(
    executor: Optional[OKXExecutor] = None,
    refresh_qlib: Optional[bool] = None,
) -> Dict[str, Any]:
    qlib_refreshed = _refresh_qlib_if_enabled(refresh_qlib)
    executor = executor or OKXExecutor()

    cycle_result = run_deterministic_cycle(executor)
    reconciliation_summary = run_execution_reconciliation()
    runtime_summary = run_in_position_runtime(executor)
    review_summary = run_post_trade_review()

    records = db.get_data("trade_decision_records", [])
    latest_cycle = db.get_data("latest_decision_cycle_v2", {})
    latest_cycle_id = cycle_result.get("cycleId")
    latest_cycle_records = [
        record for record in records
        if record.get("cycleId") == latest_cycle_id
    ]

    checks: List[Dict[str, Any]] = []
    checks.append(_check(
        "cycle_bundle_written",
        isinstance(latest_cycle, dict) and latest_cycle.get("cycleId") == cycle_result.get("cycleId"),
        {
            "expected_cycleId": cycle_result.get("cycleId"),
            "actual_cycleId": (latest_cycle or {}).get("cycleId"),
        },
    ))
    checks.append(_check(
        "record_count_matches_symbols",
        len(latest_cycle_records) == len(TRACKED_SYMBOLS),
        {
            "latest_cycle_record_count": len(latest_cycle_records),
            "tracked_symbols": len(TRACKED_SYMBOLS),
        },
    ))
    decision_ids = [record.get("decisionId") for record in latest_cycle_records if record.get("decisionId")]
    checks.append(_check(
        "decision_ids_unique",
        len(decision_ids) == len(set(decision_ids)),
        {
            "decision_id_count": len(decision_ids),
            "unique_decision_id_count": len(set(decision_ids)),
        },
    ))
    checks.append(_check(
        "post_trade_review_ran",
        review_summary.get("record_count", 0) >= len(latest_cycle_records),
        review_summary,
    ))
    checks.append(_check(
        "execution_reconciliation_ran",
        "record_count" in reconciliation_summary,
        reconciliation_summary,
    ))
    checks.append(_check(
        "position_runtime_ran",
        "record_count" in runtime_summary,
        runtime_summary,
    ))

    record_issues: Dict[str, List[str]] = {}
    for record in latest_cycle_records:
        issues = _validate_record(record)
        if issues:
            record_issues[record.get("decisionId", "unknown")] = issues
    checks.append(_check(
        "record_structure_complete",
        not record_issues,
        record_issues or {"validated_records": len(latest_cycle_records)},
    ))

    approved_records = [record for record in latest_cycle_records if (record.get("riskReview") or {}).get("approved")]
    approved_with_real_actions = [
        record.get("decisionId")
        for record in approved_records
        if (record.get("execution") or {}).get("execution_action") not in {None, "", "DO_NOTHING"}
    ]
    checks.append(_check(
        "approved_records_have_execution_requests",
        len(approved_with_real_actions) == len(approved_records),
        {
            "approved_record_count": len(approved_records),
            "approved_with_execution_action": len(approved_with_real_actions),
        },
    ))

    passed = all(item["passed"] for item in checks)
    return {
        "passed": passed,
        "cycleId": latest_cycle_id,
        "qlib_refreshed": qlib_refreshed,
        "record_count": len(records),
        "latest_cycle_record_count": len(latest_cycle_records),
        "approved_symbols": [item["symbol"] for item in cycle_result.get("risk_reviews", []) if item.get("approved")],
        "checks": checks,
    }


if __name__ == "__main__":
    summary = run_acceptance_check()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(0 if summary.get("passed") else 1)
