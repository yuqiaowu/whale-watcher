from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "backend" / "qlib_data" / "multi_coin_features.csv"
MODEL_PATH = ROOT / "backend" / "qlib_data" / "direction_model_8h.pkl"
OUTPUT_PATH = ROOT / "backend" / "backtest_results" / "e_strategy_backtest.json"


CONFIG = {
    "tracked_instruments": ["BNB", "BTC", "DOGE", "ETH", "SOL"],
    "qlib_rank_bucket_size": 3,
    "qlib_prob_threshold": 0.55,
    "qlib_prob_gap_threshold": 0.15,
    "qlib_flat_max_threshold": 0.40,
    "qlib_invalidation_prob_threshold": 0.45,
    "rsi_bull_threshold": 55.0,
    "rsi_bear_threshold": 45.0,
    "funding_extreme_positive": 2.0,
    "funding_extreme_negative": -2.0,
    "stop_atr_multiple": 2.0,
    "take_profit_r_multiple": 2.0,
    "require_entry_on_next_open": True,
}


@dataclass
class TradeRecord:
    instrument: str
    side: str
    trigger: str
    signal_time: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    stop_price: float
    take_profit_price: float
    return_pct: float
    exit_reason: str
    bars_held: int
    p_up_8h: float
    p_down_8h: float
    p_flat_8h: float
    regime_1d: str


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["datetime"])
    df = df[df["instrument"].isin(CONFIG["tracked_instruments"])].copy()
    return df.sort_values(["datetime", "instrument"]).reset_index(drop=True)


def load_direction_bundle() -> Dict:
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def add_direction_outputs(df: pd.DataFrame) -> pd.DataFrame:
    bundle = load_direction_bundle()
    feature_cols = bundle["feature_cols"]
    labels = bundle["labels"]
    label_to_idx = {label: idx for idx, label in enumerate(labels)}
    model = bundle["model"]

    features = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    probabilities = model.predict_proba(features)
    out = df.copy()
    out["p_down_8h"] = probabilities[:, label_to_idx["DOWN"]]
    out["p_flat_8h"] = probabilities[:, label_to_idx["FLAT"]]
    out["p_up_8h"] = probabilities[:, label_to_idx["UP"]]
    out["confidence_8h"] = out[["p_up_8h", "p_down_8h"]].max(axis=1)
    out["future_8h_ret"] = out.groupby("instrument")["close"].shift(-2) / out["close"] - 1.0

    out["qlib_rank_up"] = out.groupby("datetime")["p_up_8h"].rank(method="first", ascending=False)
    out["qlib_rank_down"] = out.groupby("datetime")["p_down_8h"].rank(method="first", ascending=False)
    total = len(CONFIG["tracked_instruments"])
    out["qlib_top_bucket"] = out["qlib_rank_up"] <= CONFIG["qlib_rank_bucket_size"]
    out["qlib_bottom_bucket"] = out["qlib_rank_down"] <= CONFIG["qlib_rank_bucket_size"]
    out["qlib_rank_8h"] = np.where(
        out["p_up_8h"] >= out["p_down_8h"],
        out["qlib_rank_up"],
        total - out["qlib_rank_down"] + 1,
    )
    return out


def derive_regime_1d(row: pd.Series) -> str:
    rsi = float(row["rsi_14"])
    if rsi >= CONFIG["rsi_bull_threshold"]:
        return "BULL"
    if rsi <= CONFIG["rsi_bear_threshold"]:
        return "BEAR"
    return "CHOP"


def long_signal(row: pd.Series) -> bool:
    regime = row["regime_1d"]
    funding_z = float(row.get("funding_rate_zscore", 0.0) or 0.0)
    is_overheated = float(row.get("rsi_14", 50.0)) > 70.0
    return bool(
        row["qlib_top_bucket"]
        and row["p_up_8h"] >= CONFIG["qlib_prob_threshold"]
        and (row["p_up_8h"] - row["p_down_8h"]) >= CONFIG["qlib_prob_gap_threshold"]
        and row["p_flat_8h"] <= CONFIG["qlib_flat_max_threshold"]
        and regime != "BEAR"
        and not is_overheated
        and funding_z < CONFIG["funding_extreme_positive"]
    )


def short_signal(row: pd.Series) -> bool:
    regime = row["regime_1d"]
    funding_z = float(row.get("funding_rate_zscore", 0.0) or 0.0)
    return bool(
        row["qlib_bottom_bucket"]
        and row["p_down_8h"] >= CONFIG["qlib_prob_threshold"]
        and (row["p_down_8h"] - row["p_up_8h"]) >= CONFIG["qlib_prob_gap_threshold"]
        and row["p_flat_8h"] <= CONFIG["qlib_flat_max_threshold"]
        and regime != "BULL"
        and funding_z > CONFIG["funding_extreme_negative"]
    )


def simulate_trade(g: pd.DataFrame, signal_idx: int, side: str) -> Optional[TradeRecord]:
    entry_idx = signal_idx + 1 if CONFIG["require_entry_on_next_open"] else signal_idx
    if entry_idx >= len(g):
        return None

    signal_row = g.iloc[signal_idx]
    entry_row = g.iloc[entry_idx]
    atr = float(signal_row["atr_14"])
    if not np.isfinite(atr) or atr <= 0:
        return None

    entry_price = float(entry_row["open"] if CONFIG["require_entry_on_next_open"] else signal_row["close"])
    risk = CONFIG["stop_atr_multiple"] * atr
    if side == "LONG":
        stop_price = round(entry_price - risk, 4)
        take_profit_price = round(entry_price + risk * CONFIG["take_profit_r_multiple"], 4)
    else:
        stop_price = round(entry_price + risk, 4)
        take_profit_price = round(entry_price - risk * CONFIG["take_profit_r_multiple"], 4)

    exit_price = float(g.iloc[-1]["close"])
    exit_idx = len(g) - 1
    exit_reason = "END_OF_DATA"

    for idx in range(entry_idx, len(g)):
        bar = g.iloc[idx]
        high = float(bar["high"])
        low = float(bar["low"])

        if side == "LONG":
            stop_hit = low <= stop_price
            tp_hit = high >= take_profit_price
        else:
            stop_hit = high >= stop_price
            tp_hit = low <= take_profit_price

        if stop_hit and tp_hit:
            exit_price = stop_price
            exit_idx = idx
            exit_reason = "STOP_LOSS"
            break
        if stop_hit:
            exit_price = stop_price
            exit_idx = idx
            exit_reason = "STOP_LOSS"
            break
        if tp_hit:
            exit_price = take_profit_price
            exit_idx = idx
            exit_reason = "TAKE_PROFIT"
            break

        if idx > entry_idx:
            if side == "LONG":
                if (
                    float(bar["p_up_8h"]) < CONFIG["qlib_invalidation_prob_threshold"]
                    or str(bar["regime_1d"]) == "BEAR"
                ):
                    exit_price = float(bar["close"])
                    exit_idx = idx
                    exit_reason = "INVALIDATION"
                    break
            else:
                if (
                    float(bar["p_down_8h"]) < CONFIG["qlib_invalidation_prob_threshold"]
                    or str(bar["regime_1d"]) == "BULL"
                ):
                    exit_price = float(bar["close"])
                    exit_idx = idx
                    exit_reason = "INVALIDATION"
                    break

    ret = (exit_price - entry_price) / entry_price if side == "LONG" else (entry_price - exit_price) / entry_price
    return TradeRecord(
        instrument=str(entry_row["instrument"]),
        side=side,
        trigger="Blueprint_E1" if side == "LONG" else "Blueprint_E2",
        signal_time=str(signal_row["datetime"]),
        entry_time=str(entry_row["datetime"]),
        exit_time=str(g.iloc[exit_idx]["datetime"]),
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=stop_price,
        take_profit_price=take_profit_price,
        return_pct=ret * 100.0,
        exit_reason=exit_reason,
        bars_held=max(exit_idx - entry_idx + 1, 0),
        p_up_8h=float(signal_row["p_up_8h"]),
        p_down_8h=float(signal_row["p_down_8h"]),
        p_flat_8h=float(signal_row["p_flat_8h"]),
        regime_1d=str(signal_row["regime_1d"]),
    )


def run_backtest() -> Dict:
    df = add_direction_outputs(load_dataset())
    df["regime_1d"] = df.apply(derive_regime_1d, axis=1)

    trades: List[TradeRecord] = []
    for instrument, g in df.groupby("instrument", sort=False):
        g = g.sort_values("datetime").reset_index(drop=True)
        i = 0
        while i < len(g) - 1:
            signal_row = g.iloc[i]
            trade: Optional[TradeRecord] = None
            if long_signal(signal_row):
                trade = simulate_trade(g, i, "LONG")
            elif short_signal(signal_row):
                trade = simulate_trade(g, i, "SHORT")

            if trade is None:
                i += 1
                continue

            trades.append(trade)
            exit_ts = pd.to_datetime(trade.exit_time)
            while i < len(g) and pd.to_datetime(g.iloc[i]["datetime"]) <= exit_ts:
                i += 1

    trade_dicts = [asdict(t) for t in trades]
    returns = pd.Series([t.return_pct / 100.0 for t in trades], dtype=float)
    equity = (1.0 + returns).cumprod() if not returns.empty else pd.Series(dtype=float)
    drawdown = (equity / equity.cummax() - 1.0) if not equity.empty else pd.Series(dtype=float)

    per_instrument = []
    if trade_dicts:
        trades_df = pd.DataFrame(trade_dicts)
        for instrument, group in trades_df.groupby("instrument"):
            g_returns = pd.Series(group["return_pct"] / 100.0, dtype=float)
            per_instrument.append(
                {
                    "instrument": instrument,
                    "trades": int(len(group)),
                    "win_rate": float((group["return_pct"] > 0).mean()),
                    "avg_return_pct": float(group["return_pct"].mean()),
                    "total_return_pct": float(((1.0 + g_returns).prod() - 1.0) * 100.0),
                    "final_equity": float((1.0 + g_returns).prod()),
                }
            )

    result = {
        "config": CONFIG,
        "dataset": {
            "path": str(DATA_PATH),
            "rows": int(len(df)),
            "instruments": sorted(df["instrument"].unique().tolist()),
            "start": str(df["datetime"].min()),
            "end": str(df["datetime"].max()),
            "direction_model_path": str(MODEL_PATH),
        },
        "assumptions": {
            "macro_not_backfilled": True,
            "regime_1d_proxy": "RSI proxy only: >=55 BULL, <=45 BEAR, otherwise CHOP",
            "flow_filters_not_used": True,
            "fees_and_slippage_included": False,
            "entry": "next_4h_open",
            "stop": "2 ATR",
            "take_profit": "2R",
            "invalidation": "p_up/p_down weakens below 0.45 or regime flips",
        },
        "portfolio": {
            "total_trades": int(len(trades)),
            "win_rate": float((returns > 0).mean()) if not returns.empty else 0.0,
            "final_equity": float(equity.iloc[-1]) if not equity.empty else 1.0,
            "total_return_pct": float((equity.iloc[-1] - 1.0) * 100.0) if not equity.empty else 0.0,
            "max_drawdown_pct": float(drawdown.min() * 100.0) if not drawdown.empty else 0.0,
        },
        "per_instrument": per_instrument,
        "sample_trades": trade_dicts[:20],
        "all_trades": trade_dicts,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    summary = run_backtest()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nSaved to {OUTPUT_PATH}")
