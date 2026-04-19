import json
import os
import subprocess
import sys

from deterministic_pipeline import run_deterministic_cycle
from execution_reconciliation import run_execution_reconciliation
from okx_executor import OKXExecutor
from position_runtime import run_in_position_runtime


def _run_script(script_name: str) -> None:
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(backend_dir, script_name)
    subprocess.run([sys.executable, script_path], check=True, cwd=backend_dir)


def _refresh_qlib_if_enabled() -> bool:
    refresh_enabled = os.getenv("REFRESH_QLIB_BEFORE_V2", "1").lower() in {"1", "true", "yes"}
    if not refresh_enabled:
        return False
    _run_script("update_qlib_data.py")
    _run_script("inference_qlib_model.py")
    return True


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
