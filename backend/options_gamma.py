import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests


DERIBIT_BASE_URL = os.getenv("DERIBIT_BASE_URL", "https://www.deribit.com")
SUPPORTED_DERIBIT_CURRENCIES = {"BTC", "ETH"}
DEFAULT_LOOKAHEAD_DAYS = 14
DEFAULT_MAX_INSTRUMENTS = 180
DEFAULT_WALL_NEAR_PCT = 1.0
_CACHE_TTL_SECONDS = 900
_CACHE: Dict[str, Dict[str, Any]] = {}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        parsed = float(value)
        if math.isnan(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_json(path: str, params: Dict[str, Any], timeout: float = 8.0) -> Dict[str, Any]:
    response = requests.get(f"{DERIBIT_BASE_URL}{path}", params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"Deribit error: {payload['error']}")
    result = payload.get("result")
    return result if isinstance(result, dict) else {"items": result}


def _fetch_instruments(currency: str) -> List[Dict[str, Any]]:
    result = _get_json(
        "/api/v2/public/get_instruments",
        {"currency": currency, "kind": "option", "expired": "false"},
    )
    items = result.get("items")
    return items if isinstance(items, list) else []


def _fetch_index_price(currency: str) -> Optional[float]:
    index_name = f"{currency.lower()}_usd"
    result = _get_json("/api/v2/public/get_index_price", {"index_name": index_name})
    return _safe_float(result.get("index_price"))


def _fetch_ticker(instrument_name: str) -> Dict[str, Any]:
    return _get_json("/api/v2/public/ticker", {"instrument_name": instrument_name}, timeout=6.0)


def _fetch_book_summary(currency: str) -> List[Dict[str, Any]]:
    result = _get_json(
        "/api/v2/public/get_book_summary_by_currency",
        {"currency": currency, "kind": "option"},
        timeout=12.0,
    )
    items = result.get("items")
    return items if isinstance(items, list) else []


def _parse_deribit_option_name(instrument_name: str) -> Optional[Dict[str, Any]]:
    match = re.match(r"^[A-Z]+-(\d{1,2}[A-Z]{3}\d{2})-(\d+(?:\.\d+)?)-([CP])$", str(instrument_name or ""))
    if not match:
        return None
    expiry_raw, strike_raw, cp = match.groups()
    try:
        expiry = datetime.strptime(expiry_raw, "%d%b%y").replace(tzinfo=timezone.utc)
        return {
            "expiry": expiry,
            "strike": float(strike_raw),
            "option_type": "call" if cp == "C" else "put",
        }
    except ValueError:
        return None


def _standard_normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _black_scholes_gamma(spot: float, strike: float, iv_percent: float, expiry: datetime) -> Optional[float]:
    if spot <= 0 or strike <= 0 or iv_percent <= 0:
        return None
    seconds_to_expiry = max((expiry - _utc_now()).total_seconds(), 0.0)
    years_to_expiry = seconds_to_expiry / (365.0 * 24.0 * 60.0 * 60.0)
    if years_to_expiry <= 0:
        return None
    sigma = iv_percent / 100.0
    sigma_sqrt_t = sigma * math.sqrt(years_to_expiry)
    if sigma_sqrt_t <= 0:
        return None
    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * years_to_expiry) / sigma_sqrt_t
    return _standard_normal_pdf(d1) / (spot * sigma_sqrt_t)


def _summary_strike_distance(summary: Dict[str, Any], index_price: float) -> float:
    parsed = _parse_deribit_option_name(str(summary.get("instrument_name") or ""))
    strike = _safe_float((parsed or {}).get("strike"))
    return abs((strike or index_price) - index_price)


def _gamma_sign_semantic(total_gex_usd_per_1pct: Optional[float]) -> str:
    if total_gex_usd_per_1pct is None:
        return "UNAVAILABLE"
    if total_gex_usd_per_1pct > 0:
        return (
            "POSITIVE_GAMMA: dealer hedging is more likely to dampen price moves and pin price near high open-interest "
            "strikes; breakouts usually need stronger spot/perp pressure."
        )
    if total_gex_usd_per_1pct < 0:
        return (
            "NEGATIVE_GAMMA: dealer hedging is more likely to chase price moves, increasing volatility and making "
            "support/resistance breaks more reflexive."
        )
    return "NEUTRAL_GAMMA: option gamma pressure is close to balanced."


def _empty_context(symbol: str, reason: str) -> Dict[str, Any]:
    return {
        "available": False,
        "source": "deribit_public_options",
        "symbol": symbol,
        "coverage": "BTC/ETH Deribit options only",
        "lookahead_days": DEFAULT_LOOKAHEAD_DAYS,
        "put_wall": None,
        "call_wall": None,
        "iv": {
            "atm_mark_iv": None,
            "oi_weighted_mark_iv": None,
            "put_wall_mark_iv": None,
            "call_wall_mark_iv": None,
            "unit": "annualized_percent",
        },
        "wall_distance": {
            "near_threshold_pct": DEFAULT_WALL_NEAR_PCT,
            "put_wall_downside_pct": None,
            "call_wall_upside_pct": None,
            "put_wall_abs_distance_pct": None,
            "call_wall_abs_distance_pct": None,
            "near_put_wall": False,
            "near_call_wall": False,
            "semantic": "UNAVAILABLE",
        },
        "total_gex_usd_per_1pct": None,
        "gamma_sign": "UNAVAILABLE",
        "gamma_semantic": "UNAVAILABLE",
        "missing_reason": reason,
        "calculation_note": (
            "Public OI and greeks proxy. Real dealer positioning is not directly observable, so use this as context, "
            "not a hard trading rule."
        ),
    }


def _select_wall(rows: Iterable[Dict[str, Any]], option_type: str) -> Optional[Dict[str, Any]]:
    filtered = [row for row in rows if row.get("option_type") == option_type and _safe_float(row.get("open_interest"))]
    if not filtered:
        return None
    best = max(filtered, key=lambda row: _safe_float(row.get("open_interest")) or 0.0)
    return {
        "strike": _safe_float(best.get("strike")),
        "expiry": best.get("expiry"),
        "open_interest": _safe_float(best.get("open_interest")),
        "gex_usd_per_1pct": _safe_float(best.get("gex_usd_per_1pct")),
        "mark_iv": _safe_float(best.get("mark_iv")),
    }


def _weighted_average(rows: Iterable[Dict[str, Any]], value_key: str, weight_key: str) -> Optional[float]:
    total_weight = 0.0
    total_value = 0.0
    for row in rows:
        value = _safe_float(row.get(value_key))
        weight = _safe_float(row.get(weight_key))
        if value is None or weight is None or weight <= 0:
            continue
        total_value += value * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return round(total_value / total_weight, 4)


def _nearest_atm_iv(rows: List[Dict[str, Any]], index_price: float) -> Optional[float]:
    candidates = [row for row in rows if _safe_float(row.get("mark_iv")) is not None]
    if not candidates:
        return None
    nearest = sorted(candidates, key=lambda row: abs((_safe_float(row.get("strike")) or index_price) - index_price))[:4]
    return _weighted_average(nearest, "mark_iv", "open_interest")


def _wall_distance_context(
    index_price: float,
    put_wall: Optional[Dict[str, Any]],
    call_wall: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    threshold = _safe_float(os.getenv("OPTIONS_WALL_NEAR_PCT")) or DEFAULT_WALL_NEAR_PCT
    put_strike = _safe_float((put_wall or {}).get("strike"))
    call_strike = _safe_float((call_wall or {}).get("strike"))
    put_downside = round((index_price - put_strike) / index_price * 100, 4) if put_strike else None
    call_upside = round((call_strike - index_price) / index_price * 100, 4) if call_strike else None
    put_abs = abs(put_downside) if put_downside is not None else None
    call_abs = abs(call_upside) if call_upside is not None else None
    near_put = bool(put_abs is not None and put_abs <= threshold)
    near_call = bool(call_abs is not None and call_abs <= threshold)
    if near_put and near_call:
        semantic = "PRICE_BETWEEN_CLOSE_WALLS: price is very close to both major option walls; pinning or sharp break risk is elevated."
    elif near_put:
        semantic = "NEAR_PUT_WALL: price is very close to the put wall; it may act as a magnet/support area, but breaks can accelerate."
    elif near_call:
        semantic = "NEAR_CALL_WALL: price is very close to the call wall; it may act as a magnet/resistance area, but breaks can accelerate."
    else:
        semantic = "NOT_NEAR_MAJOR_WALL: price is not within the near-wall threshold."
    return {
        "near_threshold_pct": threshold,
        "put_wall_downside_pct": put_downside,
        "call_wall_upside_pct": call_upside,
        "put_wall_abs_distance_pct": round(put_abs, 4) if put_abs is not None else None,
        "call_wall_abs_distance_pct": round(call_abs, 4) if call_abs is not None else None,
        "near_put_wall": near_put,
        "near_call_wall": near_call,
        "semantic": semantic,
    }


def build_options_gamma_context(symbol: str, lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS) -> Dict[str, Any]:
    currency = str(symbol or "").split("-")[0].upper()
    if currency not in SUPPORTED_DERIBIT_CURRENCIES:
        return _empty_context(currency, "unsupported_symbol_options_context_only_available_for_BTC_ETH")

    cache_key = f"{currency}:{lookahead_days}"
    cached = _CACHE.get(cache_key)
    now_ts = time.time()
    if cached and now_ts - float(cached.get("cached_at_ts", 0.0)) < _CACHE_TTL_SECONDS:
        return dict(cached["value"])

    if os.getenv("ENABLE_OPTIONS_GAMMA_CONTEXT", "1").lower() not in {"1", "true", "yes"}:
        return _empty_context(currency, "options_gamma_context_disabled")

    try:
        index_price = _fetch_index_price(currency)
        if not index_price or index_price <= 0:
            return _empty_context(currency, "missing_deribit_index_price")

        cutoff = _utc_now() + timedelta(days=max(1, int(lookahead_days)))
        rows: List[Dict[str, Any]] = []
        max_instruments = int(os.getenv("OPTIONS_GAMMA_MAX_INSTRUMENTS", "0") or "0")
        summaries = _fetch_book_summary(currency)
        if max_instruments > 0:
            summaries = sorted(
                summaries,
                key=lambda item: _summary_strike_distance(item, index_price),
            )[:max_instruments]

        for item in summaries:
            instrument_name = str(item.get("instrument_name") or "")
            if not instrument_name:
                continue
            parsed = _parse_deribit_option_name(instrument_name)
            if not parsed:
                continue
            expiry = parsed["expiry"]
            if expiry > cutoff:
                continue
            strike = _safe_float(parsed.get("strike"))
            option_type = str(parsed.get("option_type") or "").lower()
            mark_iv = _safe_float(item.get("mark_iv"))
            open_interest = _safe_float(item.get("open_interest"))
            underlying_price = _safe_float(item.get("underlying_price")) or index_price
            if open_interest is None or strike is None or mark_iv is None:
                continue
            gamma = _black_scholes_gamma(underlying_price, strike, mark_iv, expiry)
            if gamma is None:
                continue
            sign = 1.0 if option_type == "call" else -1.0 if option_type == "put" else 0.0
            gex_usd_per_1pct = sign * gamma * open_interest * underlying_price * underlying_price * 0.01
            rows.append(
                {
                    "instrument_name": instrument_name,
                    "option_type": option_type,
                    "strike": strike,
                    "expiry": expiry.date().isoformat(),
                    "open_interest": open_interest,
                    "gamma": gamma,
                    "mark_iv": mark_iv,
                    "gex_usd_per_1pct": round(gex_usd_per_1pct, 2),
                }
            )

        if not rows:
            return _empty_context(currency, "no_near_term_option_rows_with_gamma_and_oi")

        total_gex = round(sum(row["gex_usd_per_1pct"] for row in rows), 2)
        put_wall = _select_wall(rows, "put")
        call_wall = _select_wall(rows, "call")
        context = {
            "available": True,
            "source": "deribit_public_options",
            "symbol": currency,
            "coverage": "BTC/ETH Deribit options only",
            "lookahead_days": lookahead_days,
            "as_of": _utc_now().isoformat(timespec="seconds"),
            "underlying_index_price": round(index_price, 4),
            "instrument_count": len(rows),
            "put_wall": put_wall,
            "call_wall": call_wall,
            "iv": {
                "atm_mark_iv": _nearest_atm_iv(rows, index_price),
                "oi_weighted_mark_iv": _weighted_average(rows, "mark_iv", "open_interest"),
                "put_wall_mark_iv": _safe_float((put_wall or {}).get("mark_iv")),
                "call_wall_mark_iv": _safe_float((call_wall or {}).get("mark_iv")),
                "unit": "annualized_percent",
            },
            "wall_distance": _wall_distance_context(index_price, put_wall, call_wall),
            "total_gex_usd_per_1pct": total_gex,
            "gamma_sign": "POSITIVE" if total_gex > 0 else "NEGATIVE" if total_gex < 0 else "NEUTRAL",
            "gamma_semantic": _gamma_sign_semantic(total_gex),
            "missing_reason": None,
            "calculation_note": (
                "GEX is an approximate public-open-interest proxy in USD per 1% underlying move. Real dealer "
                "positioning is not directly observable, so use as context, not a hard trading rule."
            ),
        }
        _CACHE[cache_key] = {"cached_at_ts": now_ts, "value": dict(context)}
        return context
    except Exception as exc:
        return _empty_context(currency, f"deribit_options_gamma_fetch_failed:{type(exc).__name__}")


def load_options_gamma_context(symbols: Iterable[str], lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS) -> Dict[str, Dict[str, Any]]:
    return {str(symbol).upper(): build_options_gamma_context(str(symbol), lookahead_days) for symbol in symbols}
