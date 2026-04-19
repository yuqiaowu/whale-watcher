import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from qlib_config import QLIB_FEATURES  # noqa: E402


def analyze_direction_model() -> dict:
    bundle = joblib.load(BASE_DIR / "qlib_data" / "direction_model_8h.pkl")
    model = bundle["model"]
    feature_cols = bundle["feature_cols"]
    labels = bundle["labels"]
    label_to_idx = {label: idx for idx, label in enumerate(labels)}

    df = pd.read_csv(BASE_DIR / "qlib_data" / "multi_coin_features.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values(["datetime", "instrument"]).reset_index(drop=True)

    features = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    probabilities = model.predict_proba(features)

    df["p_down_8h"] = probabilities[:, label_to_idx["DOWN"]]
    df["p_flat_8h"] = probabilities[:, label_to_idx["FLAT"]]
    df["p_up_8h"] = probabilities[:, label_to_idx["UP"]]
    df["future_8h_ret"] = df.groupby("instrument")["close"].shift(-2) / df["close"] - 1.0
    valid = df.dropna(subset=["future_8h_ret"]).copy()

    result = {
        "dist": {
            "p_up": valid["p_up_8h"].describe(percentiles=[0.10, 0.25, 0.50, 0.75, 0.90, 0.95]).round(4).to_dict(),
            "p_down": valid["p_down_8h"].describe(percentiles=[0.10, 0.25, 0.50, 0.75, 0.90, 0.95]).round(4).to_dict(),
            "p_flat": valid["p_flat_8h"].describe(percentiles=[0.10, 0.25, 0.50, 0.75, 0.90, 0.95]).round(4).to_dict(),
        },
        "threshold_scan": [],
        "bucket_scan": [],
    }

    for threshold in [0.50, 0.52, 0.55, 0.58, 0.60]:
        longs = valid[(valid["p_up_8h"] >= threshold) & ((valid["p_up_8h"] - valid["p_down_8h"]) >= 0.10)]
        shorts = valid[(valid["p_down_8h"] >= threshold) & ((valid["p_down_8h"] - valid["p_up_8h"]) >= 0.10)]
        result["threshold_scan"].append({
            "threshold": threshold,
            "long_count": int(len(longs)),
            "short_count": int(len(shorts)),
            "long_hit_rate": None if len(longs) == 0 else round(float((longs["future_8h_ret"] > 0.012).mean()), 4),
            "short_hit_rate": None if len(shorts) == 0 else round(float((shorts["future_8h_ret"] < -0.012).mean()), 4),
            "long_avg_future_ret": None if len(longs) == 0 else round(float(longs["future_8h_ret"].mean()), 4),
            "short_avg_future_ret_if_short": None if len(shorts) == 0 else round(float((-shorts["future_8h_ret"]).mean()), 4),
        })

        trades = []
        for _, group in valid.groupby("datetime"):
            group = group.copy()
            group["rank_up"] = group["p_up_8h"].rank(method="first", ascending=False)
            group["rank_down"] = group["p_down_8h"].rank(method="first", ascending=False)
            candidate_longs = group[(group["rank_up"] <= 3) & (group["p_up_8h"] >= threshold) & ((group["p_up_8h"] - group["p_down_8h"]) >= 0.10)]
            candidate_shorts = group[(group["rank_down"] <= 3) & (group["p_down_8h"] >= threshold) & ((group["p_down_8h"] - group["p_up_8h"]) >= 0.10)]

            for _, row in candidate_longs.iterrows():
                trades.append(("LONG", float(row["future_8h_ret"])))
            for _, row in candidate_shorts.iterrows():
                trades.append(("SHORT", float(row["future_8h_ret"])))

        long_rets = [ret for side, ret in trades if side == "LONG"]
        short_rets = [-ret for side, ret in trades if side == "SHORT"]
        result["bucket_scan"].append({
            "threshold": threshold,
            "trade_count": len(trades),
            "long_count": len(long_rets),
            "short_count": len(short_rets),
            "long_win_rate": None if not long_rets else round(sum(ret > 0.012 for ret in long_rets) / len(long_rets), 4),
            "short_win_rate": None if not short_rets else round(sum(ret > 0.012 for ret in short_rets) / len(short_rets), 4),
            "avg_return_per_trade": None if not trades else round(float(np.mean(long_rets + short_rets)), 4),
        })

    return result


if __name__ == "__main__":
    print(json.dumps(analyze_direction_model(), indent=2, ensure_ascii=False))
