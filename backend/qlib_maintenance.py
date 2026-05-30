import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
QLIB_DATA_DIR = BASE_DIR / "qlib_data"
CSV_PATH = QLIB_DATA_DIR / "multi_coin_features.csv"
MODEL_PATH = QLIB_DATA_DIR / "model_latest.pkl"
MODEL_META_PATH = QLIB_DATA_DIR / "model_training_meta.json"


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _safe_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _run_script(script_name: str) -> None:
    subprocess.run([sys.executable, script_name], check=True, cwd=BASE_DIR)


def _latest_csv_datetime() -> Optional[str]:
    if not CSV_PATH.exists():
        return None
    try:
        df = pd.read_csv(CSV_PATH, usecols=["datetime"])
        if df.empty:
            return None
        latest = pd.to_datetime(df["datetime"], errors="coerce").dropna().max()
        if pd.isna(latest):
            return None
        return pd.Timestamp(latest).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _load_model_meta() -> Dict[str, Any]:
    if not MODEL_META_PATH.exists():
        return {}
    try:
        with MODEL_META_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_timestamp(value: Any) -> Optional[pd.Timestamp]:
    if not value:
        return None
    try:
        parsed = pd.Timestamp(value)
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _model_train_lag_report(meta: Dict[str, Any], reference_value: Optional[str]) -> Dict[str, Any]:
    max_lag_days = _safe_int_env("QLIB_MODEL_MAX_TRAIN_LAG_DAYS", 7)
    train_end = _parse_timestamp(meta.get("train_end"))
    reference_ts = _parse_timestamp(reference_value)
    if reference_ts is None:
        reference_ts = pd.Timestamp(datetime.now())

    if train_end is None:
        return {
            "model_train_lag_days": None,
            "max_train_lag_days": max_lag_days,
            "train_reference_datetime": reference_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "model_train_lag_exceeded": True,
            "model_train_lag_reason": "train_end_missing_or_invalid",
        }

    lag_days = max((reference_ts.normalize() - train_end.normalize()).days, 0)
    return {
        "model_train_lag_days": lag_days,
        "max_train_lag_days": max_lag_days,
        "train_reference_datetime": reference_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "model_train_lag_exceeded": lag_days > max_lag_days,
        "model_train_lag_reason": "train_end_too_old" if lag_days > max_lag_days else "ok",
    }


def qlib_retrain_needed(now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    policy = os.getenv("QLIB_RETRAIN_POLICY", "weekly").lower()
    max_age_days = _safe_int_env("QLIB_MODEL_MAX_AGE_DAYS", 7)
    force = _env_enabled("FORCE_QILB_RETRAIN", False) or _env_enabled("FORCE_QLIB_RETRAIN", False)
    meta = _load_model_meta()
    csv_latest_datetime = _latest_csv_datetime()
    train_lag_report = _model_train_lag_report(meta, csv_latest_datetime)

    reasons = []
    model_mtime = None
    if MODEL_PATH.exists():
        model_mtime = datetime.fromtimestamp(MODEL_PATH.stat().st_mtime)
    else:
        reasons.append("model_missing")

    if force:
        reasons.append("forced")
    if train_lag_report.get("model_train_lag_exceeded"):
        reasons.append("model_train_lag_exceeded")
    if policy == "always":
        reasons.append("policy_always")
    elif policy == "never":
        reasons = [
            reason
            for reason in reasons
            if reason in {"model_missing", "forced", "model_train_lag_exceeded"}
        ]
    elif policy == "daily":
        if model_mtime is None or model_mtime.date() < now.date():
            reasons.append("daily_model_stale")
    elif policy == "weekly":
        if now.weekday() == 0 and (model_mtime is None or model_mtime.date() < now.date()):
            reasons.append("weekly_monday_refresh")
        elif model_mtime is not None and now - model_mtime > timedelta(days=max_age_days):
            reasons.append("model_age_exceeded")
    else:
        if model_mtime is not None and now - model_mtime > timedelta(days=max_age_days):
            reasons.append("model_age_exceeded")

    return {
        "needed": bool(reasons),
        "policy": policy,
        "reasons": sorted(set(reasons)),
        "model_mtime": model_mtime.isoformat(timespec="seconds") if model_mtime else None,
        "model_meta": meta,
        "csv_latest_datetime": csv_latest_datetime,
        **train_lag_report,
    }


def refresh_qlib_before_decision() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "enabled": _env_enabled("REFRESH_QLIB_BEFORE_V2", True),
        "data_updated": False,
        "retrain": None,
        "retrained": False,
        "inference_ok": False,
    }
    if not report["enabled"]:
        return report

    _run_script("update_qlib_data.py")
    report["data_updated"] = True

    retrain_report = qlib_retrain_needed()
    report["retrain"] = retrain_report
    if retrain_report.get("needed"):
        _run_script("train_local_brain.py")
        _run_script("direction_model.py")
        report["retrained"] = True

    _run_script("inference_qlib_model.py")
    report["inference_ok"] = True
    return report


if __name__ == "__main__":
    print(json.dumps(refresh_qlib_before_decision(), ensure_ascii=False, indent=2))
