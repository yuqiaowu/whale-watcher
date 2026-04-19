import pickle
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from qlib_config import QLIB_FEATURES

BASE_DIR = Path(__file__).resolve().parent
QLIB_DATA_DIR = BASE_DIR / "qlib_data"
CSV_PATH = QLIB_DATA_DIR / "multi_coin_features.csv"
MODEL_PATH = QLIB_DATA_DIR / "direction_model_8h.pkl"

LABELS = ["DOWN", "FLAT", "UP"]
LABEL_TO_INT = {label: idx for idx, label in enumerate(LABELS)}
INT_TO_LABEL = {idx: label for label, idx in LABEL_TO_INT.items()}


def compute_future_8h_labels(df: pd.DataFrame, up_threshold: float = 0.012, down_threshold: float = -0.012) -> pd.DataFrame:
    ordered = df.sort_values(["instrument", "datetime"]).copy()
    ordered["future_8h_ret"] = (
        ordered.groupby("instrument")["close"].shift(-2) / ordered["close"] - 1.0
    )

    def _classify(ret: float) -> Optional[str]:
        if pd.isna(ret):
            return None
        if ret > up_threshold:
            return "UP"
        if ret < down_threshold:
            return "DOWN"
        return "FLAT"

    ordered["direction_label_8h"] = ordered["future_8h_ret"].apply(_classify)
    return ordered


def train_direction_model() -> Dict[str, object]:
    from lightgbm import LGBMClassifier

    df = pd.read_csv(CSV_PATH)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = compute_future_8h_labels(df)
    df = df.dropna(subset=["direction_label_8h"]).copy()

    feature_cols = [col for col in QLIB_FEATURES if col in df.columns]
    train_end = df["datetime"].quantile(0.80)
    valid_end = df["datetime"].quantile(0.90)

    train_df = df[df["datetime"] <= train_end]
    valid_df = df[(df["datetime"] > train_end) & (df["datetime"] <= valid_end)]
    test_df = df[df["datetime"] > valid_end]

    X_train = train_df[feature_cols].fillna(0.0)
    y_train = train_df["direction_label_8h"].map(LABEL_TO_INT)
    X_valid = valid_df[feature_cols].fillna(0.0)
    y_valid = valid_df["direction_label_8h"].map(LABEL_TO_INT)
    X_test = test_df[feature_cols].fillna(0.0)
    y_test = test_df["direction_label_8h"].map(LABEL_TO_INT)

    model = LGBMClassifier(
        objective="multiclass",
        num_class=3,
        n_estimators=120,
        learning_rate=0.05,
        max_depth=5,
        num_leaves=31,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
    )
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_valid, y_valid)] if not X_valid.empty else None,
        eval_metric="multi_logloss",
    )

    payload = {
        "model": model,
        "feature_cols": feature_cols,
        "labels": LABELS,
        "meta": {
            "target": "future_8h_direction",
            "up_threshold": 0.012,
            "down_threshold": -0.012,
            "train_rows": int(len(train_df)),
            "valid_rows": int(len(valid_df)),
            "test_rows": int(len(test_df)),
            "test_accuracy": float(model.score(X_test, y_test)) if not X_test.empty else None,
        },
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(payload, f)
    return payload["meta"]


def load_direction_model() -> Optional[Dict[str, object]]:
    if not MODEL_PATH.exists():
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict_direction_probabilities(feature_frame: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    bundle = load_direction_model()
    if bundle is None:
        return {}

    model = bundle["model"]
    feature_cols = bundle["feature_cols"]
    available_cols = [col for col in feature_cols if col in feature_frame.columns]
    X = feature_frame[available_cols].copy()
    for col in feature_cols:
        if col not in X.columns:
            X[col] = 0.0
    X = X[feature_cols].fillna(0.0)

    probs = model.predict_proba(X)
    result: Dict[str, Dict[str, float]] = {}
    for idx, (instrument, _) in enumerate(feature_frame.iterrows()):
        p_down, p_flat, p_up = probs[idx]
        result[str(instrument)] = {
            "p_up_8h": round(float(p_up), 4),
            "p_down_8h": round(float(p_down), 4),
            "p_flat_8h": round(float(p_flat), 4),
            "confidence_8h": round(float(max(p_up, p_down)), 4),
        }
    return result


def heuristic_direction_probabilities(feature_frame: pd.DataFrame, score_series: pd.Series) -> Dict[str, Dict[str, float]]:
    if feature_frame.empty:
        return {}
    mean_score = float(score_series.mean()) if len(score_series) else 0.0
    std_score = float(score_series.std()) if len(score_series) > 1 else 0.0
    denom = std_score if std_score > 1e-8 else 1.0
    result: Dict[str, Dict[str, float]] = {}
    for instrument, row in feature_frame.iterrows():
        rel = float(score_series.loc[instrument])
        z = (rel - mean_score) / denom
        directional = 1.0 / (1.0 + np.exp(-z))
        momentum = float(row.get("momentum_12", 0.0))
        ret = float(row.get("ret", 0.0))
        bias = max(min((momentum + ret) * 8.0, 0.15), -0.15)
        p_up = max(min(directional + bias, 0.90), 0.05)
        p_down = max(min((1.0 - directional) - bias, 0.90), 0.05)
        flat_mass = max(0.05, 1.0 - (p_up + p_down))
        norm = p_up + p_down + flat_mass
        p_up /= norm
        p_down /= norm
        p_flat = flat_mass / norm
        result[str(instrument)] = {
            "p_up_8h": round(float(p_up), 4),
            "p_down_8h": round(float(p_down), 4),
            "p_flat_8h": round(float(p_flat), 4),
            "confidence_8h": round(float(max(p_up, p_down)), 4),
        }
    return result
