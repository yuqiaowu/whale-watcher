import math
from typing import Any, Dict, Iterable, List, Optional

import requests


OKX_PUBLIC_BASE_URL = "https://www.okx.com"
VWAP_BAR = "5m"
VWAP_SOURCE = "HLC3"
VWAP_BAND_METHOD = "volume_weighted_standard_deviation"
VWAP_MULTIPLIERS = (1, 2, 3)
VWAP_WINDOWS = (4, 16)
FIVE_MIN_BARS_PER_HOUR = 12


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        parsed = float(value)
        if math.isnan(parsed):
            return default
        return parsed
    except Exception:
        return default


def _round_optional(value: Optional[float], digits: int = 8) -> Optional[float]:
    if value is None:
        return None
    return round(value, digits)


def _pct_distance(price: float, reference: Optional[float]) -> Optional[float]:
    if reference in (None, 0):
        return None
    return round((price - reference) / reference * 100.0, 4)


def _zone(price: float, vwap: float, bands: Dict[str, Optional[float]]) -> str:
    upper_1 = bands.get("upper_1")
    upper_2 = bands.get("upper_2")
    upper_3 = bands.get("upper_3")
    lower_1 = bands.get("lower_1")
    lower_2 = bands.get("lower_2")
    lower_3 = bands.get("lower_3")

    if upper_3 is not None and price >= upper_3:
        return "ABOVE_UPPER_3"
    if upper_2 is not None and price >= upper_2:
        return "ABOVE_UPPER_2_BELOW_UPPER_3"
    if upper_1 is not None and price >= upper_1:
        return "ABOVE_UPPER_1_BELOW_UPPER_2"
    if price >= vwap:
        return "ABOVE_VWAP_BELOW_UPPER_1"
    if lower_1 is not None and price >= lower_1:
        return "BELOW_VWAP_ABOVE_LOWER_1"
    if lower_2 is not None and price >= lower_2:
        return "BELOW_LOWER_1_ABOVE_LOWER_2"
    if lower_3 is not None and price >= lower_3:
        return "BELOW_LOWER_2_ABOVE_LOWER_3"
    return "BELOW_LOWER_3"


def _parse_okx_candles(candles: Iterable[List[Any]]) -> List[Dict[str, float]]:
    parsed: List[Dict[str, float]] = []
    for row in candles or []:
        if not isinstance(row, list) or len(row) < 7:
            continue
        high = _safe_float(row[2])
        low = _safe_float(row[3])
        close = _safe_float(row[4])
        quote_volume = _safe_float(row[7] if len(row) > 7 else None, _safe_float(row[6]))
        if high <= 0 or low <= 0 or close <= 0 or quote_volume <= 0:
            continue
        parsed.append(
            {
                "ts": _safe_float(row[0]),
                "high": high,
                "low": low,
                "close": close,
                "source_price": (high + low + close) / 3.0,
                "quote_volume": quote_volume,
            }
        )
    parsed.sort(key=lambda item: item["ts"])
    return parsed


def compute_vwap_features_from_candles(candles: Iterable[List[Any]], windows: Iterable[int] = VWAP_WINDOWS) -> Dict[str, Any]:
    bars = _parse_okx_candles(candles)
    if not bars:
        return {
            "vwap_available": False,
            "vwap_missing_reason": "no_valid_5m_candles",
            "vwap_bar": VWAP_BAR,
            "vwap_source": VWAP_SOURCE,
            "vwap_band_method": VWAP_BAND_METHOD,
            "vwap_band_multipliers": list(VWAP_MULTIPLIERS),
        }

    latest_price = bars[-1]["close"]
    result: Dict[str, Any] = {
        "vwap_available": True,
        "vwap_bar": VWAP_BAR,
        "vwap_source": VWAP_SOURCE,
        "vwap_band_method": VWAP_BAND_METHOD,
        "vwap_band_multipliers": list(VWAP_MULTIPLIERS),
        "vwap_latest_price": round(latest_price, 8),
    }

    available_any = False
    for hours in windows:
        required = int(hours) * FIVE_MIN_BARS_PER_HOUR
        suffix = f"{int(hours)}h"
        window_bars = bars[-required:] if len(bars) >= required else []
        result[f"vwap_{suffix}_bar_count"] = len(window_bars)
        result[f"vwap_{suffix}_lookback_hours"] = int(hours)
        if len(window_bars) < required:
            result[f"vwap_{suffix}_available"] = False
            result[f"vwap_{suffix}_missing_reason"] = f"need_{required}_5m_bars"
            continue

        volume_sum = sum(item["quote_volume"] for item in window_bars)
        if volume_sum <= 0:
            result[f"vwap_{suffix}_available"] = False
            result[f"vwap_{suffix}_missing_reason"] = "zero_quote_volume"
            continue

        vwap = sum(item["source_price"] * item["quote_volume"] for item in window_bars) / volume_sum
        variance = sum(item["quote_volume"] * ((item["source_price"] - vwap) ** 2) for item in window_bars) / volume_sum
        std = math.sqrt(max(variance, 0.0))
        zscore = (latest_price - vwap) / std if std > 0 else 0.0
        bands = {
            "upper_1": vwap + std,
            "lower_1": vwap - std,
            "upper_2": vwap + 2 * std,
            "lower_2": vwap - 2 * std,
            "upper_3": vwap + 3 * std,
            "lower_3": vwap - 3 * std,
        }

        result.update(
            {
                f"vwap_{suffix}_available": True,
                f"vwap_{suffix}": round(vwap, 8),
                f"vwap_std_{suffix}": round(std, 8),
                f"vwap_volume_sum_{suffix}": round(volume_sum, 4),
                f"price_vs_vwap_{suffix}_pct": _pct_distance(latest_price, vwap),
                f"price_vwap_zscore_{suffix}": round(zscore, 4),
                f"vwap_{suffix}_zone": _zone(latest_price, vwap, bands),
            }
        )
        for multiplier in VWAP_MULTIPLIERS:
            upper = bands[f"upper_{multiplier}"]
            lower = bands[f"lower_{multiplier}"]
            result[f"vwap_upper_{multiplier}_{suffix}"] = _round_optional(upper)
            result[f"vwap_lower_{multiplier}_{suffix}"] = _round_optional(lower)
            result[f"price_vs_vwap_upper_{multiplier}_{suffix}_pct"] = _pct_distance(latest_price, upper)
            result[f"price_vs_vwap_lower_{multiplier}_{suffix}_pct"] = _pct_distance(latest_price, lower)
        available_any = True

    if not available_any:
        result["vwap_available"] = False
        result["vwap_missing_reason"] = "insufficient_5m_candles"
    return result


def fetch_okx_5m_candles(inst_id: str, limit: int = 240) -> List[List[Any]]:
    response = requests.get(
        f"{OKX_PUBLIC_BASE_URL}/api/v5/market/candles",
        params={"instId": inst_id, "bar": VWAP_BAR, "limit": str(limit)},
        timeout=(5, 15),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX candles error {payload.get('code')}: {payload.get('msg')}")
    data = payload.get("data") or []
    return data if isinstance(data, list) else []


def load_vwap_feature_context(symbols: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for symbol in symbols:
        normalized = str(symbol).upper().replace("-USDT", "").replace("-SWAP", "")
        inst_id = f"{normalized}-USDT-SWAP"
        try:
            candles = fetch_okx_5m_candles(inst_id)
            result[normalized] = compute_vwap_features_from_candles(candles)
        except Exception as exc:
            result[normalized] = {
                "vwap_available": False,
                "vwap_missing_reason": f"fetch_error:{type(exc).__name__}",
                "vwap_bar": VWAP_BAR,
                "vwap_source": VWAP_SOURCE,
                "vwap_band_method": VWAP_BAND_METHOD,
                "vwap_band_multipliers": list(VWAP_MULTIPLIERS),
            }
    return result
