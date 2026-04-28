import json
import math
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from db_client import db
from macro_news_pipeline import build_macro_news_snapshot
from okx_executor import OKXExecutor
from post_trade_review import run_post_trade_review
from research_agent import build_research_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DATA_DIR = PROJECT_ROOT / "frontend" / "data"
QLOB_PAYLOAD_PATH = BASE_DIR / "qlib_data" / "deepseek_payload.json"
QLOB_FEATURES_PATH = BASE_DIR / "qlib_data" / "multi_coin_features.csv"

TRACKED_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "DOGE"]
BLUEPRINT_A2_ENABLED_SYMBOLS = {"BNB-USDT", "BTC-USDT", "SOL-USDT"}
GRID_ENABLED_SYMBOLS = {"ETH-USDT", "SOL-USDT", "DOGE-USDT"}
GRID_COOLDOWN_FAILURE_REASONS = {
    "grid_range_breakdown",
    "grid_range_breakout",
    "grid_event_window",
    "grid_macro_trend_blocked",
    "grid_regime_deterioration",
    "grid_extension_rejected",
    "grid_max_lifetime_stop",
    "grid_time_stop",
}
GRID_SYMBOL_CONFIG = {
    "ETH-USDT": {
        "grid_width_min_pct": 0.035,
        "grid_width_max_pct": 0.070,
        "grid_price_position_min": 0.25,
        "grid_price_position_max": 0.75,
        "grid_review_after_hours": 24,
        "grid_extension_step_hours": 12,
        "grid_max_lifetime_hours": 48,
    },
    "SOL-USDT": {
        "grid_width_min_pct": 0.030,
        "grid_width_max_pct": 0.090,
        "grid_price_position_min": 0.25,
        "grid_price_position_max": 0.75,
        "grid_review_after_hours": 36,
        "grid_extension_step_hours": 12,
        "grid_max_lifetime_hours": 60,
    },
    "DOGE-USDT": {
        "grid_width_min_pct": 0.030,
        "grid_width_max_pct": 0.090,
        "grid_price_position_min": 0.40,
        "grid_price_position_max": 0.60,
        "grid_recent_drift_max_pct": 0.015,
        "grid_review_after_hours": 36,
        "grid_extension_step_hours": 12,
        "grid_max_lifetime_hours": 60,
    },
}
FLOW_SCHEMA_VERSION = "flow_semantics_v1"
STRATEGY_FAMILY_DIRECTIONAL = "DIRECTIONAL"
STRATEGY_FAMILY_GRID = "GRID"

GLOBAL_CONFIG = {
    "timeframe": "4h",
    "min_rrr": 1.8,
    "global_leverage_min": 1.0,
    "global_leverage_max": 8.0,
    "approved_risk_fraction": 0.02,
    "default_position_size_fraction": 0.10,
    "max_position_size_fraction": 0.25,
    "qlib_rank_bucket_size": 3,
    "qlib_prob_threshold": 0.55,
    "qlib_prob_gap_threshold": 0.15,
    "qlib_flat_max_threshold": 0.40,
    "qlib_invalidation_prob_threshold": 0.45,
    "grid_flat_min_threshold": 0.55,
    "grid_flat_exit_threshold": 0.45,
    "grid_prob_ceiling": 0.55,
    "grid_prob_gap_max": 0.12,
    "grid_adx_max": 20.0,
    "grid_width_min_pct": 0.030,
    "grid_width_max_pct": 0.080,
    "grid_price_position_min": 0.15,
    "grid_price_position_max": 0.85,
    "grid_bb_width_min_pct": 0.025,
    "grid_bb_width_max_pct": 0.120,
    "grid_bb_mid_slope_max_pct": 0.018,
    "grid_adx_delta_max": 2.0,
    "grid_recent_drift_max_pct": 0.025,
    "grid_max_edge_close_count": 1,
    "grid_block_macro_horizons": ("SWING", "MULTI_DAY"),
    "grid_cooldown_single_failure_hours": 0,
    "grid_cooldown_multi_failure_hours": 72,
    "grid_cooldown_failure_lookback_hours": 168,
    "grid_cooldown_failure_threshold": 2,
    "grid_funding_zscore_max": 1.0,
    "grid_review_after_hours": 36,
    "grid_extension_step_hours": 12,
    "grid_max_lifetime_hours": 60,
    "grid_position_size_fraction": 0.05,
    "grid_max_position_size_fraction": 0.10,
    "grid_leverage_default": 3.0,
    "grid_leverage_max": 3.0,
    "grid_fee_rate": 0.0005,
    "grid_slippage_rate": 0.0007,
    "grid_profit_buffer_rate": 0.0010,
    "grid_min_per_grid_notional_usd": 25.0,
}
LOCAL_TZ_NAME = os.getenv("LOCAL_TIMEZONE", "Asia/Shanghai")
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)


def _execution_event(event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "type": event_type,
        "at": _iso_now(),
        "payload": payload or {},
    }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_now_local() -> str:
    return _now_utc().astimezone(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _snapshot_timestamp() -> int:
    return int(_now_utc().timestamp())


def _timestamp_to_local_iso(ts: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        return None


def _timestamp_to_utc_iso(ts: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _aligned_cycle_id(dt: Optional[datetime] = None) -> str:
    dt = dt or _now_utc()
    block_hour = (dt.hour // 4) * 4
    aligned = dt.replace(hour=block_hour, minute=0, second=0, microsecond=0)
    return f"cycle_{aligned.strftime('%Y-%m-%d_%H00')}"


def _aligned_cycle_local(dt: Optional[datetime] = None) -> str:
    dt = (dt or _now_utc()).astimezone(LOCAL_TZ)
    block_hour = (dt.hour // 4) * 4
    aligned = dt.replace(hour=block_hour, minute=0, second=0, microsecond=0)
    return aligned.strftime("%Y-%m-%d %H:%M:%S %Z")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            cleaned = value.replace("%", "").replace(",", "").strip()
            if cleaned == "":
                return default
            return float(cleaned)
        return float(value)
    except Exception:
        return default


def _token_flow_semantic(token_flow: float, flow_data_available: bool) -> str:
    if not flow_data_available:
        return "UNAVAILABLE"
    if token_flow > 0:
        return "ACCUMULATION_HINT"
    if token_flow < 0:
        return "DISTRIBUTION_PRESSURE"
    return "NEUTRAL"


def _stable_flow_semantic(stable_flow: float, flow_data_available: bool) -> str:
    if not flow_data_available:
        return "UNAVAILABLE"
    if stable_flow > 0:
        return "BUYING_POWER"
    if stable_flow < 0:
        return "CAPITAL_WITHDRAWAL"
    return "NEUTRAL"


def _build_flow_semantics(token_flow: float, stable_flow: float, flow_data_available: bool) -> Dict[str, Any]:
    token_semantic = _token_flow_semantic(token_flow, flow_data_available)
    stable_semantic = _stable_flow_semantic(stable_flow, flow_data_available)
    long_votes = 0
    short_votes = 0
    if token_semantic == "ACCUMULATION_HINT":
        long_votes += 1
    elif token_semantic == "DISTRIBUTION_PRESSURE":
        short_votes += 1
    if stable_semantic == "BUYING_POWER":
        long_votes += 1
    elif stable_semantic == "CAPITAL_WITHDRAWAL":
        short_votes += 1

    if not flow_data_available:
        composite = "UNAVAILABLE"
    elif long_votes and short_votes:
        composite = "MIXED"
    elif long_votes:
        composite = "LONG_SUPPORT"
    elif short_votes:
        composite = "SHORT_SUPPORT"
    else:
        composite = "NEUTRAL"

    return {
        "schema_version": FLOW_SCHEMA_VERSION,
        "token_semantic": token_semantic,
        "stablecoin_semantic": stable_semantic,
        "composite_semantic": composite,
        "long_support": composite == "LONG_SUPPORT",
        "short_support": composite == "SHORT_SUPPORT",
        "mixed_signal": composite == "MIXED",
    }


def _has_numeric_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.replace("%", "").replace(",", "").strip().upper() in {"", "N/A", "NONE", "NULL"}:
        return False
    try:
        float(str(value).replace("%", "").replace(",", "").strip())
        return True
    except Exception:
        return False


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return deepcopy(default)
    try:
        return json.loads(path.read_text())
    except Exception:
        return deepcopy(default)


def _load_whale_analysis() -> Dict[str, Any]:
    data = db.get_data("whale_analysis")
    if isinstance(data, dict) and data:
        return data
    return _read_json(FRONTEND_DATA_DIR / "whale_analysis.json", {})


def _load_qlib_payload() -> Dict[str, Any]:
    return _read_json(QLOB_PAYLOAD_PATH, {})


def _load_portfolio_state() -> Dict[str, Any]:
    data = db.get_data("portfolio_state", {})
    return data if isinstance(data, dict) else {}


def _compute_volume_confirmed_levels(
    lows: pd.Series,
    highs: pd.Series,
    rel_volume: pd.Series,
    lookback: int,
    min_volume_ratio: float,
) -> Tuple[pd.Series, pd.Series]:
    support_values: List[float] = []
    resistance_values: List[float] = []
    low_values = lows.astype(float).tolist()
    high_values = highs.astype(float).tolist()
    rel_volume_values = rel_volume.astype(float).tolist()
    for idx in range(len(low_values)):
        if idx < lookback:
            support_values.append(float("nan"))
            resistance_values.append(float("nan"))
            continue
        start = idx - lookback
        window_lows = low_values[start:idx]
        window_highs = high_values[start:idx]
        window_volumes = rel_volume_values[start:idx]
        confirmed = [i for i, value in enumerate(window_volumes) if pd.notna(value) and value >= min_volume_ratio]
        if confirmed:
            support_values.append(min(window_lows[i] for i in confirmed))
            resistance_values.append(max(window_highs[i] for i in confirmed))
        else:
            support_values.append(min(window_lows))
            resistance_values.append(max(window_highs))
    return pd.Series(support_values, index=lows.index), pd.Series(resistance_values, index=highs.index)


def _load_chart_feature_context_map() -> Dict[str, Dict[str, Any]]:
    if not QLOB_FEATURES_PATH.exists():
        return {}
    try:
        df = pd.read_csv(QLOB_FEATURES_PATH, parse_dates=["datetime"])
    except Exception:
        return {}
    if df.empty:
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    for instrument, instrument_df in df.groupby("instrument"):
        frame = instrument_df.sort_values("datetime").copy()
        frame["volume_ma_60"] = frame["volume"].rolling(60, min_periods=60).mean()
        frame["rel_volume_60"] = frame["volume"] / frame["volume_ma_60"]
        frame["sma50_4h"] = frame["close"].rolling(50, min_periods=50).mean()
        frame["bb_width"] = frame["bb_width_20"] if "bb_width_20" in frame.columns else pd.NA
        frame["bb_pct_b"] = frame["bb_pos_20"] if "bb_pos_20" in frame.columns else 0.5
        frame["bb_mid_20"] = frame["close"].rolling(20, min_periods=20).mean()
        frame["bb_mid_slope_pct"] = (frame["bb_mid_20"] - frame["bb_mid_20"].shift(3)) / frame["bb_mid_20"].replace(0, pd.NA)
        if "adx_14" not in frame.columns:
            frame["adx_14"] = pd.NA
        frame["adx_delta"] = frame["adx_14"] - frame["adx_14"].shift(3)
        close_mean_7 = frame["close"].rolling(7, min_periods=7).mean()
        frame["recent_close_drift_pct"] = (frame["close"] - frame["close"].shift(6)) / close_mean_7.replace(0, pd.NA)
        frame["sma5_1d"] = frame["close"].rolling(30, min_periods=30).mean()
        frame["sma10_1d"] = frame["close"].rolling(60, min_periods=60).mean()
        ma_diff = frame["sma5_1d"] - frame["sma10_1d"]
        prev_ma_diff = ma_diff.shift(1)
        frame["ma5_cross_up_ma10_1d"] = (ma_diff > 0) & (prev_ma_diff <= 0)
        frame["ma5_cross_down_ma10_1d"] = (ma_diff < 0) & (prev_ma_diff >= 0)
        frame["ma5_10_gap_pct_1d"] = ma_diff / frame["close"].replace(0, pd.NA)
        prev_price_high = frame["high"].shift(1).rolling(8, min_periods=8).max()
        prev_price_low = frame["low"].shift(1).rolling(8, min_periods=8).min()
        prev_macd_high = frame["macd_hist"].shift(1).rolling(8, min_periods=8).max()
        prev_macd_low = frame["macd_hist"].shift(1).rolling(8, min_periods=8).min()
        frame["bearish_divergence_4h"] = (frame["high"] > prev_price_high) & (frame["macd_hist"] < prev_macd_high)
        frame["bullish_divergence_4h"] = (frame["low"] < prev_price_low) & (frame["macd_hist"] > prev_macd_low)
        diff = frame["macd"] - frame["macd_signal"]
        prev_diff = diff.shift(1)
        frame["macd_cross_up_4h"] = (diff > 0) & (prev_diff <= 0)
        frame["macd_cross_down_4h"] = (diff < 0) & (prev_diff >= 0)
        support_level, resistance_level = _compute_volume_confirmed_levels(
            lows=frame["low"],
            highs=frame["high"],
            rel_volume=frame["rel_volume_60"],
            lookback=12,
            min_volume_ratio=1.5,
        )
        frame["structure_support_12bar_volume_confirmed"] = support_level
        frame["structure_resistance_12bar_volume_confirmed"] = resistance_level
        range_width = (resistance_level - support_level).replace(0, pd.NA)
        range_position = (frame["close"] - support_level) / range_width
        edge_close = (range_position <= 0.18) | (range_position >= 0.82)
        frame["range_edge_close_count"] = edge_close.astype(int).rolling(3, min_periods=3).sum()
        latest = frame.iloc[-1]
        atr = _safe_float(latest.get("atr_14"))
        support = _safe_float(latest.get("structure_support_12bar_volume_confirmed"))
        resistance = _safe_float(latest.get("structure_resistance_12bar_volume_confirmed"))
        grid_preflight_fields = [
            "bb_width",
            "bb_pct_b",
            "bb_mid_slope_pct",
            "adx_delta",
            "recent_close_drift_pct",
            "range_edge_close_count",
            "sma5_1d",
            "sma10_1d",
            "ma5_10_gap_pct_1d",
        ]
        missing_preflight_fields = [
            field for field in grid_preflight_fields
            if field not in latest or pd.isna(latest.get(field))
        ]
        result[str(instrument).upper()] = {
            "macd_line_4h": _safe_float(latest.get("macd")),
            "macd_signal_4h": _safe_float(latest.get("macd_signal")),
            "macd_hist_4h": _safe_float(latest.get("macd_hist")),
            "rsi_4h": _safe_float(latest.get("rsi_14")),
            "adx_14_4h": _safe_float(latest.get("adx_14")),
            "atr_14": atr,
            "rel_volume_60": _safe_float(latest.get("rel_volume_60")),
            "sma50_4h": _safe_float(latest.get("sma50_4h")),
            "bb_width": _safe_float(latest.get("bb_width")),
            "bb_pct_b": _safe_float(latest.get("bb_pct_b"), 0.5),
            "bb_mid_slope_pct": _safe_float(latest.get("bb_mid_slope_pct")),
            "adx_delta": _safe_float(latest.get("adx_delta")),
            "recent_close_drift_pct": _safe_float(latest.get("recent_close_drift_pct")),
            "range_edge_close_count": int(_safe_float(latest.get("range_edge_close_count"))),
            "sma5_1d": _safe_float(latest.get("sma5_1d")),
            "sma10_1d": _safe_float(latest.get("sma10_1d")),
            "ma5_cross_up_ma10_1d": bool(latest.get("ma5_cross_up_ma10_1d")),
            "ma5_cross_down_ma10_1d": bool(latest.get("ma5_cross_down_ma10_1d")),
            "ma5_10_gap_pct_1d": _safe_float(latest.get("ma5_10_gap_pct_1d")),
            "bearish_divergence_4h": bool(latest.get("bearish_divergence_4h")),
            "bullish_divergence_4h": bool(latest.get("bullish_divergence_4h")),
            "macd_cross_up_4h": bool(latest.get("macd_cross_up_4h")),
            "macd_cross_down_4h": bool(latest.get("macd_cross_down_4h")),
            "volume_usd_4h": _safe_float(latest.get("volume_usd_4h")),
            "liquidation_long_usd": _safe_float(latest.get("liquidation_long_usd")),
            "liquidation_short_usd": _safe_float(latest.get("liquidation_short_usd")),
            "liquidation_long_to_volume_4h": _safe_float(latest.get("liquidation_long_to_volume_4h")),
            "liquidation_short_to_volume_4h": _safe_float(latest.get("liquidation_short_to_volume_4h")),
            "structure_support_12bar_volume_confirmed": support,
            "structure_resistance_12bar_volume_confirmed": resistance,
            "structure_support_stop_long": round(support - 0.5 * atr, 4) if support > 0 and atr > 0 else None,
            "structure_resistance_stop_short": round(resistance + 0.5 * atr, 4) if resistance > 0 and atr > 0 else None,
            "grid_preflight_data_ok": not missing_preflight_fields,
            "grid_preflight_missing_fields": missing_preflight_fields,
        }
    return result


def _symbol_position_snapshot(portfolio_state: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    positions = portfolio_state.get("positions", []) or []
    symbol_positions = [p for p in positions if p.get("symbol", "").upper() == symbol.upper()]
    if not symbol_positions:
        return {
            "position_side": "NONE",
            "position_size_usd": 0.0,
            "entry_price": None,
            "current_price": None,
            "unrealized_pnl_pct": 0.0,
            "distance_to_liq": None,
            "open_positions": [],
        }

    first = symbol_positions[0]
    side = "LONG" if str(first.get("type", "")).lower() == "long" else "SHORT"
    notional = _safe_float(first.get("margin")) * max(_safe_float(first.get("leverage"), 1.0), 1.0)
    distance_to_liq = _estimate_distance_to_liq(first)
    return {
        "position_side": side,
        "position_size_usd": round(notional, 2),
        "entry_price": _safe_float(first.get("entryPrice"), None),
        "current_price": _safe_float(first.get("currentPrice"), None),
        "unrealized_pnl_pct": _safe_float(first.get("pnlPercent")) / 100.0,
        "distance_to_liq": distance_to_liq,
        "open_positions": symbol_positions,
    }


def _estimate_distance_to_liq(position: Dict[str, Any]) -> Optional[float]:
    current = _safe_float(position.get("currentPrice"))
    entry = _safe_float(position.get("entryPrice"))
    leverage = max(_safe_float(position.get("leverage"), 1.0), 1.0)
    if current <= 0 or entry <= 0 or leverage <= 0:
        return None

    # Approximation only. We need a deterministic guard rail before full exchange math mapping.
    # Assume effective liquidation buffer shrinks roughly with leverage.
    # Example: 5x -> about 20% buffer, 2x -> about 50% buffer.
    base_buffer = max(0.03, min(0.80, 1.0 / leverage))
    adverse_move = abs(current - entry) / current if current else 0.0
    return max(0.0, round(base_buffer - adverse_move, 4))


def _build_macro_snapshot(whale_analysis: Dict[str, Any]) -> Dict[str, Any]:
    return build_macro_news_snapshot(whale_analysis)


def _compact_news_summary(news_obj: Dict[str, Any]) -> str:
    snippets: List[str] = []
    for key in ["macro", "general", "bitcoin", "ethereum"]:
        bucket = news_obj.get(key, {})
        if not isinstance(bucket, dict):
            continue
        items = bucket.get("items", [])
        if items:
            first = items[0]
            title = first.get("title")
            if title:
                snippets.append(title)
    return " | ".join(snippets[:3])


def _derive_macro_mode(fear: Dict[str, Any], macro: Dict[str, Any]) -> str:
    fear_value = _safe_float(fear.get("value"), 50.0)
    risk_off_score = _safe_float(macro.get("risk_off_score"), 0.0)
    if macro.get("event_window"):
        return "EVENT_DRIVEN"
    if fear_value <= 30 or risk_off_score >= 0.7:
        return "RISK_OFF"
    if fear_value >= 60 and risk_off_score <= 0.3:
        return "RISK_ON"
    return "MIXED"


def _derive_macro_permission(fear: Dict[str, Any], macro: Dict[str, Any]) -> str:
    mode = _derive_macro_mode(fear, macro)
    if mode == "RISK_OFF":
        return "ALLOW_SHORT"
    if mode == "RISK_ON":
        return "ALLOW_LONG"
    return "ALLOW_BOTH"


def _qlib_coin_map(qlib_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result = {}
    coins = [coin for coin in (qlib_payload.get("coins", []) or []) if isinstance(coin, dict)]
    total = len(coins)
    for coin in coins:
        if not isinstance(coin, dict):
            continue
        sym = str(coin.get("symbol", "")).upper()
        if sym:
            normalized = dict(coin)
            rank = normalized.get("rank")
            try:
                rank = int(rank)
            except (TypeError, ValueError):
                rank = None
            if total <= 1:
                percentile = 1.0
            elif rank is None:
                percentile = None
            else:
                # Rank 1 means strongest coin. Convert to [0, 1] percentile so
                # blueprint thresholds remain meaningful even when raw qlib_score
                # is a tiny relative-strength value rather than a probability.
                percentile = round(max(0.0, min(1.0, 1.0 - ((rank - 1) / (total - 1)))), 4)
            normalized["qlib_percentile"] = percentile
            normalized["qlib_relative_score_8h"] = _safe_float(normalized.get("qlib_relative_score_8h"), _safe_float(normalized.get("qlib_score")))
            result[sym] = normalized
    return result


def _build_decision_snapshot(
    symbol: str,
    whale_analysis: Dict[str, Any],
    qlib_coin: Dict[str, Any],
    portfolio_state: Dict[str, Any],
    cycle_id: str,
    chart_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sym_key = symbol.lower()
    coin_root = whale_analysis.get(sym_key, {}) if isinstance(whale_analysis.get(sym_key), dict) else {}
    market = coin_root.get("market", {}) if isinstance(coin_root.get("market"), dict) else {}
    stats24 = coin_root.get("stats_24h", {}) if isinstance(coin_root.get("stats_24h"), dict) else {}
    position_snapshot = _symbol_position_snapshot(portfolio_state, symbol)
    macro_snapshot = _build_macro_snapshot(whale_analysis)
    market_data = qlib_coin.get("market_data", {})
    chart_context = chart_context or {}

    funding_rate = _safe_float(market.get("funding_rate"), _safe_float(market_data.get("funding_rate")))
    funding_zscore = _safe_float(market.get("funding_zscore"), _safe_float(market_data.get("funding_rate_zscore")) / 100.0)
    raw_token_flow = stats24.get("token_net_flow")
    raw_stable_flow = stats24.get("stablecoin_net_flow")
    token_flow = _safe_float(raw_token_flow)
    stable_flow = _safe_float(raw_stable_flow)
    flow_data_available = _has_numeric_value(raw_token_flow) or _has_numeric_value(raw_stable_flow)
    flow_semantics = _build_flow_semantics(token_flow, stable_flow, flow_data_available)
    qlib_score = _safe_float(qlib_coin.get("qlib_relative_score_8h"), _safe_float(qlib_coin.get("qlib_score")))
    qlib_percentile = _safe_float(qlib_coin.get("qlib_percentile"))
    p_up_8h = _safe_float(qlib_coin.get("p_up_8h"))
    p_down_8h = _safe_float(qlib_coin.get("p_down_8h"))
    p_flat_8h = _safe_float(qlib_coin.get("p_flat_8h"))
    confidence_8h = _safe_float(qlib_coin.get("confidence_8h"), max(p_up_8h, p_down_8h))

    market_snapshot = {
        "price": _safe_float(market.get("price"), _safe_float(market_data.get("close"))),
        "change_24h": _safe_float(market.get("change_24h")),
        "rsi_4h": _safe_float(chart_context.get("rsi_4h"), _safe_float(market.get("rsi_4h"), _safe_float(market.get("rsi_14"), _safe_float(market_data.get("rsi_14"))))),
        "adx_14": _safe_float(chart_context.get("adx_14_4h"), _safe_float(market.get("adx_14"))),
        "volume_ratio": _safe_float(market.get("volume_ratio"), _safe_float(market.get("vol_ratio_20"), 1.0)),
        "bb_width": _safe_float(chart_context.get("bb_width"), _safe_float(market.get("bb_width"), _safe_float(market_data.get("bb_width_20")))),
        "bb_pct_b": _safe_float(chart_context.get("bb_pct_b"), _safe_float(market.get("bb_pct_b"), _safe_float(market_data.get("bb_pos_20"), 0.5))),
        "bb_mid_slope_pct": _safe_float(chart_context.get("bb_mid_slope_pct"), _safe_float(market.get("bb_mid_slope_pct"))),
        "adx_delta": _safe_float(chart_context.get("adx_delta"), _safe_float(market.get("adx_delta"))),
        "recent_close_drift_pct": _safe_float(chart_context.get("recent_close_drift_pct"), _safe_float(market.get("recent_close_drift_pct"))),
        "range_edge_close_count": int(_safe_float(chart_context.get("range_edge_close_count"), _safe_float(market.get("range_edge_close_count")))),
        "wick_ratio_lower": _safe_float(market.get("wick_ratio_lower")),
        "wick_ratio_upper": _safe_float(market.get("wick_ratio_upper")),
        "funding_rate": funding_rate,
        "funding_zscore": funding_zscore,
        "oi_now": _safe_float(market.get("oi_now")),
        "delta_oi_24h_percent": _safe_float(market.get("delta_oi_24h_percent"), _safe_float(market_data.get("oi_change")) / 100.0),
        "natr_percent": _safe_float(market.get("natr_percent"), _safe_float(market_data.get("natr_14"))),
        "whale_ls_ratio": _safe_float(market.get("whale_ls_ratio")),
        "whale_pos_ratio": _safe_float(market.get("whale_pos_ratio")),
        "atr_14": _safe_float(chart_context.get("atr_14"), _safe_float(market_data.get("atr_14"))),
        "macd_line_4h": _safe_float(chart_context.get("macd_line_4h"), _safe_float(market_data.get("macd"))),
        "macd_signal_4h": _safe_float(chart_context.get("macd_signal_4h"), _safe_float(market_data.get("macd_signal"))),
        "macd_hist_4h": _safe_float(chart_context.get("macd_hist_4h"), _safe_float(market.get("macd_hist"), _safe_float(market_data.get("macd_hist")))),
        "rel_volume_60": _safe_float(chart_context.get("rel_volume_60")),
        "volume_usd_4h": _safe_float(chart_context.get("volume_usd_4h")),
        "sma50_4h": _safe_float(chart_context.get("sma50_4h")),
        "sma5_1d": _safe_float(chart_context.get("sma5_1d"), _safe_float(market.get("sma5_1d"))),
        "sma10_1d": _safe_float(chart_context.get("sma10_1d"), _safe_float(market.get("sma10_1d"))),
        "ma5_cross_up_ma10_1d": bool(chart_context.get("ma5_cross_up_ma10_1d", market.get("ma5_cross_up_ma10_1d"))),
        "ma5_cross_down_ma10_1d": bool(chart_context.get("ma5_cross_down_ma10_1d", market.get("ma5_cross_down_ma10_1d"))),
        "ma5_10_gap_pct_1d": _safe_float(chart_context.get("ma5_10_gap_pct_1d"), _safe_float(market.get("ma5_10_gap_pct_1d"))),
        "grid_preflight_data_ok": bool(chart_context.get("grid_preflight_data_ok")),
        "grid_preflight_missing_fields": chart_context.get("grid_preflight_missing_fields", []),
        "bearish_divergence_4h": bool(chart_context.get("bearish_divergence_4h")),
        "bullish_divergence_4h": bool(chart_context.get("bullish_divergence_4h")),
        "macd_cross_up_4h": bool(chart_context.get("macd_cross_up_4h")),
        "macd_cross_down_4h": bool(chart_context.get("macd_cross_down_4h")),
        "structure_support_12bar_volume_confirmed": chart_context.get("structure_support_12bar_volume_confirmed"),
        "structure_resistance_12bar_volume_confirmed": chart_context.get("structure_resistance_12bar_volume_confirmed"),
        "structure_support_stop_long": chart_context.get("structure_support_stop_long"),
        "structure_resistance_stop_short": chart_context.get("structure_resistance_stop_short"),
    }
    onchain_snapshot = {
        "token_net_flow": token_flow,
        "stablecoin_net_flow": stable_flow,
        "flow_data_available": flow_data_available,
        "flow_schema_version": flow_semantics["schema_version"],
        "token_flow_semantic": flow_semantics["token_semantic"],
        "stablecoin_flow_semantic": flow_semantics["stablecoin_semantic"],
        "flow_composite_semantic": flow_semantics["composite_semantic"],
        "flow_signal_mixed": flow_semantics["mixed_signal"],
        "sentiment_score": _safe_float(stats24.get("sentiment_score")),
        "liquidation_long_usd": _safe_float(stats24.get("liquidation_long_usd")),
        "liquidation_short_usd": _safe_float(stats24.get("liquidation_short_usd")),
        "liquidation_long_to_volume_4h": _safe_float(chart_context.get("liquidation_long_to_volume_4h")),
        "liquidation_short_to_volume_4h": _safe_float(chart_context.get("liquidation_short_to_volume_4h")),
        "qlib_relative_score_8h": qlib_score,
        "qlib_rank_8h": qlib_coin.get("rank"),
        "qlib_percentile_8h": qlib_percentile,
        "p_up_8h": p_up_8h,
        "p_down_8h": p_down_8h,
        "p_flat_8h": p_flat_8h,
        "confidence_8h": confidence_8h,
    }

    qlib_direction = "NONE"
    if max(p_up_8h, p_down_8h) < 0.55:
        qlib_direction = "FLAT"
    elif p_up_8h >= p_down_8h:
        qlib_direction = "LONG"
    else:
        qlib_direction = "SHORT"

    regime_1d = _derive_regime_1d(macro_snapshot, market_snapshot)
    grid_setup = _derive_grid_setup(
        symbol=f"{symbol}-USDT",
        price=market_snapshot["price"],
        atr=_safe_float(market_snapshot.get("atr_14")),
        adx_14=_safe_float(market_snapshot.get("adx_14")),
        p_up_8h=p_up_8h,
        p_down_8h=p_down_8h,
        p_flat_8h=p_flat_8h,
        macro_mode=macro_snapshot["macro_mode"],
        support_level=market_snapshot.get("structure_support_12bar_volume_confirmed"),
        resistance_level=market_snapshot.get("structure_resistance_12bar_volume_confirmed"),
        bb_width=_safe_float(market_snapshot.get("bb_width")),
        bb_pct_b=_safe_float(market_snapshot.get("bb_pct_b"), 0.5),
        bb_mid_slope_pct=_safe_float(market_snapshot.get("bb_mid_slope_pct")),
        adx_delta=_safe_float(market_snapshot.get("adx_delta")),
        recent_close_drift_pct=_safe_float(market_snapshot.get("recent_close_drift_pct")),
        range_edge_close_count=int(_safe_float(market_snapshot.get("range_edge_close_count"))),
        macro_horizon=macro_snapshot.get("macro_horizon", "NOISE"),
        macro_key_events=macro_snapshot.get("key_events") or macro_snapshot.get("key_tags") or [],
        flow_composite_semantic=flow_semantics["composite_semantic"],
        ma5_cross_up_ma10_1d=bool(market_snapshot.get("ma5_cross_up_ma10_1d")),
        ma5_cross_down_ma10_1d=bool(market_snapshot.get("ma5_cross_down_ma10_1d")),
        preflight_data_ok=bool(market_snapshot.get("grid_preflight_data_ok")),
        preflight_missing_fields=market_snapshot.get("grid_preflight_missing_fields") or [],
    )
    decision_ready_features = {
        "regime_1d": regime_1d,
        "macro_mode": macro_snapshot["macro_mode"],
        "macro_horizon": macro_snapshot["macro_horizon"],
        "macro_permission": macro_snapshot["macro_permission"],
        "event_risk_active": bool(macro_snapshot["macro_event_window"]),
        "usd_strength_flag": "USD_STRENGTH" in (macro_snapshot.get("key_events") or []) or macro_snapshot.get("dxy_trend") == "UP",
        "yen_stress_flag": "YEN_STRESS" in (macro_snapshot.get("key_events") or []) or macro_snapshot.get("usdjpy_trend") == "DOWN",
        "flow_data_available": flow_data_available,
        "flow_schema_version": flow_semantics["schema_version"],
        "flow_token_semantic": flow_semantics["token_semantic"],
        "flow_stablecoin_semantic": flow_semantics["stablecoin_semantic"],
        "flow_composite_semantic": flow_semantics["composite_semantic"],
        "flow_signal_mixed": flow_semantics["mixed_signal"],
        "flow_support_long": flow_semantics["long_support"],
        "flow_support_short": flow_semantics["short_support"],
        "qlib_relative_score_8h": qlib_score,
        "qlib_percentile_8h": qlib_percentile,
        "p_up_8h": p_up_8h,
        "p_down_8h": p_down_8h,
        "p_flat_8h": p_flat_8h,
        "confidence_8h": confidence_8h,
        "qlib_direction": qlib_direction,
        "qlib_direction_confident": max(p_up_8h, p_down_8h) >= GLOBAL_CONFIG["qlib_prob_threshold"],
        "qlib_top_bucket": bool((qlib_coin.get("rank") or 999) <= GLOBAL_CONFIG["qlib_rank_bucket_size"]),
        "qlib_bottom_bucket": bool((qlib_coin.get("rank") or 0) >= len(TRACKED_SYMBOLS) - GLOBAL_CONFIG["qlib_rank_bucket_size"] + 1),
        "range_regime": grid_setup["range_regime"],
        "grid_candidate_eligible": grid_setup["grid_candidate_eligible"],
        "range_lower_bound": grid_setup["range_lower_bound"],
        "range_upper_bound": grid_setup["range_upper_bound"],
        "range_width_pct": grid_setup["range_width_pct"],
        "price_position_in_range": grid_setup["price_position_in_range"],
        "grid_mode": grid_setup["grid_mode"],
        "grid_count": grid_setup["grid_count"],
        "grid_spacing_pct": grid_setup["grid_spacing_pct"],
        "min_profitable_spacing_pct": grid_setup["min_profitable_spacing_pct"],
        "grid_spacing_profitable": grid_setup["spacing_profitable"],
        "grid_bb_width": grid_setup["bb_width"],
        "grid_bb_pct_b": grid_setup["bb_pct_b"],
        "grid_bb_mid_slope_pct": grid_setup["bb_mid_slope_pct"],
        "grid_bb_width_ok": grid_setup["bb_width_ok"],
        "grid_bb_slope_ok": grid_setup["bb_slope_ok"],
        "grid_adx_delta": grid_setup["adx_delta"],
        "grid_recent_close_drift_pct": grid_setup["recent_close_drift_pct"],
        "grid_range_edge_close_count": grid_setup["range_edge_close_count"],
        "grid_trend_risk_ok": grid_setup["trend_risk_ok"],
        "grid_preflight_data_ok": grid_setup["preflight_data_ok"],
        "grid_preflight_missing_fields": grid_setup["preflight_missing_fields"],
        "grid_macro_trend_ok": grid_setup["macro_trend_ok"],
        "grid_macro_block_reasons": grid_setup["macro_block_reasons"],
        "ma5_cross_up_ma10_1d": bool(market_snapshot.get("ma5_cross_up_ma10_1d")),
        "ma5_cross_down_ma10_1d": bool(market_snapshot.get("ma5_cross_down_ma10_1d")),
        "ma5_10_gap_pct_1d": _safe_float(market_snapshot.get("ma5_10_gap_pct_1d")),
        "max_profitable_grid_count": grid_setup["max_profitable_grid_count"],
        "grid_review_after_hours": grid_setup["review_after_hours"],
        "grid_extension_step_hours": grid_setup["extension_step_hours"],
        "grid_max_lifetime_hours": grid_setup["max_lifetime_hours"],
    }

    snapshot_ts = _snapshot_timestamp()
    snapshot = {
        "decision_id": f"{cycle_id}_{symbol}",
        "symbol": f"{symbol}-USDT",
        "cycleId": cycle_id,
        "timeframe": GLOBAL_CONFIG["timeframe"],
        "snapshot_timestamp": snapshot_ts,
        "snapshot_time": _timestamp_to_utc_iso(snapshot_ts),
        "snapshot_time_local": _timestamp_to_local_iso(snapshot_ts),
        "local_timezone": LOCAL_TZ_NAME,
        "market_snapshot": market_snapshot,
        "onchain_snapshot": onchain_snapshot,
        "macro_snapshot": macro_snapshot,
        "position_snapshot": position_snapshot,
        "decision_ready_features": decision_ready_features,
        "quality_score": _quality_score(market_snapshot, onchain_snapshot, macro_snapshot),
    }
    snapshot["is_decision_eligible"] = snapshot["quality_score"] >= 0.70
    return snapshot


def _derive_regime_1d(macro_snapshot: Dict[str, Any], market_snapshot: Dict[str, Any]) -> str:
    macro_mode = macro_snapshot.get("macro_mode")
    rsi = _safe_float(market_snapshot.get("rsi_4h"), 50.0)
    if macro_mode == "RISK_OFF":
        return "BEAR"
    if macro_mode == "RISK_ON":
        return "BULL"
    if rsi >= 55:
        return "BULL"
    if rsi <= 45:
        return "BEAR"
    return "CHOP"


def _quality_score(market_snapshot: Dict[str, Any], onchain_snapshot: Dict[str, Any], macro_snapshot: Dict[str, Any]) -> float:
    checks = [
        market_snapshot.get("price", 0) > 0,
        market_snapshot.get("rsi_4h", 0) > 0,
        market_snapshot.get("adx_14", 0) > 0,
        market_snapshot.get("volume_ratio", 0) > 0,
        macro_snapshot.get("macro_mode") is not None,
        onchain_snapshot.get("qlib_relative_score_8h") is not None,
    ]
    return round(sum(1 for x in checks if x) / len(checks), 2)


def _rrr(intent: str, entry: float, sl: float, tp: float) -> float:
    if intent == "LONG":
        risk = entry - sl
        reward = tp - entry
    elif intent == "GRID_NEUTRAL":
        risk = abs(entry - sl)
        reward = abs(tp - entry)
    else:
        risk = sl - entry
        reward = entry - tp
    if risk <= 0:
        return 0.0
    return round(reward / risk, 2)


def _entry_type_for_blueprint(blueprint: str) -> str:
    if blueprint == "Blueprint_G1":
        return "GRID_BOT"
    if blueprint in {"Blueprint_A1", "Blueprint_A2"}:
        return "MARKET"
    return "MARKET"


def _strategy_family_for_intent(intent: str) -> str:
    return STRATEGY_FAMILY_GRID if intent == "GRID_NEUTRAL" else STRATEGY_FAMILY_DIRECTIONAL


def _grid_symbol_config(symbol: str) -> Dict[str, float]:
    return {**GLOBAL_CONFIG, **GRID_SYMBOL_CONFIG.get(symbol, {})}


def _canonical_symbol(value: Any) -> str:
    raw = str(value or "").upper()
    if not raw:
        return ""
    if raw.endswith("-SWAP"):
        raw = raw[:-5]
    if raw.endswith("-USDT"):
        return raw
    return f"{raw}-USDT"


def _grid_record_failure_reason(record: Dict[str, Any]) -> Optional[str]:
    execution = record.get("execution") or {}
    reason = str(execution.get("runtime_reason") or execution.get("failure_reason") or "").strip()
    if reason in GRID_COOLDOWN_FAILURE_REASONS:
        return reason
    if reason == "grid_max_lifetime_stop" and _safe_float(execution.get("realized_pnl")) <= 0:
        return reason
    pnl = execution.get("realized_pnl")
    if pnl is not None and _safe_float(pnl) < 0:
        return "negative_realized_pnl"
    return None


def _grid_record_event_time(record: Dict[str, Any]) -> Optional[datetime]:
    execution = record.get("execution") or {}
    for key in ("closed_at", "updated_at", "executed_at"):
        dt = _parse_dt(execution.get(key) or record.get(key))
        if dt is not None:
            return dt
    return _parse_dt(record.get("updated_at") or record.get("created_at"))


def _grid_cooldown_state(symbol: str, records: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or _now_utc()
    target_symbol = _canonical_symbol(symbol)
    lookback_since = now - timedelta(hours=float(GLOBAL_CONFIG["grid_cooldown_failure_lookback_hours"]))
    failures: List[Dict[str, Any]] = []
    for record in records if isinstance(records, list) else []:
        risk_review = record.get("riskReview") or {}
        execution = record.get("execution") or {}
        if _canonical_symbol(record.get("symbol")) != target_symbol:
            continue
        if risk_review.get("strategy_family") != STRATEGY_FAMILY_GRID and execution.get("execution_action") != "START_GRID_BOT":
            continue
        reason = _grid_record_failure_reason(record)
        if not reason:
            continue
        event_time = _grid_record_event_time(record)
        if event_time is None or event_time < lookback_since or event_time > now:
            continue
        failures.append({
            "decisionId": record.get("decisionId"),
            "reason": reason,
            "at": event_time,
            "positionState": record.get("positionState"),
            "realized_pnl": _safe_float(execution.get("realized_pnl")),
        })

    failures.sort(key=lambda item: item["at"], reverse=True)
    if not failures:
        return {"blocked": False, "failure_count": 0, "failure_reasons": [], "cooldown_until": None}

    failure_count = len(failures)
    threshold = int(GLOBAL_CONFIG["grid_cooldown_failure_threshold"])
    cooldown_hours = (
        float(GLOBAL_CONFIG["grid_cooldown_multi_failure_hours"])
        if failure_count >= threshold
        else float(GLOBAL_CONFIG["grid_cooldown_single_failure_hours"])
    )
    latest_failure_at = failures[0]["at"]
    cooldown_until = latest_failure_at + timedelta(hours=cooldown_hours)
    blocked = now < cooldown_until
    return {
        "blocked": blocked,
        "failure_count": failure_count,
        "failure_reasons": [item["reason"] for item in failures[:5]],
        "last_failure_at": latest_failure_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cooldown_until": cooldown_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cooldown_hours": cooldown_hours,
        "recent_failures": [
            {
                **{k: v for k, v in item.items() if k != "at"},
                "at": item["at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            for item in failures[:5]
        ],
    }


def _derive_grid_macro_trend_gate(
    *,
    macro_mode: str,
    macro_horizon: str,
    macro_key_events: List[str],
    flow_composite_semantic: str,
    ma5_cross_up_ma10_1d: bool,
    ma5_cross_down_ma10_1d: bool,
) -> Dict[str, Any]:
    tags = {str(tag).upper() for tag in (macro_key_events or [])}
    reasons: List[str] = []
    bullish_macro_cluster = (
        "LIQUIDITY_EXPANDING" in tags
        and bool(tags & {"FED_DOVISH", "CPI_COOL", "RISK_ON_NEWS", "USD_WEAKNESS"})
    )
    bearish_macro_cluster = (
        "LIQUIDITY_CONTRACTING" in tags
        and bool(tags & {"FED_HAWKISH", "CPI_HOT", "RISK_OFF_NEWS", "USD_STRENGTH", "YEN_STRESS"})
    )
    directional_swing_macro = (
        macro_mode in {"RISK_ON", "RISK_OFF"}
        and str(macro_horizon).upper() in GLOBAL_CONFIG["grid_block_macro_horizons"]
    )
    if bullish_macro_cluster:
        reasons.append("bullish_liquidity_macro_cluster")
    if bearish_macro_cluster:
        reasons.append("bearish_liquidity_macro_cluster")
    if directional_swing_macro:
        reasons.append("directional_swing_macro")
    if macro_mode == "RISK_ON" and flow_composite_semantic == "LONG_SUPPORT":
        reasons.append("risk_on_with_long_flow_support")
    if macro_mode == "RISK_OFF" and flow_composite_semantic == "SHORT_SUPPORT":
        reasons.append("risk_off_with_short_flow_support")
    if ma5_cross_up_ma10_1d:
        reasons.append("ma5_cross_up_ma10_1d")
    if ma5_cross_down_ma10_1d:
        reasons.append("ma5_cross_down_ma10_1d")
    return {
        "ok": not reasons,
        "reasons": reasons,
    }


def _derive_grid_setup(
    symbol: str,
    price: float,
    atr: float,
    adx_14: float,
    p_up_8h: float,
    p_down_8h: float,
    p_flat_8h: float,
    macro_mode: str,
    support_level: Any,
    resistance_level: Any,
    bb_width: float = 0.0,
    bb_pct_b: float = 0.5,
    bb_mid_slope_pct: float = 0.0,
    adx_delta: float = 0.0,
    recent_close_drift_pct: float = 0.0,
    range_edge_close_count: int = 0,
    macro_horizon: str = "NOISE",
    macro_key_events: Optional[List[str]] = None,
    flow_composite_semantic: str = "MIXED",
    ma5_cross_up_ma10_1d: bool = False,
    ma5_cross_down_ma10_1d: bool = False,
    preflight_data_ok: bool = False,
    preflight_missing_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    grid_config = _grid_symbol_config(symbol)
    fallback_half_range = max(atr * 2.0, price * 0.025)
    lower_bound = _safe_float(support_level)
    upper_bound = _safe_float(resistance_level)
    if lower_bound <= 0 or lower_bound >= price:
        lower_bound = round(price - fallback_half_range, 4)
    if upper_bound <= price:
        upper_bound = round(price + fallback_half_range, 4)
    if upper_bound <= lower_bound:
        lower_bound = round(price - fallback_half_range, 4)
        upper_bound = round(price + fallback_half_range, 4)

    range_mid = max((upper_bound + lower_bound) / 2.0, 1e-9)
    range_width_pct = (upper_bound - lower_bound) / range_mid
    price_position_in_range = (price - lower_bound) / max(upper_bound - lower_bound, 1e-9)
    fee_rate = float(GLOBAL_CONFIG["grid_fee_rate"])
    slippage_rate = float(GLOBAL_CONFIG["grid_slippage_rate"])
    profit_buffer_rate = float(GLOBAL_CONFIG["grid_profit_buffer_rate"])
    min_profitable_spacing_pct = 2 * fee_rate + 2 * slippage_rate + profit_buffer_rate
    width_ok = (
        grid_config["grid_width_min_pct"]
        <= range_width_pct
        <= grid_config["grid_width_max_pct"]
    )
    flat_regime = (
        p_flat_8h >= GLOBAL_CONFIG["grid_flat_min_threshold"]
        and p_flat_8h >= max(p_up_8h, p_down_8h)
        and max(p_up_8h, p_down_8h) < GLOBAL_CONFIG["grid_prob_ceiling"]
        and abs(p_up_8h - p_down_8h) < GLOBAL_CONFIG["grid_prob_gap_max"]
        and adx_14 <= GLOBAL_CONFIG["grid_adx_max"]
    )
    price_position_ok = (
        grid_config["grid_price_position_min"]
        <= price_position_in_range
        <= grid_config["grid_price_position_max"]
    )
    bb_width_ok = (
        bb_width <= 0
        or (
            GLOBAL_CONFIG["grid_bb_width_min_pct"]
            <= bb_width
            <= GLOBAL_CONFIG["grid_bb_width_max_pct"]
        )
    )
    bb_slope_ok = abs(bb_mid_slope_pct) <= GLOBAL_CONFIG["grid_bb_mid_slope_max_pct"]
    trend_risk_ok = (
        adx_delta <= grid_config["grid_adx_delta_max"]
        and abs(recent_close_drift_pct) <= grid_config["grid_recent_drift_max_pct"]
        and range_edge_close_count <= grid_config["grid_max_edge_close_count"]
    )
    macro_trend_gate = _derive_grid_macro_trend_gate(
        macro_mode=macro_mode,
        macro_horizon=macro_horizon,
        macro_key_events=macro_key_events or [],
        flow_composite_semantic=flow_composite_semantic,
        ma5_cross_up_ma10_1d=ma5_cross_up_ma10_1d,
        ma5_cross_down_ma10_1d=ma5_cross_down_ma10_1d,
    )
    target_spacing_pct = max(min_profitable_spacing_pct * 1.5, 0.008)
    raw_grid_count = int(round(range_width_pct / target_spacing_pct))
    raw_grid_count = max(2, raw_grid_count)
    max_profitable_grid_count = int(range_width_pct / max(min_profitable_spacing_pct, 1e-9))
    max_profitable_grid_count = max(2, max_profitable_grid_count)
    grid_count = min(24, raw_grid_count, max_profitable_grid_count)
    grid_count = max(2, grid_count)
    realized_grid_spacing_pct = range_width_pct / grid_count
    spacing_profitable = realized_grid_spacing_pct > min_profitable_spacing_pct
    range_regime = (
        flat_regime
        and macro_mode != "EVENT_DRIVEN"
        and width_ok
        and price_position_ok
        and preflight_data_ok
        and bb_width_ok
        and bb_slope_ok
        and trend_risk_ok
        and macro_trend_gate["ok"]
        and spacing_profitable
    )

    return {
        "range_lower_bound": round(lower_bound, 4),
        "range_upper_bound": round(upper_bound, 4),
        "range_width_pct": round(range_width_pct, 4),
        "price_position_in_range": round(price_position_in_range, 4),
        "range_regime": range_regime,
        "grid_candidate_eligible": range_regime,
        "grid_mode": "ARITHMETIC",
        "grid_count": grid_count,
        "grid_spacing_pct": round(realized_grid_spacing_pct, 4),
        "min_profitable_spacing_pct": round(min_profitable_spacing_pct, 4),
        "spacing_profitable": spacing_profitable,
        "price_position_ok": price_position_ok,
        "bb_width": round(bb_width, 4),
        "bb_pct_b": round(bb_pct_b, 4),
        "bb_mid_slope_pct": round(bb_mid_slope_pct, 4),
        "bb_width_ok": bb_width_ok,
        "bb_slope_ok": bb_slope_ok,
        "adx_delta": round(adx_delta, 4),
        "recent_close_drift_pct": round(recent_close_drift_pct, 4),
        "range_edge_close_count": range_edge_close_count,
        "trend_risk_ok": trend_risk_ok,
        "preflight_data_ok": preflight_data_ok,
        "preflight_missing_fields": preflight_missing_fields or [],
        "macro_trend_ok": macro_trend_gate["ok"],
        "macro_block_reasons": macro_trend_gate["reasons"],
        "max_profitable_grid_count": max_profitable_grid_count,
        "review_after_hours": int(grid_config["grid_review_after_hours"]),
        "extension_step_hours": int(grid_config["grid_extension_step_hours"]),
        "max_lifetime_hours": int(grid_config["grid_max_lifetime_hours"]),
    }


def _build_candidate_proposals(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    symbol = snapshot["symbol"]
    features = snapshot["decision_ready_features"]
    market = snapshot["market_snapshot"]
    onchain = snapshot["onchain_snapshot"]
    atr = max(_safe_float(market.get("atr_14")), _safe_float(market.get("price")) * 0.01)
    price = _safe_float(market.get("price"))
    proposals: List[Dict[str, Any]] = []

    def add_candidate(intent: str, blueprint: str, rationale: str, entry: float, sl: float, tp: float,
                      reference_values: Optional[Dict[str, float]] = None,
                      invalidation_basis: str = "", invalidation_conditions: Optional[Dict[str, Any]] = None) -> None:
        proposals.append({
            "strategy_family": _strategy_family_for_intent(intent),
            "decision_intent": intent,
            "trigger_source": blueprint,
            "rationale": rationale,
            "entry_type": _entry_type_for_blueprint(blueprint),
            "proposed_entry_price": round(entry, 4),
            "proposed_sl_price": round(sl, 4),
            "proposed_tp_price": round(tp, 4),
            "reference_values": reference_values or {},
            "invalidation_basis": invalidation_basis,
            "invalidation_conditions": invalidation_conditions or {"operator": "OR", "rules": [], "persistence": 1},
        })

    def add_grid_candidate() -> None:
        if symbol not in GRID_ENABLED_SYMBOLS:
            return
        if features.get("grid_preflight_data_ok") is not True:
            return
        if features.get("grid_macro_trend_ok") is False:
            return
        recent_records = db.get_data("trade_decision_records", [])
        cooldown = _grid_cooldown_state(symbol, recent_records if isinstance(recent_records, list) else [])
        if cooldown.get("blocked"):
            return
        lower_bound = _safe_float(features.get("range_lower_bound"))
        upper_bound = _safe_float(features.get("range_upper_bound"))
        grid_count = int(features.get("grid_count") or 8)
        review_after_hours = int(features.get("grid_review_after_hours") or GLOBAL_CONFIG["grid_review_after_hours"])
        extension_step_hours = int(features.get("grid_extension_step_hours") or GLOBAL_CONFIG["grid_extension_step_hours"])
        max_lifetime_hours = int(features.get("grid_max_lifetime_hours") or GLOBAL_CONFIG["grid_max_lifetime_hours"])
        grid_spacing_pct = _safe_float(features.get("grid_spacing_pct"))
        min_profitable_spacing_pct = _safe_float(features.get("min_profitable_spacing_pct"))
        price_position_in_range = _safe_float(features.get("price_position_in_range"))
        funding_zscore = abs(_safe_float(market.get("funding_zscore")))
        if funding_zscore > GLOBAL_CONFIG["grid_funding_zscore_max"]:
            return
        stop_loss = round(max(0.0, lower_bound - 0.5 * atr), 4)
        take_profit = round(upper_bound + 0.5 * atr, 4)
        grid_bias = "NEUTRAL"
        bb_pct_b = _safe_float(market.get("bb_pct_b"), 0.5)
        volume_boundary_confirmed = lower_bound > 0 and upper_bound > 0 and (
            market.get("structure_support_12bar_volume_confirmed") is not None
            or market.get("structure_resistance_12bar_volume_confirmed") is not None
        )
        if price_position_in_range >= 0.65 or bb_pct_b >= 0.80:
            grid_bias = "SHORT_BIASED"
        elif 0 < price_position_in_range <= 0.35 or bb_pct_b <= 0.20:
            grid_bias = "LONG_BIASED"
        proposals.append({
            "strategy_family": STRATEGY_FAMILY_GRID,
            "decision_intent": "GRID_NEUTRAL",
            "trigger_source": "Blueprint_G1",
            "rationale": "high flat probability with contained range and low trend strength",
            "entry_type": "GRID_BOT",
            "proposed_entry_price": round(price, 4),
            "proposed_sl_price": stop_loss,
            "proposed_tp_price": take_profit,
            "reference_values": {
                "range_lower_bound": round(lower_bound, 4),
                "range_upper_bound": round(upper_bound, 4),
                "range_width_pct": _safe_float(features.get("range_width_pct")),
                "grid_count": grid_count,
                "grid_mode": str(features.get("grid_mode") or "ARITHMETIC"),
                "grid_bias": grid_bias,
                "grid_spacing_pct": grid_spacing_pct,
                "min_profitable_spacing_pct": min_profitable_spacing_pct,
                "price_position_in_range": price_position_in_range,
                "bb_width": _safe_float(market.get("bb_width")),
                "bb_pct_b": bb_pct_b,
                "bb_mid_slope_pct": _safe_float(market.get("bb_mid_slope_pct")),
                "adx_delta": _safe_float(market.get("adx_delta")),
                "recent_close_drift_pct": _safe_float(market.get("recent_close_drift_pct")),
                "range_edge_close_count": int(_safe_float(market.get("range_edge_close_count"))),
                "preflight_data_ok": bool(features.get("grid_preflight_data_ok")),
                "preflight_missing_fields": features.get("grid_preflight_missing_fields") or [],
                "macro_trend_ok": bool(features.get("grid_macro_trend_ok", True)),
                "macro_block_reasons": list(features.get("grid_macro_block_reasons") or []),
                "ma5_cross_up_ma10_1d": bool(features.get("ma5_cross_up_ma10_1d")),
                "ma5_cross_down_ma10_1d": bool(features.get("ma5_cross_down_ma10_1d")),
                "ma5_10_gap_pct_1d": _safe_float(features.get("ma5_10_gap_pct_1d")),
                "grid_cooldown_blocked": bool(cooldown.get("blocked")),
                "grid_cooldown_failure_count": int(cooldown.get("failure_count") or 0),
                "grid_cooldown_until": cooldown.get("cooldown_until"),
                "grid_cooldown_failure_reasons": cooldown.get("failure_reasons") or [],
                "volume_boundary_confirmed": volume_boundary_confirmed,
                "funding_zscore": _safe_float(market.get("funding_zscore")),
                "review_after_hours": review_after_hours,
                "extension_step_hours": extension_step_hours,
                "max_lifetime_hours": max_lifetime_hours,
                "p_flat_8h": _safe_float(onchain.get("p_flat_8h")),
                "p_up_8h": _safe_float(onchain.get("p_up_8h")),
                "p_down_8h": _safe_float(onchain.get("p_down_8h")),
            },
            "invalidation_basis": "range breakout, event window activation, or flat regime deterioration",
            "invalidation_conditions": {
                "operator": "OR",
                "rules": [
                    {"field": "close_below_range_lower_2bars", "op": "==", "value": True},
                    {"field": "close_above_range_upper_2bars", "op": "==", "value": True},
                    {"field": "macro_mode", "op": "==", "value": "EVENT_DRIVEN"},
                    {"field": "grid_macro_trend_ok", "op": "==", "value": False},
                    {"field": "p_flat_8h", "op": "<", "value": GLOBAL_CONFIG["grid_flat_exit_threshold"]},
                ],
                "persistence": 1,
            },
        })

    # Blueprint_A2
    if (
        snapshot["symbol"] in BLUEPRINT_A2_ENABLED_SYMBOLS
        and
        market.get("wick_ratio_upper", 0) >= 30
        and market.get("rsi_4h", 50) > 60
        and features.get("regime_1d") == "BEAR"
    ):
        trigger_high = round(price + atr * 0.5, 4)
        sl = round(trigger_high * 1.002, 4)
        tp = round(price - max(sl - price, atr) * 2.0, 4)
        add_candidate(
            "SHORT",
            "Blueprint_A2",
            "bearish wick reversal in daily bear regime",
            price,
            sl,
            tp,
            {"trigger_candle_high": trigger_high},
            "trigger candle high broken",
            {
                "operator": "OR",
                "rules": [{"field": "price", "op": ">=", "value_ref": "trigger_candle_high"}],
                "persistence": 1,
            },
        )

    # Blueprint_E1 / E2
    qlib_score = onchain.get("qlib_relative_score_8h", 0.0)
    qlib_percentile = onchain.get("qlib_percentile_8h", 0.0)
    qlib_rank = int(onchain.get("qlib_rank_8h") or 999)
    p_up_8h = _safe_float(onchain.get("p_up_8h"))
    p_down_8h = _safe_float(onchain.get("p_down_8h"))
    p_flat_8h = _safe_float(onchain.get("p_flat_8h"))
    funding_z = _safe_float(market.get("funding_zscore"))
    token_flow = _safe_float(onchain.get("token_net_flow"))
    stable_flow = _safe_float(onchain.get("stablecoin_net_flow"))
    is_overheated = market.get("rsi_4h", 50) > 70
    funding_extreme_positive = funding_z >= 2.0
    funding_extreme_negative = funding_z <= -2.0
    qlib_bucket_size = int(GLOBAL_CONFIG.get("qlib_rank_bucket_size", 3))
    qlib_prob_threshold = float(GLOBAL_CONFIG.get("qlib_prob_threshold", 0.55))
    qlib_prob_gap_threshold = float(GLOBAL_CONFIG.get("qlib_prob_gap_threshold", 0.15))
    qlib_flat_max_threshold = float(GLOBAL_CONFIG.get("qlib_flat_max_threshold", 0.40))
    qlib_invalidation_prob_threshold = float(GLOBAL_CONFIG.get("qlib_invalidation_prob_threshold", 0.45))
    whale_bias = "neutral"
    if token_flow <= -5_000_000 or stable_flow <= -5_000_000:
        whale_bias = "strong_outflow"
    elif token_flow >= 5_000_000 or stable_flow >= 5_000_000:
        whale_bias = "strong_inflow"
    is_squeeze_zone = funding_extreme_negative and whale_bias == "strong_inflow"

    long_rank_pass = qlib_rank <= qlib_bucket_size
    short_rank_pass = qlib_rank >= len(TRACKED_SYMBOLS) - qlib_bucket_size + 1
    long_prob_pass = p_up_8h >= qlib_prob_threshold
    short_prob_pass = p_down_8h >= qlib_prob_threshold
    long_gap_pass = (p_up_8h - p_down_8h) >= qlib_prob_gap_threshold
    short_gap_pass = (p_down_8h - p_up_8h) >= qlib_prob_gap_threshold
    flat_gate_pass = p_flat_8h <= qlib_flat_max_threshold
    long_regime_pass = features.get("regime_1d") != "BEAR"
    short_regime_pass = features.get("regime_1d") != "BULL"
    long_heat_pass = not is_overheated
    short_squeeze_pass = not is_squeeze_zone
    long_funding_pass = not funding_extreme_positive
    short_funding_pass = not funding_extreme_negative
    long_whale_pass = whale_bias != "strong_outflow"
    short_whale_pass = whale_bias != "strong_inflow"

    long_blockers: List[str] = []
    short_blockers: List[str] = []
    if not long_rank_pass:
        long_blockers.append("rank_bucket")
    if not short_rank_pass:
        short_blockers.append("rank_bucket")
    if not long_prob_pass:
        long_blockers.append("prob_threshold")
    if not short_prob_pass:
        short_blockers.append("prob_threshold")
    if not long_gap_pass:
        long_blockers.append("prob_gap")
    if not short_gap_pass:
        short_blockers.append("prob_gap")
    if not flat_gate_pass:
        long_blockers.append("p_flat_gate")
        short_blockers.append("p_flat_gate")
    if not long_regime_pass:
        long_blockers.append("regime")
    if not short_regime_pass:
        short_blockers.append("regime")
    if not long_heat_pass:
        long_blockers.append("overheated")
    if not short_squeeze_pass:
        short_blockers.append("squeeze_zone")
    if not long_funding_pass:
        long_blockers.append("funding_extreme_positive")
    if not short_funding_pass:
        short_blockers.append("funding_extreme_negative")
    if not long_whale_pass:
        long_blockers.append("whale_outflow")
    if not short_whale_pass:
        short_blockers.append("whale_inflow")

    long_eligible = not long_blockers
    short_eligible = not short_blockers
    diagnostic = {
        "qlib_inputs": {
            "qlib_relative_score_8h": qlib_score,
            "qlib_percentile_8h": qlib_percentile,
            "qlib_rank_8h": qlib_rank,
            "p_up_8h": p_up_8h,
            "p_down_8h": p_down_8h,
            "p_flat_8h": p_flat_8h,
            "funding_zscore": funding_z,
            "token_net_flow": token_flow,
            "stablecoin_net_flow": stable_flow,
            "regime_1d": features.get("regime_1d"),
            "whale_bias": whale_bias,
            "is_overheated": is_overheated,
            "is_squeeze_zone": is_squeeze_zone,
        },
        "config": {
            "qlib_rank_bucket_size": qlib_bucket_size,
            "qlib_prob_threshold": qlib_prob_threshold,
            "qlib_prob_gap_threshold": qlib_prob_gap_threshold,
            "qlib_flat_max_threshold": qlib_flat_max_threshold,
        },
        "long_path": {
            "candidate": "Blueprint_E1",
            "checks": {
                "rank_bucket_pass": long_rank_pass,
                "prob_threshold_pass": long_prob_pass,
                "prob_gap_pass": long_gap_pass,
                "flat_gate_pass": flat_gate_pass,
                "regime_pass": long_regime_pass,
                "overheated_pass": long_heat_pass,
                "funding_pass": long_funding_pass,
                "whale_pass": long_whale_pass,
            },
            "eligible": long_eligible,
            "blocked_by": long_blockers,
        },
        "short_path": {
            "candidate": "Blueprint_E2",
            "checks": {
                "rank_bucket_pass": short_rank_pass,
                "prob_threshold_pass": short_prob_pass,
                "prob_gap_pass": short_gap_pass,
                "flat_gate_pass": flat_gate_pass,
                "regime_pass": short_regime_pass,
                "squeeze_pass": short_squeeze_pass,
                "funding_pass": short_funding_pass,
                "whale_pass": short_whale_pass,
            },
            "eligible": short_eligible,
            "blocked_by": short_blockers,
        },
    }
    if long_eligible:
        diagnostic["summary"] = "Blueprint_E1 eligible"
    elif short_eligible:
        diagnostic["summary"] = "Blueprint_E2 eligible"
    else:
        diagnostic["summary"] = (
            "No E candidate: "
            f"long blocked by {', '.join(long_blockers) or 'none'}; "
            f"short blocked by {', '.join(short_blockers) or 'none'}"
        )

    if (
        long_rank_pass
        and long_prob_pass
        and long_gap_pass
        and flat_gate_pass
        and long_regime_pass
        and long_heat_pass
        and long_funding_pass
        and long_whale_pass
    ):
        sl = round(price - 2 * atr, 4)
        tp = round(price + max(price - sl, atr) * 2.0, 4)
        add_candidate(
            "LONG",
            "Blueprint_E1",
            "qlib top-rank directional long with sufficient upside probability",
            price,
            sl,
            tp,
            {
                "qlib_rank_8h": qlib_rank,
                "qlib_percentile_8h": qlib_percentile,
                "qlib_relative_score_8h": qlib_score,
                "p_up_8h": p_up_8h,
                "p_down_8h": p_down_8h,
                "p_flat_8h": p_flat_8h,
            },
            "qlib bullish thesis invalid if upside probability weakens or bear regime returns",
            {
                "operator": "OR",
                "rules": [
                    {"field": "p_up_8h", "op": "<", "value": qlib_invalidation_prob_threshold},
                    {"field": "regime_1d", "op": "==", "value": "BEAR"},
                ],
                "persistence": 1,
            },
        )
    if (
        short_rank_pass
        and short_prob_pass
        and short_gap_pass
        and flat_gate_pass
        and short_regime_pass
        and short_squeeze_pass
        and short_funding_pass
        and short_whale_pass
    ):
        sl = round(price + 2 * atr, 4)
        tp = round(price - max(sl - price, atr) * 2.0, 4)
        add_candidate(
            "SHORT",
            "Blueprint_E2",
            "qlib bottom-rank directional short with sufficient downside probability",
            price,
            sl,
            tp,
            {
                "qlib_rank_8h": qlib_rank,
                "qlib_percentile_8h": qlib_percentile,
                "qlib_relative_score_8h": qlib_score,
                "p_up_8h": p_up_8h,
                "p_down_8h": p_down_8h,
                "p_flat_8h": p_flat_8h,
            },
            "qlib bearish thesis invalid if downside probability weakens or bull regime returns",
            {
                "operator": "OR",
                "rules": [
                    {"field": "p_down_8h", "op": "<", "value": qlib_invalidation_prob_threshold},
                    {"field": "regime_1d", "op": "==", "value": "BULL"},
                ],
                "persistence": 1,
            },
        )

    if features.get("grid_candidate_eligible"):
        add_grid_candidate()

    # Blueprint_F1 / F2 retained runtime variant
    macd_line = _safe_float(market.get("macd_line_4h"))
    macd_signal = _safe_float(market.get("macd_signal_4h"))
    rel_volume_60 = _safe_float(market.get("rel_volume_60"))
    support_stop_long = market.get("structure_support_stop_long")
    resistance_stop_short = market.get("structure_resistance_stop_short")
    symbol_base = str(symbol).replace("-USDT", "").upper()

    if (
        symbol_base not in {"SOL", "DOGE", "BTC"}
        and market.get("rsi_4h", 50) > 50
        and macd_line > macd_signal
        and macd_line > 0
        and macd_signal > 0
        and rel_volume_60 >= 1.5
        and support_stop_long is not None
        and _safe_float(support_stop_long) < price
    ):
        sl = round(_safe_float(support_stop_long), 4)
        tp = round(price + 2 * (price - sl), 4)
        add_candidate(
            "LONG",
            "Blueprint_F1",
            "zero-axis MACD long with rel_volume_60 confirmation",
            price,
            sl,
            tp,
            {
                "structure_support_stop_long": sl,
                "sma50_4h": _safe_float(market.get("sma50_4h")),
            },
            "volume-confirmed support broken with sma50 confirmation or long momentum reverses",
            {
                "operator": "OR",
                "rules": [
                    {"field": "price", "op": "<=", "value_ref": "structure_support_stop_long"},
                ],
                "persistence": 1,
            },
        )

    if (
        symbol_base in {"BNB", "ETH", "DOGE"}
        and market.get("rsi_4h", 50) < 50
        and macd_line < macd_signal
        and macd_line < 0
        and macd_signal < 0
        and rel_volume_60 >= 1.5
        and resistance_stop_short is not None
        and _safe_float(resistance_stop_short) > price
    ):
        sl = round(_safe_float(resistance_stop_short), 4)
        tp = round(price - 2 * (sl - price), 4)
        add_candidate(
            "SHORT",
            "Blueprint_F2",
            "zero-axis MACD short with rel_volume_60 confirmation",
            price,
            sl,
            tp,
            {
                "structure_resistance_stop_short": sl,
                "sma50_4h": _safe_float(market.get("sma50_4h")),
            },
            "volume-confirmed resistance broken with sma50 confirmation or short momentum reverses",
            {
                "operator": "OR",
                "rules": [
                    {"field": "price", "op": ">=", "value_ref": "structure_resistance_stop_short"},
                ],
                "persistence": 1,
            },
        )

    return {
        "symbol": symbol,
        "cycleId": snapshot["cycleId"],
        "timeframe": snapshot["timeframe"],
        "snapshot_timestamp": snapshot["snapshot_timestamp"],
        "candidate_proposals": proposals,
        "e_strategy_diagnostic": diagnostic,
    }


def _validate_candidate_schema(proposal: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    required = [
        "strategy_family",
        "decision_intent",
        "trigger_source",
        "rationale",
        "entry_type",
        "proposed_entry_price",
        "proposed_sl_price",
        "proposed_tp_price",
        "reference_values",
        "invalidation_basis",
        "invalidation_conditions",
    ]
    for field in required:
        if field not in proposal:
            return False, f"missing_{field}"
    if proposal["strategy_family"] not in {STRATEGY_FAMILY_DIRECTIONAL, STRATEGY_FAMILY_GRID}:
        return False, "invalid_strategy_family"
    if proposal["decision_intent"] not in {"LONG", "SHORT", "GRID_NEUTRAL"}:
        return False, "invalid_decision_intent"
    if proposal["entry_type"] not in {"MARKET", "LIMIT", "STOP", "GRID_BOT"}:
        return False, "invalid_entry_type"
    return True, None


def _summarize_candidate_structure(proposals: List[Dict[str, Any]], approved_candidates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    approved_candidates = approved_candidates or []
    intent_groups: Dict[str, List[str]] = {"LONG": [], "SHORT": [], "GRID_NEUTRAL": []}
    for proposal in proposals:
        intent = str(proposal.get("decision_intent") or "")
        source = str(proposal.get("trigger_source") or "")
        if intent in intent_groups and source:
            intent_groups[intent].append(source)

    approved_groups: Dict[str, List[str]] = {"LONG": [], "SHORT": [], "GRID_NEUTRAL": []}
    for proposal in approved_candidates:
        intent = str(proposal.get("decision_intent") or "")
        source = str(proposal.get("trigger_source") or "")
        if intent in approved_groups and source:
            approved_groups[intent].append(source)

    has_long = bool(intent_groups["LONG"])
    has_short = bool(intent_groups["SHORT"])
    has_grid = bool(intent_groups["GRID_NEUTRAL"])
    if has_long and has_short:
        overall_state = "directional_conflict"
    elif len(intent_groups["LONG"]) >= 2 or len(intent_groups["SHORT"]) >= 2:
        overall_state = "same_direction_resonance"
    elif has_long or has_short or has_grid:
        overall_state = "single_signal"
    else:
        overall_state = "no_candidate"

    return {
        "overall_state": overall_state,
        "has_directional_conflict": has_long and has_short,
        "long_count": len(intent_groups["LONG"]),
        "short_count": len(intent_groups["SHORT"]),
        "grid_count": len(intent_groups["GRID_NEUTRAL"]),
        "resonance_groups": {
            "LONG": intent_groups["LONG"],
            "SHORT": intent_groups["SHORT"],
            "GRID_NEUTRAL": intent_groups["GRID_NEUTRAL"],
        },
        "approved_groups": {
            "LONG": approved_groups["LONG"],
            "SHORT": approved_groups["SHORT"],
            "GRID_NEUTRAL": approved_groups["GRID_NEUTRAL"],
        },
        "approved_resonance_strength": max(
            len(approved_groups["LONG"]),
            len(approved_groups["SHORT"]),
            len(approved_groups["GRID_NEUTRAL"]),
        ),
    }


def _evaluate_rules(snapshot: Dict[str, Any], candidate_batch: Dict[str, Any]) -> Dict[str, Any]:
    passed = True
    reason_codes: List[str] = []
    rule_trace: List[Dict[str, Any]] = []
    approved_candidates: List[Dict[str, Any]] = []
    position_snapshot = snapshot["position_snapshot"]
    macro_permission = snapshot["decision_ready_features"].get("macro_permission", "ALLOW_BOTH")
    quality_ok = bool(snapshot.get("is_decision_eligible"))
    proposals = candidate_batch.get("candidate_proposals", []) or []
    candidate_structure = _summarize_candidate_structure(proposals)

    if not quality_ok:
        passed = False
        reason_codes.append("DATA_MISSING")
        rule_trace.append({"rule": "DATA_ELIGIBILITY_CHECK", "passed": False})
    else:
        rule_trace.append({"rule": "DATA_ELIGIBILITY_CHECK", "passed": True})

    if candidate_structure["has_directional_conflict"]:
        reason_codes.append("CANDIDATE_CONFLICT")
        rule_trace.append({
            "rule": "CANDIDATE_CONFLICT_CHECK",
            "passed": False,
            "detail": candidate_structure["resonance_groups"],
        })
    elif proposals:
        rule_trace.append({"rule": "CANDIDATE_CONFLICT_CHECK", "passed": True})
    if candidate_structure["overall_state"] == "same_direction_resonance":
        rule_trace.append({
            "rule": "CANDIDATE_RESONANCE_CHECK",
            "passed": True,
            "detail": candidate_structure["resonance_groups"],
        })

    for proposal in proposals:
        schema_ok, schema_err = _validate_candidate_schema(proposal)
        if not schema_ok:
            passed = False
            reason_codes.append("SCHEMA_VIOLATION")
            rule_trace.append({"rule": "SCHEMA_VALIDATION_CHECK", "passed": False, "detail": schema_err})
            continue

        entry = _safe_float(proposal.get("proposed_entry_price"))
        sl = _safe_float(proposal.get("proposed_sl_price"))
        tp = _safe_float(proposal.get("proposed_tp_price"))
        intent = proposal.get("decision_intent")

        if intent == "GRID_NEUTRAL":
            if not snapshot["decision_ready_features"].get("grid_candidate_eligible") or not snapshot["decision_ready_features"].get("range_regime"):
                passed = False
                reason_codes.append("CHOP_FILTER_BLOCKED")
                rule_trace.append({"rule": "GRID_REGIME_CHECK", "passed": False, "detail": "range_regime_false"})
                continue
            range_width_pct = _safe_float(snapshot["decision_ready_features"].get("range_width_pct"))
            grid_config = _grid_symbol_config(str(snapshot.get("symbol") or ""))
            if not (
                grid_config["grid_width_min_pct"]
                <= range_width_pct
                <= grid_config["grid_width_max_pct"]
            ):
                passed = False
                reason_codes.append("GRID_WIDTH_INVALID")
                rule_trace.append({"rule": "GRID_WIDTH_CHECK", "passed": False, "detail": {"range_width_pct": range_width_pct}})
                continue
            existing_side = position_snapshot.get("position_side")
            if existing_side not in {None, "", "NONE"}:
                passed = False
                reason_codes.append("POSITION_CONFLICT")
                rule_trace.append({"rule": "GRID_POSITION_MUTEX_CHECK", "passed": False, "detail": existing_side})
                continue
            if snapshot["decision_ready_features"].get("macro_mode") == "EVENT_DRIVEN":
                passed = False
                reason_codes.append("GRID_EVENT_RISK_BLOCKED")
                rule_trace.append({"rule": "GRID_EVENT_WINDOW_CHECK", "passed": False, "detail": "event_driven"})
                continue
            if snapshot["decision_ready_features"].get("grid_preflight_data_ok") is not True:
                passed = False
                reason_codes.append("GRID_PREFLIGHT_DATA_MISSING")
                rule_trace.append({
                    "rule": "GRID_PREFLIGHT_DATA_CHECK",
                    "passed": False,
                    "detail": snapshot["decision_ready_features"].get("grid_preflight_missing_fields") or [],
                })
                continue
            if snapshot["decision_ready_features"].get("grid_macro_trend_ok") is False:
                passed = False
                reason_codes.append("GRID_MACRO_TREND_BLOCKED")
                rule_trace.append({
                    "rule": "GRID_MACRO_TREND_CHECK",
                    "passed": False,
                    "detail": snapshot["decision_ready_features"].get("grid_macro_block_reasons") or [],
                })
                continue

        rrr = _rrr(intent, entry, sl, tp)
        if rrr < GLOBAL_CONFIG["min_rrr"]:
            passed = False
            reason_codes.append("LOW_RRR")
            rule_trace.append({"rule": "MIN_RRR_CHECK", "passed": False, "detail": {"trigger_source": proposal.get("trigger_source"), "rrr": rrr}})
            continue

        existing_side = position_snapshot.get("position_side")
        if existing_side == "LONG" and intent == "SHORT":
            passed = False
            reason_codes.append("POSITION_CONFLICT")
            rule_trace.append({"rule": "POSITION_CONFLICT_CHECK", "passed": False, "detail": "existing_long"})
            continue
        if existing_side == "SHORT" and intent == "LONG":
            passed = False
            reason_codes.append("POSITION_CONFLICT")
            rule_trace.append({"rule": "POSITION_CONFLICT_CHECK", "passed": False, "detail": "existing_short"})
            continue

        if macro_permission == "ALLOW_SHORT" and intent == "LONG":
            passed = False
            reason_codes.append("BEAR_MARKET_LONG_BLOCKED")
            rule_trace.append({"rule": "REGIME_PERMISSION_CHECK", "passed": False, "detail": "macro_short_only"})
            continue
        if macro_permission == "ALLOW_LONG" and intent == "SHORT":
            passed = False
            reason_codes.append("NO_CONFIRMATION")
            rule_trace.append({"rule": "REGIME_PERMISSION_CHECK", "passed": False, "detail": "macro_long_only"})
            continue

        leverage_target = GLOBAL_CONFIG["grid_leverage_default"] if intent == "GRID_NEUTRAL" else 3.0
        leverage = min(GLOBAL_CONFIG["global_leverage_max"], max(GLOBAL_CONFIG["global_leverage_min"], leverage_target))
        liq_buffer = _estimate_pretrade_liq_buffer(entry, sl, leverage)
        if liq_buffer <= 0.05:
            passed = False
            reason_codes.append("RISK_LIMIT_EXCEEDED")
            rule_trace.append({"rule": "LIQUIDATION_BUFFER_PRECHECK", "passed": False, "detail": {"estimated_distance_to_liq": liq_buffer}})
            continue

        rule_trace.append({
            "rule": "CANDIDATE_ACCEPTED",
            "passed": True,
            "detail": {"trigger_source": proposal.get("trigger_source"), "rrr": rrr, "estimated_distance_to_liq": liq_buffer},
        })
        resonance_bonus = 0.0
        if candidate_structure["overall_state"] == "same_direction_resonance":
            same_direction_sources = candidate_structure["resonance_groups"].get(intent, [])
            if len(same_direction_sources) >= 2:
                resonance_bonus = min(0.2, 0.05 * (len(same_direction_sources) - 1))
        approved_candidates.append({
            **proposal,
            "rrr": rrr,
            "estimated_distance_to_liq": liq_buffer,
            "resonance_bonus": round(resonance_bonus, 2),
        })

    if proposals and not approved_candidates and not reason_codes:
        passed = False
        reason_codes.append("NO_CONFIRMATION")

    return {
        "symbol": snapshot["symbol"],
        "cycleId": snapshot["cycleId"],
        "stage": "pre_trade_filter",
        "passed": passed and bool(approved_candidates),
        "reason_codes": sorted(set(reason_codes)),
        "approved_candidates": approved_candidates,
        "rule_trace": rule_trace,
        "candidate_structure": _summarize_candidate_structure(proposals, approved_candidates),
    }


def _estimate_pretrade_liq_buffer(entry_price: float, stop_loss: float, leverage: float) -> float:
    risk_fraction = abs(entry_price - stop_loss) / max(entry_price, 1e-9)
    base_buffer = max(0.03, 1.0 / max(leverage, 1.0))
    return round(base_buffer - risk_fraction, 4)


def _cap_position_size_by_max_loss(account_equity: float, entry_price: float, stop_loss: float, requested_size_usd: float) -> float:
    stop_fraction = abs(entry_price - stop_loss) / max(entry_price, 1e-9)
    if stop_fraction <= 0:
        return 0.0
    max_loss_usd = account_equity * GLOBAL_CONFIG["approved_risk_fraction"]
    risk_capped_size = max_loss_usd / stop_fraction
    return min(requested_size_usd, risk_capped_size)


def _build_risk_review(snapshot: Dict[str, Any], rule_evaluation: Dict[str, Any]) -> Dict[str, Any]:
    return _build_risk_review_with_research(snapshot, rule_evaluation, None)


def _build_risk_review_with_research(snapshot: Dict[str, Any], rule_evaluation: Dict[str, Any], research_output: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not rule_evaluation.get("passed") or not rule_evaluation.get("approved_candidates"):
        return {
            "symbol": snapshot["symbol"],
            "cycleId": snapshot["cycleId"],
            "strategy_family": None,
            "approved": False,
            "final_intent": "NO_TRADE",
            "approved_risk_fraction": 0.0,
            "approved_position_size_usd": 0.0,
            "leverage": 1.0,
            "max_holding_bars": 0,
            "execution_action": "DO_NOTHING",
            "next_position_state": "candidate",
            "review_note": "rule evaluation rejected or produced no approved candidates",
        }

    if research_output and research_output.get("selected_intent") in {"NO_TRADE", "WAIT_FOR_CONFIRMATION"}:
        return {
            "symbol": snapshot["symbol"],
            "cycleId": snapshot["cycleId"],
            "strategy_family": None,
            "approved": False,
            "final_intent": research_output["selected_intent"],
            "approved_risk_fraction": 0.0,
            "approved_position_size_usd": 0.0,
            "leverage": 1.0,
            "max_holding_bars": 0,
            "execution_action": "DO_NOTHING",
            "next_position_state": "candidate",
            "review_note": "research requested no trade or wait for confirmation",
        }

    candidate = rule_evaluation["approved_candidates"][0]
    if research_output and research_output.get("selected_trigger_sources"):
        selected_source = set(research_output["selected_trigger_sources"])
        matching = [c for c in rule_evaluation["approved_candidates"] if c.get("trigger_source") in selected_source]
        if matching:
            candidate = matching[0]

    portfolio_state = _load_portfolio_state()
    account_equity = _safe_float(portfolio_state.get("total_equity"), 0.0)
    if account_equity <= 0:
        account_equity = 1000.0

    approved_risk_fraction = GLOBAL_CONFIG["approved_risk_fraction"]
    is_grid_candidate = candidate.get("decision_intent") == "GRID_NEUTRAL"
    if is_grid_candidate:
        approved_risk_fraction = min(approved_risk_fraction, 0.01)
        raw_size = account_equity * GLOBAL_CONFIG["grid_position_size_fraction"]
        approved_position_size_usd = min(raw_size, account_equity * GLOBAL_CONFIG["grid_max_position_size_fraction"])
        leverage = min(GLOBAL_CONFIG["grid_leverage_default"], GLOBAL_CONFIG["grid_leverage_max"])
        max_holding_bars = max(1, int((_safe_float(candidate.get("reference_values", {}).get("max_lifetime_hours"), GLOBAL_CONFIG["grid_max_lifetime_hours"])) / 4))
    else:
        raw_size = account_equity * GLOBAL_CONFIG["default_position_size_fraction"]
        approved_position_size_usd = min(raw_size, account_equity * GLOBAL_CONFIG["max_position_size_fraction"])
        approved_position_size_usd = _cap_position_size_by_max_loss(
            account_equity=account_equity,
            entry_price=_safe_float(candidate.get("proposed_entry_price")),
            stop_loss=_safe_float(candidate.get("proposed_sl_price")),
            requested_size_usd=approved_position_size_usd,
        )
        leverage = 3.0
        max_holding_bars = 3 if snapshot["decision_ready_features"].get("macro_mode") == "EVENT_DRIVEN" else 6
    review_note = (
        f"approved from {candidate['trigger_source']} with deterministic risk defaults; "
        f"max loss capped at {round(approved_risk_fraction * 100, 1)}% of equity"
    )
    candidate_structure = rule_evaluation.get("candidate_structure", {}) or {}
    if is_grid_candidate:
        grid_count = max(int(candidate.get("reference_values", {}).get("grid_count") or 1), 1)
        per_grid_notional = approved_position_size_usd / grid_count
        candidate.setdefault("reference_values", {})
        candidate["reference_values"]["per_grid_notional_usd"] = round(per_grid_notional, 2)
        if per_grid_notional < GLOBAL_CONFIG["grid_min_per_grid_notional_usd"]:
            return {
                "symbol": snapshot["symbol"],
                "cycleId": snapshot["cycleId"],
                "strategy_family": STRATEGY_FAMILY_GRID,
                "approved": False,
                "final_intent": "NO_TRADE",
                "approved_risk_fraction": 0.0,
                "approved_position_size_usd": 0.0,
                "leverage": 1.0,
                "max_holding_bars": 0,
                "execution_action": "DO_NOTHING",
                "next_position_state": "candidate",
                "review_note": "grid per-cell notional too small after fees/slippage sizing constraints",
            }

    if research_output:
        if research_output.get("thesis_strength") == "LOW":
            approved_position_size_usd *= 0.5
            leverage = 1.0 if not is_grid_candidate else min(leverage, 2.0)
            max_holding_bars = min(max_holding_bars, 2)
            review_note = "research flagged low thesis strength; reduced size and leverage"
        elif research_output.get("thesis_strength") == "MEDIUM":
            approved_position_size_usd *= 0.75
            leverage = 2.0 if not is_grid_candidate else min(leverage, 2.5)
            max_holding_bars = min(max_holding_bars, 4)
            review_note = "research flagged medium thesis strength; reduced size and duration"

        if research_output.get("holding_horizon") == "SHORT":
            max_holding_bars = min(max_holding_bars, 3)

    resonance_bonus = _safe_float(candidate.get("resonance_bonus"), 0.0)
    if candidate_structure.get("overall_state") == "same_direction_resonance" and resonance_bonus > 0:
        approved_position_size_usd = min(
            approved_position_size_usd * (1.0 + resonance_bonus),
            account_equity * GLOBAL_CONFIG["max_position_size_fraction"],
        )
        review_note = (
            f"{review_note}; same-direction resonance increased size by {round(resonance_bonus * 100, 1)}%"
        )

    if not is_grid_candidate:
        approved_position_size_usd = _cap_position_size_by_max_loss(
            account_equity=account_equity,
            entry_price=_safe_float(candidate.get("proposed_entry_price")),
            stop_loss=_safe_float(candidate.get("proposed_sl_price")),
            requested_size_usd=approved_position_size_usd,
        )
    leverage = min(GLOBAL_CONFIG["global_leverage_max"], max(GLOBAL_CONFIG["global_leverage_min"], leverage))

    if candidate["decision_intent"] == "GRID_NEUTRAL":
        execution_action = "START_GRID_BOT"
        review_note = (
            f"approved grid bot from {candidate['trigger_source']}; "
            f"range={candidate.get('reference_values', {}).get('range_lower_bound')}~{candidate.get('reference_values', {}).get('range_upper_bound')}, "
            f"grid_count={candidate.get('reference_values', {}).get('grid_count')}, "
            f"review_after_hours={candidate.get('reference_values', {}).get('review_after_hours')}, "
            f"max_lifetime_hours={candidate.get('reference_values', {}).get('max_lifetime_hours')}"
        )
    else:
        execution_action = "OPEN_LONG" if candidate["decision_intent"] == "LONG" else "OPEN_SHORT"

    return {
        "symbol": snapshot["symbol"],
        "cycleId": snapshot["cycleId"],
        "strategy_family": _strategy_family_for_intent(candidate["decision_intent"]),
        "approved": True,
        "final_intent": candidate["decision_intent"],
        "approved_risk_fraction": approved_risk_fraction,
        "approved_position_size_usd": round(approved_position_size_usd, 2),
        "leverage": leverage,
        "max_holding_bars": max_holding_bars,
        "execution_action": execution_action,
        "next_position_state": "approved",
        "review_note": review_note,
        "approved_candidate": candidate,
        "candidate_structure": candidate_structure,
    }


def _build_execution_request(snapshot: Dict[str, Any], risk_review: Dict[str, Any]) -> Dict[str, Any]:
    if not risk_review.get("approved"):
        return {
            "symbol": snapshot["symbol"],
            "cycleId": snapshot["cycleId"],
            "strategy_family": risk_review.get("strategy_family"),
            "execution_action": "DO_NOTHING",
            "order_status": "NOT_REQUESTED",
            "requested_size_usd": 0.0,
            "requested_leverage": 1.0,
            "avg_fill_price": None,
            "filled_size": 0.0,
            "exchange_order_id": None,
            "executed_at": None,
            "sync_status": "NOT_REQUESTED",
            "failure_reason": None,
            "history": [
                _execution_event("EXECUTION_NOT_REQUESTED", {
                    "review_note": risk_review.get("review_note"),
                })
            ],
        }

    candidate = risk_review["approved_candidate"]
    return {
        "symbol": snapshot["symbol"],
        "cycleId": snapshot["cycleId"],
        "strategy_family": risk_review.get("strategy_family"),
        "execution_action": risk_review["execution_action"],
        "order_status": "PENDING_SUBMIT",
        "requested_size_usd": risk_review["approved_position_size_usd"],
        "requested_leverage": risk_review["leverage"],
        "entry_type": candidate["entry_type"],
        "proposed_entry_price": candidate["proposed_entry_price"],
        "proposed_sl_price": candidate["proposed_sl_price"],
        "proposed_tp_price": candidate["proposed_tp_price"],
        "requested_protection": {
            "stop_loss": candidate["proposed_sl_price"],
            "take_profit": candidate["proposed_tp_price"],
        },
        "grid_config": candidate.get("reference_values") if candidate.get("entry_type") == "GRID_BOT" else None,
        "avg_fill_price": None,
        "filled_size": 0.0,
        "exchange_order_id": None,
        "exchange_algo_id": None,
        "executed_at": None,
        "sync_status": "PENDING_SUBMIT",
        "failure_reason": None,
        "protection_status": "PENDING_ATTACH",
        "history": [
            _execution_event("EXECUTION_REQUEST_CREATED", {
                "execution_action": risk_review["execution_action"],
                "requested_size_usd": risk_review["approved_position_size_usd"],
                "requested_leverage": risk_review["leverage"],
                "requested_protection": {
                    "stop_loss": candidate["proposed_sl_price"],
                    "take_profit": candidate["proposed_tp_price"],
                },
            })
        ],
    }


def _make_trade_record(snapshot: Dict[str, Any], candidate_batch: Dict[str, Any], rule_evaluation: Dict[str, Any], research_output: Optional[Dict[str, Any]], risk_review: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
    now_iso = _iso_now()
    now_local = _iso_now_local()
    return {
        "decisionId": snapshot["decision_id"],
        "cycleId": snapshot["cycleId"],
        "symbol": snapshot["symbol"],
        "timeframe": snapshot["timeframe"],
        "snapshot_timestamp": snapshot["snapshot_timestamp"],
        "snapshot_time": snapshot.get("snapshot_time"),
        "snapshot_time_local": snapshot.get("snapshot_time_local"),
        "local_timezone": LOCAL_TZ_NAME,
        "positionState": risk_review.get("next_position_state", "candidate"),
        "snapshot": snapshot,
        "candidate": candidate_batch,
        "ruleEvaluation": rule_evaluation,
        "researchOutput": research_output,
        "riskReview": risk_review,
        "execution": execution,
        "evaluation": None,
        "created_at": now_iso,
        "created_at_local": now_local,
        "updated_at": now_iso,
        "updated_at_local": now_local,
    }


def _append_trade_record(record: Dict[str, Any]) -> None:
    collection = db.get_data("trade_decision_records", [])
    if not isinstance(collection, list):
        collection = []
    decision_id = str(record.get("decisionId") or "")
    collection.insert(0, record)
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in collection:
        item_decision_id = str(item.get("decisionId") or "")
        if not item_decision_id or item_decision_id in seen:
            continue
        seen.add(item_decision_id)
        deduped.append(item)
    collection = deduped
    collection = collection[:500]
    db.save_data("trade_decision_records", collection)
    db.save_data("latest_trade_decision_record", record)


def _save_cycle_bundle(cycle_id: str, bundle: Dict[str, Any]) -> None:
    cycles = db.get_data("decision_cycles_v2", [])
    if not isinstance(cycles, list):
        cycles = []
    cycles.insert(0, bundle)
    deduped_cycles: List[Dict[str, Any]] = []
    seen = set()
    for item in cycles:
        item_cycle_id = str(item.get("cycleId") or "")
        if not item_cycle_id or item_cycle_id in seen:
            continue
        seen.add(item_cycle_id)
        deduped_cycles.append(item)
    cycles = deduped_cycles
    cycles = cycles[:50]
    db.save_data("decision_cycles_v2", cycles)
    db.save_data("latest_decision_cycle_v2", bundle)


def _execute_if_enabled(executor: OKXExecutor, execution: Dict[str, Any], risk_review: Dict[str, Any]) -> Dict[str, Any]:
    history = execution.setdefault("history", [])
    execution_flag = os.getenv("ENABLE_V2_EXECUTION")
    trading_mode = os.getenv("TRADING_MODE", "SHADOW").upper()
    if execution_flag is None:
        enabled = trading_mode in {"DEMO", "REAL"}
    else:
        enabled = execution_flag.lower() in {"1", "true", "yes"}
    if not enabled or execution["execution_action"] == "DO_NOTHING":
        execution["order_status"] = "SKIPPED"
        execution["sync_status"] = "SKIPPED"
        execution["protection_status"] = "SKIPPED"
        execution["failure_reason"] = "v2_execution_disabled" if not enabled else None
        history.append(_execution_event("EXECUTION_SKIPPED", {
            "reason": execution["failure_reason"] or "do_nothing",
            "execution_action": execution.get("execution_action"),
        }))
        execution["history"] = history[-50:]
        return execution

    candidate = risk_review.get("approved_candidate", {})
    if execution["execution_action"] == "START_GRID_BOT":
        grid_order_id = None
        if hasattr(executor, "execute_grid_bot"):
            grid_order_id = executor.execute_grid_bot(
                symbol=execution["symbol"].replace("-USDT", ""),
                amount_usd=execution["requested_size_usd"],
                leverage=execution["requested_leverage"],
                grid_config=execution.get("grid_config") or {},
            )
        elif getattr(executor, "shadow_mode", False):
            grid_order_id = f"shadow_grid_{int(_now_utc().timestamp() * 1000)}"

        if grid_order_id:
            execution["exchange_algo_id"] = str(grid_order_id)
            execution["order_status"] = "SUBMITTED"
            execution["sync_status"] = "SUBMITTED"
            execution["protection_status"] = "PENDING_SYNC"
            execution["executed_at"] = _iso_now()
            history.append(_execution_event("GRID_BOT_SUBMITTED", {
                "exchange_algo_id": str(grid_order_id),
                "execution_action": execution.get("execution_action"),
                "grid_config": execution.get("grid_config"),
            }))
        else:
            execution["order_status"] = "FAILED"
            execution["sync_status"] = "FAILED"
            execution["protection_status"] = "FAILED"
            execution["failure_reason"] = "grid_executor_not_supported"
            history.append(_execution_event("GRID_BOT_SUBMIT_FAILED", {
                "execution_action": execution.get("execution_action"),
                "failure_reason": execution["failure_reason"],
            }))
        execution["history"] = history[-50:]
        return execution

    symbol = execution["symbol"].replace("-USDT", "")
    action_map = {
        "OPEN_LONG": "open_long",
        "OPEN_SHORT": "open_short",
        "CLOSE_POSITION": "close_position",
    }
    raw_action = action_map.get(execution["execution_action"], execution["execution_action"].lower())
    order_id = executor.execute_trade(
        symbol=symbol,
        action=raw_action,
        amount_usd=execution["requested_size_usd"],
        leverage=execution["requested_leverage"],
        stop_loss=execution.get("proposed_sl_price"),
        take_profit=execution.get("proposed_tp_price"),
        pos_side="long" if risk_review.get("final_intent") == "LONG" else "short",
        invalidation_rule={
            "basis": candidate.get("invalidation_basis"),
            "conditions": candidate.get("invalidation_conditions"),
        },
    )
    if order_id:
        execution["exchange_order_id"] = str(order_id)
        execution["order_status"] = "SUBMITTED"
        execution["sync_status"] = "SUBMITTED"
        execution["protection_status"] = "PENDING_SYNC"
        execution["executed_at"] = _iso_now()
        history.append(_execution_event("EXECUTION_SUBMITTED", {
            "exchange_order_id": str(order_id),
            "execution_action": execution.get("execution_action"),
        }))
    else:
        execution["order_status"] = "FAILED"
        execution["sync_status"] = "FAILED"
        execution["protection_status"] = "FAILED"
        execution["failure_reason"] = "executor_returned_empty_order_id"
        history.append(_execution_event("EXECUTION_SUBMIT_FAILED", {
            "execution_action": execution.get("execution_action"),
            "failure_reason": execution["failure_reason"],
        }))
    execution["history"] = history[-50:]
    return execution


def run_deterministic_cycle(executor: Optional[OKXExecutor] = None) -> Dict[str, Any]:
    executor = executor or OKXExecutor()
    whale_analysis = _load_whale_analysis()
    qlib_payload = _load_qlib_payload()
    portfolio_state = _load_portfolio_state()
    cycle_id = _aligned_cycle_id()
    qlib_map = _qlib_coin_map(qlib_payload)
    chart_context_map = _load_chart_feature_context_map()

    snapshots: List[Dict[str, Any]] = []
    candidate_batches: List[Dict[str, Any]] = []
    rule_evaluations: List[Dict[str, Any]] = []
    research_outputs: List[Optional[Dict[str, Any]]] = []
    risk_reviews: List[Dict[str, Any]] = []
    executions: List[Dict[str, Any]] = []
    records: List[Dict[str, Any]] = []

    for symbol in TRACKED_SYMBOLS:
        snapshot = _build_decision_snapshot(
            symbol,
            whale_analysis,
            qlib_map.get(symbol, {}),
            portfolio_state,
            cycle_id,
            chart_context=chart_context_map.get(symbol, {}),
        )
        candidate_batch = _build_candidate_proposals(snapshot)
        rule_evaluation = _evaluate_rules(snapshot, candidate_batch)
        research_output = build_research_output(snapshot, candidate_batch, rule_evaluation)
        risk_review = _build_risk_review_with_research(snapshot, rule_evaluation, research_output)
        execution = _build_execution_request(snapshot, risk_review)
        execution = _execute_if_enabled(executor, execution, risk_review)
        record = _make_trade_record(snapshot, candidate_batch, rule_evaluation, research_output, risk_review, execution)

        snapshots.append(snapshot)
        candidate_batches.append(candidate_batch)
        rule_evaluations.append(rule_evaluation)
        research_outputs.append(research_output)
        risk_reviews.append(risk_review)
        executions.append(execution)
        records.append(record)
        _append_trade_record(record)

    review_summary = run_post_trade_review()

    bundle = {
        "cycleId": cycle_id,
        "generated_at": _iso_now(),
        "generated_at_local": _iso_now_local(),
        "cycle_local_time": _aligned_cycle_local(),
        "local_timezone": LOCAL_TZ_NAME,
        "timeframe": GLOBAL_CONFIG["timeframe"],
        "snapshots": snapshots,
        "candidate_batches": candidate_batches,
        "rule_evaluations": rule_evaluations,
        "research_outputs": research_outputs,
        "risk_reviews": risk_reviews,
        "executions": executions,
        "record_count": len(records),
        "post_trade_review": review_summary,
    }
    _save_cycle_bundle(cycle_id, bundle)
    return bundle


if __name__ == "__main__":
    result = run_deterministic_cycle()
    print(json.dumps({
        "cycleId": result["cycleId"],
        "record_count": result["record_count"],
        "approved": [r["symbol"] for r in result["risk_reviews"] if r.get("approved")],
    }, indent=2, ensure_ascii=False))
