import json
import math
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
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
        latest = frame.iloc[-1]
        atr = _safe_float(latest.get("atr_14"))
        support = _safe_float(latest.get("structure_support_12bar_volume_confirmed"))
        resistance = _safe_float(latest.get("structure_resistance_12bar_volume_confirmed"))
        result[str(instrument).upper()] = {
            "macd_line_4h": _safe_float(latest.get("macd")),
            "macd_signal_4h": _safe_float(latest.get("macd_signal")),
            "macd_hist_4h": _safe_float(latest.get("macd_hist")),
            "rsi_4h": _safe_float(latest.get("rsi_14")),
            "adx_14_4h": _safe_float(latest.get("adx_14")),
            "atr_14": atr,
            "rel_volume_60": _safe_float(latest.get("rel_volume_60")),
            "sma50_4h": _safe_float(latest.get("sma50_4h")),
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
    token_flow = _safe_float(stats24.get("token_net_flow"))
    stable_flow = _safe_float(stats24.get("stablecoin_net_flow"))
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
    decision_ready_features = {
        "regime_1d": regime_1d,
        "macro_mode": macro_snapshot["macro_mode"],
        "macro_horizon": macro_snapshot["macro_horizon"],
        "macro_permission": macro_snapshot["macro_permission"],
        "event_risk_active": bool(macro_snapshot["macro_event_window"]),
        "usd_strength_flag": "USD_STRENGTH" in (macro_snapshot.get("key_events") or []) or macro_snapshot.get("dxy_trend") == "UP",
        "yen_stress_flag": "YEN_STRESS" in (macro_snapshot.get("key_events") or []) or macro_snapshot.get("usdjpy_trend") == "DOWN",
        "flow_support_long": token_flow > 0 or stable_flow > 0,
        "flow_support_short": token_flow < 0 or stable_flow < 0,
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
    else:
        risk = sl - entry
        reward = entry - tp
    if risk <= 0:
        return 0.0
    return round(reward / risk, 2)


def _entry_type_for_blueprint(blueprint: str) -> str:
    if blueprint in {"Blueprint_A1", "Blueprint_A2"}:
        return "MARKET"
    return "MARKET"


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
    if proposal["decision_intent"] not in {"LONG", "SHORT"}:
        return False, "invalid_decision_intent"
    if proposal["entry_type"] not in {"MARKET", "LIMIT", "STOP"}:
        return False, "invalid_entry_type"
    return True, None


def _summarize_candidate_structure(proposals: List[Dict[str, Any]], approved_candidates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    approved_candidates = approved_candidates or []
    intent_groups: Dict[str, List[str]] = {"LONG": [], "SHORT": []}
    for proposal in proposals:
        intent = str(proposal.get("decision_intent") or "")
        source = str(proposal.get("trigger_source") or "")
        if intent in intent_groups and source:
            intent_groups[intent].append(source)

    approved_groups: Dict[str, List[str]] = {"LONG": [], "SHORT": []}
    for proposal in approved_candidates:
        intent = str(proposal.get("decision_intent") or "")
        source = str(proposal.get("trigger_source") or "")
        if intent in approved_groups and source:
            approved_groups[intent].append(source)

    has_long = bool(intent_groups["LONG"])
    has_short = bool(intent_groups["SHORT"])
    if has_long and has_short:
        overall_state = "directional_conflict"
    elif len(intent_groups["LONG"]) >= 2 or len(intent_groups["SHORT"]) >= 2:
        overall_state = "same_direction_resonance"
    elif has_long or has_short:
        overall_state = "single_signal"
    else:
        overall_state = "no_candidate"

    return {
        "overall_state": overall_state,
        "has_directional_conflict": has_long and has_short,
        "long_count": len(intent_groups["LONG"]),
        "short_count": len(intent_groups["SHORT"]),
        "resonance_groups": {
            "LONG": intent_groups["LONG"],
            "SHORT": intent_groups["SHORT"],
        },
        "approved_groups": {
            "LONG": approved_groups["LONG"],
            "SHORT": approved_groups["SHORT"],
        },
        "approved_resonance_strength": max(len(approved_groups["LONG"]), len(approved_groups["SHORT"])),
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

        leverage = min(GLOBAL_CONFIG["global_leverage_max"], max(GLOBAL_CONFIG["global_leverage_min"], 3.0))
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

    if research_output:
        if research_output.get("thesis_strength") == "LOW":
            approved_position_size_usd *= 0.5
            leverage = 1.0
            max_holding_bars = min(max_holding_bars, 2)
            review_note = "research flagged low thesis strength; reduced size and leverage"
        elif research_output.get("thesis_strength") == "MEDIUM":
            approved_position_size_usd *= 0.75
            leverage = 2.0
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

    approved_position_size_usd = _cap_position_size_by_max_loss(
        account_equity=account_equity,
        entry_price=_safe_float(candidate.get("proposed_entry_price")),
        stop_loss=_safe_float(candidate.get("proposed_sl_price")),
        requested_size_usd=approved_position_size_usd,
    )
    leverage = min(GLOBAL_CONFIG["global_leverage_max"], max(GLOBAL_CONFIG["global_leverage_min"], leverage))

    execution_action = "OPEN_LONG" if candidate["decision_intent"] == "LONG" else "OPEN_SHORT"

    return {
        "symbol": snapshot["symbol"],
        "cycleId": snapshot["cycleId"],
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
        "avg_fill_price": None,
        "filled_size": 0.0,
        "exchange_order_id": None,
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
    enabled = os.getenv("ENABLE_V2_EXECUTION", "0").lower() in {"1", "true", "yes"}
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
