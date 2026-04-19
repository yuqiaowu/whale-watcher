from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "backend" / "qlib_data" / "multi_coin_features.csv"
OUTPUT_DIR = ROOT / "backend" / "backtest_results"
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class TradeRecord:
    instrument: str
    side: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    support_or_resistance: float
    return_pct: float
    exit_reason: str
    bars_held: int


@dataclass
class InstrumentStats:
    instrument: str
    trades: int
    win_rate: float
    avg_return_pct: float
    total_return_pct: float
    final_equity: float


DEFAULT_CONFIG = {
    "swing_lookback": 5,
    "stop_lookback": 12,
    "stop_atr_buffer": 0.5,
    "stop_require_sma50_confirm": True,
    "break_even_r_multiple": None,
    "trailing_start_r_multiple": None,
    "trailing_atr_multiple": None,
    "divergence_lookback": 8,
    "rsi_trend_mid": 50.0,
    "rsi_long_min": 50.0,
    "rsi_short_max": 50.0,
    "rsi_take_profit_long": 70.0,
    "rsi_take_profit_short": 30.0,
    "require_macd_hist_confirmation": False,
    "require_macd_zero_axis_confirmation": True,
    "adx_min": 0.0,
    "volume_ma_window": 60,
    "volume_ratio_min": 1.5,
    "structure_volume_confirm": True,
    "structure_volume_ratio_min": 1.5,
    "structure_volume_fallback_to_plain": True,
    "long_disabled_instruments": ["DOGE"],
    "short_disabled_instruments": [],
    "excluded_instruments": ["SOL", "BTC"],
}


def load_features(path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime"])
    return df.sort_values(["instrument", "datetime"]).reset_index(drop=True)


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr0 = (high - low).abs()
    tr1 = (high - close.shift(1)).abs()
    tr2 = (low - close.shift(1)).abs()
    tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)

    tr_ema = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = (
        100
        * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean()
        / tr_ema.replace(0, np.nan)
    )
    minus_di = (
        100
        * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean()
        / tr_ema.replace(0, np.nan)
    )

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx.fillna(0.0)


def compute_volume_confirmed_levels(
    lows: pd.Series,
    highs: pd.Series,
    rel_volume: pd.Series,
    lookback: int,
    min_volume_ratio: float,
    fallback_to_plain: bool,
) -> Tuple[pd.Series, pd.Series]:
    support_values: List[float] = []
    resistance_values: List[float] = []

    low_values = lows.astype(float).tolist()
    high_values = highs.astype(float).tolist()
    rel_volume_values = rel_volume.astype(float).tolist()

    for idx in range(len(low_values)):
        if idx < lookback:
            support_values.append(np.nan)
            resistance_values.append(np.nan)
            continue

        start = idx - lookback
        window_lows = low_values[start:idx]
        window_highs = high_values[start:idx]
        window_volumes = rel_volume_values[start:idx]
        confirmed_indexes = [
            i for i, volume_ratio in enumerate(window_volumes) if pd.notna(volume_ratio) and volume_ratio >= min_volume_ratio
        ]

        if confirmed_indexes:
            support_values.append(min(window_lows[i] for i in confirmed_indexes))
            resistance_values.append(max(window_highs[i] for i in confirmed_indexes))
            continue

        if fallback_to_plain:
            support_values.append(min(window_lows))
            resistance_values.append(max(window_highs))
        else:
            support_values.append(np.nan)
            resistance_values.append(np.nan)

    return pd.Series(support_values, index=lows.index), pd.Series(resistance_values, index=highs.index)


def add_chart_features(df: pd.DataFrame, cfg: Dict[str, float]) -> pd.DataFrame:
    out = df.copy()
    lookback = int(cfg["stop_lookback"])
    div_lookback = int(cfg["divergence_lookback"])
    volume_window = int(cfg["volume_ma_window"])
    out["adx_14"] = out.groupby("instrument", group_keys=False)[["high", "low", "close"]].apply(compute_adx)
    out["sma50_dynamic"] = out.groupby("instrument")["close"].transform(
        lambda s: s.rolling(50, min_periods=50).mean()
    )
    out["volume_ma_dynamic"] = out.groupby("instrument")["volume"].transform(
        lambda s: s.rolling(volume_window, min_periods=volume_window).mean()
    )
    out["rel_volume_dynamic"] = out["volume"] / out["volume_ma_dynamic"]

    if cfg.get("structure_volume_confirm", False):
        supports: List[pd.Series] = []
        resistances: List[pd.Series] = []
        min_volume_ratio = float(cfg["structure_volume_ratio_min"])
        fallback_to_plain = bool(cfg.get("structure_volume_fallback_to_plain", True))
        for _, instrument_df in out.groupby("instrument", sort=False):
            support_level, resistance_level = compute_volume_confirmed_levels(
                lows=instrument_df["low"],
                highs=instrument_df["high"],
                rel_volume=instrument_df["rel_volume_dynamic"],
                lookback=lookback,
                min_volume_ratio=min_volume_ratio,
                fallback_to_plain=fallback_to_plain,
            )
            supports.append(support_level)
            resistances.append(resistance_level)
        out["support_level"] = pd.concat(supports).sort_index()
        out["resistance_level"] = pd.concat(resistances).sort_index()
    else:
        out["support_level"] = out.groupby("instrument")["low"].transform(
            lambda s: s.shift(1).rolling(lookback, min_periods=lookback).min()
        )
        out["resistance_level"] = out.groupby("instrument")["high"].transform(
            lambda s: s.shift(1).rolling(lookback, min_periods=lookback).max()
        )

    prev_price_high = out.groupby("instrument")["high"].transform(
        lambda s: s.shift(1).rolling(div_lookback, min_periods=div_lookback).max()
    )
    prev_price_low = out.groupby("instrument")["low"].transform(
        lambda s: s.shift(1).rolling(div_lookback, min_periods=div_lookback).min()
    )
    prev_macd_high = out.groupby("instrument")["macd_hist"].transform(
        lambda s: s.shift(1).rolling(div_lookback, min_periods=div_lookback).max()
    )
    prev_macd_low = out.groupby("instrument")["macd_hist"].transform(
        lambda s: s.shift(1).rolling(div_lookback, min_periods=div_lookback).min()
    )

    out["bearish_divergence_4h"] = (out["high"] > prev_price_high) & (
        out["macd_hist"] < prev_macd_high
    )
    out["bullish_divergence_4h"] = (out["low"] < prev_price_low) & (
        out["macd_hist"] > prev_macd_low
    )

    diff = out["macd"] - out["macd_signal"]
    prev_diff = diff.groupby(out["instrument"]).shift(1)
    out["macd_cross_up"] = (diff > 0) & (prev_diff <= 0)
    out["macd_cross_down"] = (diff < 0) & (prev_diff >= 0)
    return out


def uptrend(row: pd.Series, cfg: Dict[str, float]) -> bool:
    return bool(row["rsi_14"] > cfg["rsi_trend_mid"])


def downtrend(row: pd.Series, cfg: Dict[str, float]) -> bool:
    return bool(row["rsi_14"] < cfg["rsi_trend_mid"])


def long_entry(row: pd.Series, cfg: Dict[str, float]) -> bool:
    if str(row["instrument"]) in set(cfg.get("long_disabled_instruments", [])):
        return False
    return bool(
        uptrend(row, cfg)
        and row["rsi_14"] >= cfg["rsi_long_min"]
        and row["macd_cross_up"]
        and (
            (not cfg["require_macd_hist_confirmation"])
            or row["macd_hist"] > 0
        )
        and (
            (not cfg["require_macd_zero_axis_confirmation"])
            or (row["macd"] > 0 and row["macd_signal"] > 0)
        )
        and row["adx_14"] >= cfg["adx_min"]
        and row["rel_volume_dynamic"] >= cfg["volume_ratio_min"]
    )


def short_entry(row: pd.Series, cfg: Dict[str, float]) -> bool:
    if str(row["instrument"]) in set(cfg.get("short_disabled_instruments", [])):
        return False
    return bool(
        downtrend(row, cfg)
        and row["rsi_14"] <= cfg["rsi_short_max"]
        and row["macd_cross_down"]
        and (
            (not cfg["require_macd_hist_confirmation"])
            or row["macd_hist"] < 0
        )
        and (
            (not cfg["require_macd_zero_axis_confirmation"])
            or (row["macd"] < 0 and row["macd_signal"] < 0)
        )
        and row["adx_14"] >= cfg["adx_min"]
        and row["rel_volume_dynamic"] >= cfg["volume_ratio_min"]
    )


def simulate_trade(df: pd.DataFrame, start_idx: int, side: str, cfg: Dict[str, float]) -> Optional[TradeRecord]:
    if start_idx >= len(df):
        return None

    signal_row = df.iloc[start_idx - 1]
    row = df.iloc[start_idx]
    entry_price = float(row["open"])
    stop_atr_buffer = float(cfg.get("stop_atr_buffer", 0.0))
    if side == "LONG":
        support_or_resistance = float(signal_row["support_level"]) - (stop_atr_buffer * float(signal_row["atr_14"]))
    else:
        support_or_resistance = float(signal_row["resistance_level"]) + (stop_atr_buffer * float(signal_row["atr_14"]))
    if np.isnan(support_or_resistance):
        return None
    initial_stop = support_or_resistance
    risk_distance = abs(entry_price - initial_stop)
    dynamic_stop = initial_stop
    highest_close = entry_price
    lowest_close = entry_price

    exit_price = float(df.iloc[-1]["close"])
    exit_idx = len(df) - 1
    exit_reason = "END_OF_DATA"

    for idx in range(start_idx, len(df)):
        bar = df.iloc[idx]
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        atr_14 = float(bar["atr_14"])

        if side == "LONG":
            highest_close = max(highest_close, close)
            be_multiple = cfg.get("break_even_r_multiple")
            trail_start = cfg.get("trailing_start_r_multiple")
            trail_atr = cfg.get("trailing_atr_multiple")
            if be_multiple is not None and risk_distance > 0 and close >= entry_price + float(be_multiple) * risk_distance:
                dynamic_stop = max(dynamic_stop, entry_price)
            if (
                trail_start is not None
                and trail_atr is not None
                and risk_distance > 0
                and close >= entry_price + float(trail_start) * risk_distance
            ):
                trailing_stop = highest_close - float(trail_atr) * atr_14
                dynamic_stop = max(dynamic_stop, trailing_stop)

            stop_hit = low <= dynamic_stop
            is_initial_stop = abs(dynamic_stop - initial_stop) < 1e-9
            stop_confirmed = (
                (not is_initial_stop)
                or (not cfg.get("stop_require_sma50_confirm", False))
                or close < float(bar["sma50_dynamic"])
            )
            if stop_hit and stop_confirmed:
                exit_price = dynamic_stop
                exit_idx = idx
                if dynamic_stop >= entry_price:
                    exit_reason = "TRAILING_OR_BREAK_EVEN_STOP"
                else:
                    exit_reason = "SUPPORT_BROKEN"
                break
            if (
                bar["rsi_14"] > cfg["rsi_take_profit_long"]
                and (bar["macd_cross_down"] or bool(bar["bearish_divergence_4h"]))
            ):
                exit_price = close
                exit_idx = idx
                exit_reason = "OVERBOUGHT_MOMENTUM_REVERSAL"
                break
        else:
            lowest_close = min(lowest_close, close)
            be_multiple = cfg.get("break_even_r_multiple")
            trail_start = cfg.get("trailing_start_r_multiple")
            trail_atr = cfg.get("trailing_atr_multiple")
            if be_multiple is not None and risk_distance > 0 and close <= entry_price - float(be_multiple) * risk_distance:
                dynamic_stop = min(dynamic_stop, entry_price)
            if (
                trail_start is not None
                and trail_atr is not None
                and risk_distance > 0
                and close <= entry_price - float(trail_start) * risk_distance
            ):
                trailing_stop = lowest_close + float(trail_atr) * atr_14
                dynamic_stop = min(dynamic_stop, trailing_stop)

            stop_hit = high >= dynamic_stop
            is_initial_stop = abs(dynamic_stop - initial_stop) < 1e-9
            stop_confirmed = (
                (not is_initial_stop)
                or (not cfg.get("stop_require_sma50_confirm", False))
                or close > float(bar["sma50_dynamic"])
            )
            if stop_hit and stop_confirmed:
                exit_price = dynamic_stop
                exit_idx = idx
                if dynamic_stop <= entry_price:
                    exit_reason = "TRAILING_OR_BREAK_EVEN_STOP"
                else:
                    exit_reason = "RESISTANCE_BROKEN"
                break
            if (
                bar["rsi_14"] < cfg["rsi_take_profit_short"]
                and (bar["macd_cross_up"] or bool(bar["bullish_divergence_4h"]))
            ):
                exit_price = close
                exit_idx = idx
                exit_reason = "OVERSOLD_MOMENTUM_REVERSAL"
                break

    if side == "LONG":
        ret = (exit_price - entry_price) / entry_price
    else:
        ret = (entry_price - exit_price) / entry_price

    return TradeRecord(
        instrument=str(row["instrument"]),
        side=side,
        entry_time=str(row["datetime"]),
        exit_time=str(df.iloc[exit_idx]["datetime"]),
        entry_price=entry_price,
        exit_price=exit_price,
        support_or_resistance=support_or_resistance,
        return_pct=ret * 100,
        exit_reason=exit_reason,
        bars_held=int(exit_idx - start_idx + 1),
    )


def backtest_instrument(df: pd.DataFrame, cfg: Dict[str, float]) -> Tuple[List[TradeRecord], InstrumentStats]:
    trades: List[TradeRecord] = []
    equity = 1.0
    idx = 1

    while idx < len(df):
        prev_row = df.iloc[idx - 1]
        signal = None
        if long_entry(prev_row, cfg):
            signal = "LONG"
        elif short_entry(prev_row, cfg):
            signal = "SHORT"

        if signal:
            trade = simulate_trade(df, idx, signal, cfg)
            if trade is None:
                idx += 1
                continue
            trades.append(trade)
            equity *= 1 + (trade.return_pct / 100.0)
            exit_time = pd.Timestamp(trade.exit_time)
            later = df.index[df["datetime"] > exit_time]
            idx = int(later[0]) if len(later) else len(df)
        else:
            idx += 1

    returns = np.array([t.return_pct for t in trades], dtype=float) if trades else np.array([])
    stats = InstrumentStats(
        instrument=str(df.iloc[0]["instrument"]),
        trades=len(trades),
        win_rate=float((returns > 0).mean()) if len(returns) else 0.0,
        avg_return_pct=float(returns.mean()) if len(returns) else 0.0,
        total_return_pct=(equity - 1.0) * 100.0,
        final_equity=equity,
    )
    return trades, stats


def build_portfolio_equity(trades_by_instrument: Dict[str, List[TradeRecord]], instruments: List[str]) -> pd.DataFrame:
    equities = {inst: 1.0 for inst in instruments}
    events = []
    for inst, trades in trades_by_instrument.items():
        for trade in trades:
            events.append((pd.Timestamp(trade.exit_time), inst, trade.return_pct / 100.0))
    events.sort(key=lambda x: x[0])

    rows = []
    for ts, inst, ret in events:
        equities[inst] *= 1 + ret
        rows.append({"datetime": ts, "portfolio_equity": float(np.mean(list(equities.values())))})
    return pd.DataFrame(rows)


def compute_max_drawdown(equity_curve: pd.DataFrame) -> float:
    if equity_curve.empty:
        return 0.0
    running_max = equity_curve["portfolio_equity"].cummax()
    drawdown = equity_curve["portfolio_equity"] / running_max - 1.0
    return float(drawdown.min() * 100)


def run_backtest(path: Path = DATA_PATH, config: Optional[Dict[str, float]] = None) -> Dict[str, object]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    raw = load_features(path)
    excluded = set(cfg.get("excluded_instruments", []))
    if excluded:
        raw = raw[~raw["instrument"].isin(excluded)].copy()
    df = add_chart_features(raw, cfg)

    trades_by_instrument: Dict[str, List[TradeRecord]] = {}
    stats_list: List[InstrumentStats] = []
    for instrument, instrument_df in df.groupby("instrument"):
        instrument_df = instrument_df.reset_index(drop=True)
        trades, stats = backtest_instrument(instrument_df, cfg)
        trades_by_instrument[instrument] = trades
        stats_list.append(stats)

    all_trades = [t for trades in trades_by_instrument.values() for t in trades]
    equity_curve = build_portfolio_equity(trades_by_instrument, sorted(trades_by_instrument))
    final_equity = float(np.mean([s.final_equity for s in stats_list])) if stats_list else 1.0

    return {
        "config": cfg,
        "dataset": {
            "path": str(path),
            "rows": int(len(df)),
            "instruments": sorted(df["instrument"].unique().tolist()),
            "start": str(df["datetime"].min()),
            "end": str(df["datetime"].max()),
        },
        "portfolio": {
            "total_trades": len(all_trades),
            "win_rate": float(np.mean([t.return_pct > 0 for t in all_trades])) if all_trades else 0.0,
            "final_equity": final_equity,
            "total_return_pct": (final_equity - 1.0) * 100.0,
            "max_drawdown_pct": compute_max_drawdown(equity_curve),
        },
        "per_instrument": [asdict(s) for s in stats_list],
        "sample_trades": [asdict(t) for t in all_trades[:20]],
        "all_trades": [asdict(t) for t in all_trades],
    }


def main() -> None:
    result = run_backtest()
    output_path = OUTPUT_DIR / "f_strategy_chart_backtest.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
