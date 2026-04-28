from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from grid_backtest import GridBacktestConfig, run_grid_backtest, scan_grid_parameters
from market_data import OKXDataClient


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "backend" / "backtest_results" / "grid_strategy_scan.json"

SYMBOL_GRID_CONFIGS = {
    "ETH": {
        "train_bars": 18,
        "review_bars": 6,
        "extension_step_bars": 3,
        "max_lifetime_bars": 12,
        "min_width_pct": 0.035,
        "max_width_pct": 0.070,
        "min_price_position": 0.25,
        "max_price_position": 0.75,
        "max_drift_pct": 0.035,
    },
    "SOL": {
        "train_bars": 24,
        "review_bars": 9,
        "extension_step_bars": 3,
        "max_lifetime_bars": 15,
        "min_width_pct": 0.030,
        "max_width_pct": 0.090,
        "min_price_position": 0.25,
        "max_price_position": 0.75,
        "max_drift_pct": 0.035,
    },
    "DOGE": {
        "train_bars": 24,
        "review_bars": 9,
        "extension_step_bars": 3,
        "max_lifetime_bars": 15,
        "min_width_pct": 0.030,
        "max_width_pct": 0.090,
        "min_price_position": 0.40,
        "max_price_position": 0.60,
        "max_drift_pct": 0.015,
    },
}


def _load_4h_bars(symbol: str, limit: int) -> List[Dict[str, float]]:
    client = OKXDataClient()
    inst_id = f"{symbol}-USDT-SWAP"
    candles = []
    after = None
    while len(candles) < limit:
        batch_limit = min(300, limit - len(candles))
        params = {"instId": inst_id, "bar": "4H", "limit": str(batch_limit)}
        if after:
            params["after"] = after
        batch = client._request("GET", "/api/v5/market/candles", params)
        if not batch:
            break
        candles.extend(batch)
        after = batch[-1][0]
        if len(batch) < batch_limit:
            break
        time.sleep(0.1)

    if not candles:
        return []

    bars: List[Dict[str, float]] = []
    seen = set()
    for candle in candles:
        if candle[0] in seen:
            continue
        seen.add(candle[0])
        try:
            bars.append(
                {
                    "timestamp": float(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]) if len(candle) > 5 else 0.0,
                }
            )
        except Exception:
            continue
    return sorted(bars, key=lambda item: item["timestamp"])


def _closes(bars: List[Dict[str, float]]) -> List[float]:
    return [float(bar["close"]) for bar in bars]


def _atr(bars: List[Dict[str, float]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    true_ranges: List[float] = []
    for i in range(1, len(bars)):
        prev_close = float(bars[i - 1]["close"])
        high = float(bars[i]["high"])
        low = float(bars[i]["low"])
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    window = true_ranges[-period:]
    return sum(window) / len(window) if window else 0.0


def _adx(bars: List[Dict[str, float]], period: int = 14) -> float:
    if len(bars) < period + 2:
        return 100.0

    true_ranges: List[float] = []
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    for i in range(1, len(bars)):
        high = float(bars[i]["high"])
        low = float(bars[i]["low"])
        prev_high = float(bars[i - 1]["high"])
        prev_low = float(bars[i - 1]["low"])
        prev_close = float(bars[i - 1]["close"])
        up_move = high - prev_high
        down_move = prev_low - low
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    dx_values: List[float] = []
    for i in range(period, len(true_ranges) + 1):
        tr_sum = sum(true_ranges[i - period : i])
        if tr_sum <= 0:
            continue
        plus_di = 100.0 * sum(plus_dm[i - period : i]) / tr_sum
        minus_di = 100.0 * sum(minus_dm[i - period : i]) / tr_sum
        denom = plus_di + minus_di
        if denom <= 0:
            continue
        dx_values.append(100.0 * abs(plus_di - minus_di) / denom)

    window = dx_values[-period:]
    return sum(window) / len(window) if window else 100.0


def _adx_delta(bars: List[Dict[str, float]], period: int = 14, lag: int = 3) -> float:
    if len(bars) < period + lag + 3:
        return 0.0
    current = _adx(bars, period)
    previous = _adx(bars[:-lag], period)
    return current - previous


def _range_bounds(history: List[Dict[str, float]]) -> Dict[str, float]:
    atr = _atr(history)
    core_low = min(float(bar["low"]) for bar in history)
    core_high = max(float(bar["high"]) for bar in history)
    return {
        "lower_bound": core_low - 0.35 * atr,
        "upper_bound": core_high + 0.35 * atr,
        "atr": atr,
    }


def _price_position(price: float, lower: float, upper: float) -> float:
    return (price - lower) / max(upper - lower, 1e-9)


def _directional_drift_pct(history: List[Dict[str, float]]) -> float:
    closes = _closes(history)
    if len(closes) < 2:
        return 0.0
    return (closes[-1] - closes[0]) / max(sum(closes) / len(closes), 1e-9)


def _close_drift_pct(history: List[Dict[str, float]], bars: int = 6) -> float:
    closes = _closes(history)
    if len(closes) <= bars:
        return 0.0
    return (closes[-1] - closes[-bars - 1]) / max(sum(closes[-bars - 1 :]) / len(closes[-bars - 1 :]), 1e-9)


def _edge_close_count(history: List[Dict[str, float]], lower: float, upper: float, edge_pct: float = 0.18, bars: int = 3) -> int:
    width = max(upper - lower, 1e-9)
    count = 0
    for bar in history[-bars:]:
        pos = _price_position(float(bar["close"]), lower, upper)
        if pos <= edge_pct or pos >= 1.0 - edge_pct:
            count += 1
    return count


def _daily_ma_cross_context(history: List[Dict[str, float]]) -> Dict[str, float]:
    closes = _closes(history)
    if len(closes) < 61:
        return {
            "sma5_1d": 0.0,
            "sma10_1d": 0.0,
            "ma5_10_gap_pct_1d": 0.0,
            "ma5_cross_up_ma10_1d": 0.0,
            "ma5_cross_down_ma10_1d": 0.0,
        }
    sma5 = sum(closes[-30:]) / 30.0
    sma10 = sum(closes[-60:]) / 60.0
    prev_sma5 = sum(closes[-31:-1]) / 30.0
    prev_sma10 = sum(closes[-61:-1]) / 60.0
    diff = sma5 - sma10
    prev_diff = prev_sma5 - prev_sma10
    return {
        "sma5_1d": sma5,
        "sma10_1d": sma10,
        "ma5_10_gap_pct_1d": diff / max(closes[-1], 1e-9),
        "ma5_cross_up_ma10_1d": 1.0 if diff > 0 and prev_diff <= 0 else 0.0,
        "ma5_cross_down_ma10_1d": 1.0 if diff < 0 and prev_diff >= 0 else 0.0,
    }


def _bollinger_context(history: List[Dict[str, float]], window: int = 18) -> Dict[str, float]:
    closes = _closes(history)
    if len(closes) < window:
        return {"bb_width": 0.0, "bb_pct_b": 0.5, "bb_mid_slope_pct": 0.0}

    current = closes[-window:]
    mid = sum(current) / len(current)
    std = statistics.stdev(current) if len(current) > 1 else 0.0
    width = (4.0 * std) / max(mid, 1e-9)
    lower = mid - 2.0 * std
    upper = mid + 2.0 * std
    pct_b = (closes[-1] - lower) / max(upper - lower, 1e-9)

    previous = closes[-window - 3 : -3]
    if len(previous) < window:
        slope = 0.0
    else:
        previous_mid = sum(previous) / len(previous)
        slope = (mid - previous_mid) / max(mid, 1e-9)

    return {
        "bb_width": width,
        "bb_pct_b": pct_b,
        "bb_mid_slope_pct": slope,
    }


def _volume_boundary_context(history: List[Dict[str, float]], min_volume_ratio: float = 1.25) -> Dict[str, float]:
    volumes = [float(bar.get("volume", 0.0)) for bar in history]
    volume_ma = sum(volumes) / len(volumes) if volumes else 0.0
    price = float(history[-1]["close"])
    support_hits = 0
    resistance_hits = 0
    if volume_ma > 0:
        for bar in history[-18:]:
            if float(bar.get("volume", 0.0)) < volume_ma * min_volume_ratio:
                continue
            if float(bar["low"]) < price:
                support_hits += 1
            if float(bar["high"]) > price:
                resistance_hits += 1

    return {
        "volume_support_hits": float(support_hits),
        "volume_resistance_hits": float(resistance_hits),
        "volume_boundary_confirmed": 1.0 if support_hits or resistance_hits else 0.0,
    }


def _grid_count_for_width(range_width_pct: float, min_spacing_pct: float) -> int:
    target_spacing_pct = max(min_spacing_pct * 1.5, 0.008)
    raw = max(int(math.floor(range_width_pct / target_spacing_pct)), 2)
    max_profitable = max(int(range_width_pct / max(min_spacing_pct, 1e-9)), 2)
    return max(4, min(24, raw, max_profitable))


def _eligible_setup(
    history: List[Dict[str, float]],
    *,
    fee_rate: float,
    slippage_rate: float,
    profit_buffer_rate: float,
    min_width_pct: float,
    max_width_pct: float,
    min_price_position: float,
    max_price_position: float,
    max_drift_pct: float,
    min_bb_width_pct: float = 0.025,
    max_bb_width_pct: float = 0.120,
    max_bb_mid_slope_pct: float = 0.018,
    max_adx: float = 20.0,
    max_adx_delta: float = 2.0,
    max_recent_drift_pct: float = 0.025,
    max_edge_close_count: int = 2,
    trend_history: Optional[List[Dict[str, float]]] = None,
) -> Optional[Dict[str, float]]:
    if len(history) < 10:
        return None

    bounds = _range_bounds(history)
    lower = bounds["lower_bound"]
    upper = bounds["upper_bound"]
    price = float(history[-1]["close"])
    if lower <= 0 or upper <= lower or not (lower < price < upper):
        return None

    mid = (lower + upper) / 2.0
    width_pct = (upper - lower) / max(mid, 1e-9)
    price_pos = _price_position(price, lower, upper)
    if not (min_width_pct <= width_pct <= max_width_pct):
        return None
    if not (min_price_position <= price_pos <= max_price_position):
        return None
    if abs(_directional_drift_pct(history)) > max_drift_pct:
        return None
    adx = _adx(history)
    if adx > max_adx:
        return None
    adx_delta = _adx_delta(history)
    if adx_delta > max_adx_delta:
        return None
    recent_drift_pct = _close_drift_pct(history)
    if abs(recent_drift_pct) > max_recent_drift_pct:
        return None
    edge_close_count = _edge_close_count(history, lower, upper)
    if edge_close_count >= max_edge_close_count:
        return None
    ma_context = _daily_ma_cross_context(trend_history or history)
    if ma_context["ma5_cross_up_ma10_1d"] or ma_context["ma5_cross_down_ma10_1d"]:
        return None
    bb = _bollinger_context(history)
    if not (min_bb_width_pct <= bb["bb_width"] <= max_bb_width_pct):
        return None
    if abs(bb["bb_mid_slope_pct"]) > max_bb_mid_slope_pct:
        return None

    min_spacing_pct = 2 * fee_rate + 2 * slippage_rate + profit_buffer_rate
    grid_count = _grid_count_for_width(width_pct, min_spacing_pct)
    spacing_pct = width_pct / max(grid_count, 1)
    if spacing_pct <= min_spacing_pct:
        return None
    volume_context = _volume_boundary_context(history)

    return {
        "lower_bound": lower,
        "upper_bound": upper,
        "range_width_pct": width_pct,
        "price_position_in_range": price_pos,
        "grid_count": float(grid_count),
        "grid_spacing_pct": spacing_pct,
        "min_profitable_spacing_pct": min_spacing_pct,
        "atr": bounds["atr"],
        "adx_14": adx,
        "adx_delta": adx_delta,
        "recent_drift_pct": recent_drift_pct,
        "edge_close_count": float(edge_close_count),
        **ma_context,
        "bb_width": bb["bb_width"],
        "bb_pct_b": bb["bb_pct_b"],
        "bb_mid_slope_pct": bb["bb_mid_slope_pct"],
        "volume_boundary_confirmed": volume_context["volume_boundary_confirmed"],
        "volume_support_hits": volume_context["volume_support_hits"],
        "volume_resistance_hits": volume_context["volume_resistance_hits"],
    }


def _run_rolling_backtest(
    bars: List[Dict[str, float]],
    *,
    train_bars: int,
    review_bars: int,
    extension_step_bars: int,
    max_lifetime_bars: int,
    fee_rate: float,
    slippage_rate: float,
    profit_buffer_rate: float,
    min_width_pct: float,
    max_width_pct: float,
    min_price_position: float,
    max_price_position: float,
    max_drift_pct: float,
    per_grid_notional: float,
    leverage: float,
    cooldown_single_failure_bars: int = 0,
    cooldown_multi_failure_bars: int = 18,
    cooldown_failure_lookback_bars: int = 42,
    cooldown_failure_threshold: int = 2,
) -> Dict[str, object]:
    trades: List[Dict[str, object]] = []
    recent_failures: List[Dict[str, object]] = []
    skipped = 0
    skipped_cooldown = 0
    i = train_bars
    while i + 2 < len(bars):
        active_failures = [
            failure for failure in recent_failures
            if i - int(failure["exit_index"]) <= cooldown_failure_lookback_bars
        ]
        if active_failures:
            latest_failure = max(active_failures, key=lambda item: int(item["exit_index"]))
            cooldown_bars = (
                cooldown_multi_failure_bars
                if len(active_failures) >= cooldown_failure_threshold
                else cooldown_single_failure_bars
            )
            cooldown_until = int(latest_failure["exit_index"]) + cooldown_bars
            if i < cooldown_until:
                skipped_cooldown += 1
                i += 1
                continue

        history = bars[i - train_bars : i]
        setup = _eligible_setup(
            history,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            profit_buffer_rate=profit_buffer_rate,
            min_width_pct=min_width_pct,
            max_width_pct=max_width_pct,
            min_price_position=min_price_position,
            max_price_position=max_price_position,
            max_drift_pct=max_drift_pct,
            trend_history=bars[max(0, i - 61) : i],
        )
        if not setup:
            skipped += 1
            i += 1
            continue

        test_bars = bars[i - 1 : min(i + max_lifetime_bars, len(bars))]
        price_pos = float(setup["price_position_in_range"])
        initial_base_ratio = 0.30
        bb_pct_b = float(setup.get("bb_pct_b") or 0.5)
        if price_pos >= 0.65 or bb_pct_b >= 0.80:
            initial_base_ratio = 0.15
        elif price_pos <= 0.35 or bb_pct_b <= 0.20:
            initial_base_ratio = 0.45

        result = run_grid_backtest(
            test_bars,
            GridBacktestConfig(
                lower_bound=float(setup["lower_bound"]),
                upper_bound=float(setup["upper_bound"]),
                grid_count=int(setup["grid_count"]),
                leverage=leverage,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
                per_grid_notional=per_grid_notional,
                initial_base_ratio=initial_base_ratio,
                breakout_buffer_pct=0.006,
                take_profit_pct=0.04,
                stop_loss_pct=-0.06,
                max_bars=max_lifetime_bars,
            ),
        )
        summary = result.get("summary", {}) or {}
        metrics = result.get("metrics", {}) or {}
        bars_processed = int(summary.get("bars_processed") or 0)
        if summary.get("breakout_exit") == "time_stop" and bars_processed >= review_bars:
            extension_eligible = (
                float(metrics.get("net_total_pnl") or 0.0) > 0
                and int(summary.get("fill_count") or 0) >= max(3, bars_processed // max(extension_step_bars, 1))
            )
            if not extension_eligible:
                summary["breakout_exit"] = "review_stop"
                summary["exit_reason"] = "REVIEW_STOP"

        exit_index = i + max(bars_processed - 1, 0)
        net_pnl = float(metrics.get("net_total_pnl") or 0.0)
        exit_reason = str(summary.get("breakout_exit") or summary.get("exit_reason") or "")
        if net_pnl < 0 or exit_reason in {"upper_breakout", "lower_breakout", "review_stop", "stop_loss"}:
            recent_failures.append({
                "entry_index": i,
                "exit_index": exit_index,
                "reason": exit_reason or "negative_pnl",
                "net_total_pnl": net_pnl,
            })

        trades.append(
            {
                "entry_index": i,
                "entry_timestamp": int(bars[i]["timestamp"]),
                "setup": {k: round(v, 6) for k, v in setup.items()},
                "initial_base_ratio": initial_base_ratio,
                "summary": summary,
                "metrics": metrics,
            }
        )
        i += max(int(summary.get("bars_processed") or review_bars), 1)

    net_pnl = sum(float((trade.get("metrics") or {}).get("net_total_pnl", 0.0)) for trade in trades)
    initial_margin = sum(float((trade.get("metrics") or {}).get("initial_margin", 0.0)) for trade in trades)
    wins = [t for t in trades if float((t.get("metrics") or {}).get("net_total_pnl", 0.0)) > 0]
    segments = _segment_trades(trades, len(bars), segment_count=4)
    return {
        "valid": True,
        "mode": "rolling_range_grid",
        "train_bars": train_bars,
        "review_bars": review_bars,
        "extension_step_bars": extension_step_bars,
        "max_lifetime_bars": max_lifetime_bars,
        "skipped_windows": skipped,
        "skipped_cooldown_windows": skipped_cooldown,
        "trade_count": len(trades),
        "win_count": len(wins),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "net_total_pnl": round(net_pnl, 4),
        "aggregate_return_on_margin_pct": round((net_pnl / initial_margin) * 100.0, 4) if initial_margin > 0 else 0.0,
        "segments": segments,
        "trades": trades,
    }


def _segment_trades(trades: List[Dict[str, object]], bar_count: int, segment_count: int) -> List[Dict[str, object]]:
    if bar_count <= 0 or segment_count <= 0:
        return []

    segments: List[Dict[str, object]] = []
    segment_size = max(bar_count // segment_count, 1)
    for segment_index in range(segment_count):
        start_index = segment_index * segment_size
        end_index = bar_count if segment_index == segment_count - 1 else min((segment_index + 1) * segment_size, bar_count)
        segment_trades = [
            trade
            for trade in trades
            if start_index <= int(trade.get("entry_index") or 0) < end_index
        ]
        net_pnl = sum(float((trade.get("metrics") or {}).get("net_total_pnl", 0.0)) for trade in segment_trades)
        initial_margin = sum(float((trade.get("metrics") or {}).get("initial_margin", 0.0)) for trade in segment_trades)
        wins = [trade for trade in segment_trades if float((trade.get("metrics") or {}).get("net_total_pnl", 0.0)) > 0]
        segments.append(
            {
                "segment": segment_index + 1,
                "bar_start": start_index,
                "bar_end": end_index,
                "trade_count": len(segment_trades),
                "win_count": len(wins),
                "win_rate": round(len(wins) / len(segment_trades), 4) if segment_trades else 0.0,
                "net_total_pnl": round(net_pnl, 4),
                "return_on_margin_pct": round((net_pnl / initial_margin) * 100.0, 4) if initial_margin > 0 else 0.0,
            }
        )
    return segments


def _run_static_scan(bars: List[Dict[str, float]]) -> Dict[str, object]:
    bounds = _range_bounds(bars)
    if len(bars) < 20 or bounds["upper_bound"] <= bounds["lower_bound"]:
        return {
            "valid": False,
            "price_points": len(bars),
            "reason": "insufficient_history_or_flat_range",
        }
    return scan_grid_parameters(
        bars,
        lower_bound=bounds["lower_bound"],
        upper_bound=bounds["upper_bound"],
        grid_counts=[4, 6, 8, 10, 12],
        fee_rates=[0.0005],
        slippage_rates=[0.0007],
        per_grid_notionals=[50.0, 75.0, 100.0],
        leverage_values=[3.0],
        top_k=5,
    )


def run_scan(symbols: List[str], bars: int, mode: str = "rolling") -> Dict[str, object]:
    results: Dict[str, object] = {}
    for symbol in symbols:
        ohlc = _load_4h_bars(symbol, bars)
        if len(ohlc) < 30:
            results[symbol] = {"valid": False, "price_points": len(ohlc), "reason": "insufficient_history"}
            continue

        if mode == "static":
            results[symbol] = _run_static_scan(ohlc)
        else:
            symbol_config = SYMBOL_GRID_CONFIGS.get(
                symbol,
                {
                    "train_bars": 18,
                    "review_bars": 9,
                    "extension_step_bars": 3,
                    "max_lifetime_bars": 15,
                    "min_width_pct": 0.030,
                    "max_width_pct": 0.080,
                    "min_price_position": 0.15,
                    "max_price_position": 0.85,
                    "max_drift_pct": 0.035,
                },
            )
            results[symbol] = _run_rolling_backtest(
                ohlc,
                train_bars=int(symbol_config["train_bars"]),
                review_bars=int(symbol_config["review_bars"]),
                extension_step_bars=int(symbol_config["extension_step_bars"]),
                max_lifetime_bars=int(symbol_config["max_lifetime_bars"]),
                fee_rate=0.0005,
                slippage_rate=0.0007,
                profit_buffer_rate=0.0010,
                min_width_pct=float(symbol_config["min_width_pct"]),
                max_width_pct=float(symbol_config["max_width_pct"]),
                min_price_position=float(symbol_config["min_price_position"]),
                max_price_position=float(symbol_config["max_price_position"]),
                max_drift_pct=float(symbol_config["max_drift_pct"]),
                per_grid_notional=100.0,
                leverage=3.0,
            )
            results[symbol]["symbol_config"] = symbol_config
    valid_results = [result for result in results.values() if isinstance(result, dict) and result.get("valid")]
    total_trades = sum(int(result.get("trade_count") or 0) for result in valid_results)
    total_wins = sum(int(result.get("win_count") or 0) for result in valid_results)
    total_net_pnl = sum(float(result.get("net_total_pnl") or 0.0) for result in valid_results)
    weighted_margin = 0.0
    for result in valid_results:
        ret = float(result.get("aggregate_return_on_margin_pct") or 0.0)
        pnl = float(result.get("net_total_pnl") or 0.0)
        if abs(ret) > 1e-9:
            weighted_margin += pnl / (ret / 100.0)
    return {
        "strategy_family": "GRID",
        "mode": mode,
        "bars": bars,
        "symbols": symbols,
        "portfolio_summary": {
            "trade_count": total_trades,
            "win_count": total_wins,
            "win_rate": round(total_wins / total_trades, 4) if total_trades else 0.0,
            "net_total_pnl": round(total_net_pnl, 4),
            "aggregate_return_on_margin_pct": round((total_net_pnl / weighted_margin) * 100.0, 4) if weighted_margin > 0 else 0.0,
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan neutral/range grid parameters over recent 4H history.")
    parser.add_argument("--symbols", nargs="+", default=["ETH", "SOL", "DOGE"], help="Symbols like ETH SOL DOGE")
    parser.add_argument("--bars", type=int, default=180, help="Number of 4H candles to fetch")
    parser.add_argument("--mode", choices=["rolling", "static"], default="rolling", help="Backtest mode")
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH), help="Output JSON path")
    args = parser.parse_args()

    payload = run_scan([s.upper() for s in args.symbols], args.bars, args.mode)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "symbols": args.symbols, "bars": args.bars, "mode": args.mode}, ensure_ascii=False))


if __name__ == "__main__":
    main()
