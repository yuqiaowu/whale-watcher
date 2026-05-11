import json

from deterministic_pipeline import run_deterministic_cycle
from execution_reconciliation import run_execution_reconciliation
from okx_executor import OKXExecutor
from position_runtime import run_in_position_runtime
from qlib_maintenance import refresh_qlib_before_decision


def _refresh_qlib_if_enabled() -> bool:
    report = refresh_qlib_before_decision()
    return bool(report.get("enabled") and report.get("inference_ok"))


if __name__ == "__main__":
    qlib_refreshed = _refresh_qlib_if_enabled()
    executor = OKXExecutor()
    result = run_deterministic_cycle(executor)
    reconciliation_summary = run_execution_reconciliation()
    runtime_summary = run_in_position_runtime(executor)
    print(json.dumps({
        "cycleId": result.get("cycleId"),
        "qlib_refreshed": qlib_refreshed,
        "record_count": result.get("record_count"),
        "approved_symbols": [item["symbol"] for item in result.get("risk_reviews", []) if item.get("approved")],
        "post_trade_review": result.get("post_trade_review", {}),
        "execution_reconciliation": reconciliation_summary,
        "position_runtime": runtime_summary,
    }, indent=2, ensure_ascii=False))
