import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "backend" / "qlib_data" / "multi_coin_features.csv"
OUTPUT_PATH = ROOT / "backend" / "backtest_results" / "a_strategy_backtest.json"


CONFIG = {
    "enabled_blueprints": ["Blueprint_A2"],
    "a2_enabled_instruments": ["BNB", "BTC", "SOL"],
    "wick_threshold_pct": 30.0,
    "a2_rsi_min": 60.0,
    "regime_fast_ma": "ma_20",
    "regime_slow_ma": "ma_60",
}


@dataclass
class TradeRecord:
    instrument: str
    side: str
    trigger: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    stop_price: float
    take_profit_price: float
    return_pct: float
    exit_reason: str
    bars_held: int


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["datetime"])
    df = df.sort_values(["instrument", "datetime"]).copy()
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    full_range = (out["high"] - out["low"]).replace(0, 1e-9)
    body_top = out[["open", "close"]].max(axis=1)
    body_bottom = out[["open", "close"]].min(axis=1)
    out["wick_ratio_upper_pct"] = ((out["high"] - body_top) / full_range) * 100.0
    out["wick_ratio_lower_pct"] = ((body_bottom - out["low"]) / full_range) * 100.0
    fast = CONFIG["regime_fast_ma"]
    slow = CONFIG["regime_slow_ma"]
    out["regime_proxy"] = np.where(out[fast] > out[slow], "BULL", np.where(out[fast] < out[slow], "BEAR", "NEUTRAL"))
    return out


def short_entry(row: pd.Series) -> bool:
    return bool(
        row["wick_ratio_upper_pct"] >= CONFIG["wick_threshold_pct"]
        and row["rsi_14"] >= CONFIG["a2_rsi_min"]
        and row["regime_proxy"] == "BEAR"
    )


def simulate_trade(df: pd.DataFrame, start_idx: int, side: str) -> Optional[TradeRecord]:
    if start_idx >= len(df):
        return None

    signal_row = df.iloc[start_idx - 1]
    entry_bar = df.iloc[start_idx]
    entry_price = float(entry_bar["open"])
    atr = float(signal_row["atr_14"])
    if not np.isfinite(atr) or atr <= 0:
        return None

    if side == "LONG":
        trigger_low = round(float(signal_row["close"]) - atr * 0.5, 4)
        stop_price = round(trigger_low * 0.998, 4)
        take_profit_price = round(entry_price + max(entry_price - stop_price, atr) * 2.0, 4)
    else:
        trigger_high = round(float(signal_row["close"]) + atr * 0.5, 4)
        stop_price = round(trigger_high * 1.002, 4)
        take_profit_price = round(entry_price - max(stop_price - entry_price, atr) * 2.0, 4)

    exit_price = float(df.iloc[-1]["close"])
    exit_idx = len(df) - 1
    exit_reason = "END_OF_DATA"

    for idx in range(start_idx, len(df)):
        bar = df.iloc[idx]
        high = float(bar["high"])
        low = float(bar["low"])

        if side == "LONG":
            stop_hit = low <= stop_price
            tp_hit = high >= take_profit_price
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

    ret = (exit_price - entry_price) / entry_price if side == "LONG" else (entry_price - exit_price) / entry_price
    return TradeRecord(
        instrument=str(entry_bar["instrument"]),
        side=side,
        trigger="Blueprint_A2",
        entry_time=str(entry_bar["datetime"]),
        exit_time=str(df.iloc[exit_idx]["datetime"]),
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=stop_price,
        take_profit_price=take_profit_price,
        return_pct=ret * 100.0,
        exit_reason=exit_reason,
        bars_held=max(exit_idx - start_idx + 1, 0),
    )


def run_backtest() -> Dict:
    df = enrich(load_dataset())
    trades: List[TradeRecord] = []

    for instrument, g in df.groupby("instrument"):
        g = g.sort_values("datetime").reset_index(drop=True)
        i = 1
        while i < len(g):
            signal_row = g.iloc[i - 1]
            trade: Optional[TradeRecord] = None
            if (
                "Blueprint_A2" in CONFIG["enabled_blueprints"]
                and instrument in CONFIG["a2_enabled_instruments"]
                and short_entry(signal_row)
            ):
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
    for instrument, group in pd.DataFrame(trade_dicts).groupby("instrument") if trade_dicts else []:
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
