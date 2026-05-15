import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests

from db_client import db


GAMMA_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
MARKET_SNAPSHOT_COLLECTION = "polymarket_market_snapshots"
SIGNAL_SNAPSHOT_COLLECTION = "polymarket_signal_snapshots"
WATCHLIST_COLLECTION = "polymarket_watchlist"

SEARCH_QUERIES = ("bitcoin", "ethereum", "solana", "crypto")
DELTA_WINDOWS_HOURS = (4, 24, 168, 720)
MAX_HISTORY_DAYS = 45
MAX_HISTORY_ROWS = 5000
DEFAULT_STABLE_MIN_OBSERVATIONS = 2
DEFAULT_STABLE_MIN_AGE_HOURS = 24.0

SCORE_SCALE = {
    "min": -1.0,
    "neutral": 0.0,
    "max": 1.0,
    "positive_meaning": "prediction markets imply more crypto risk-on expectation",
    "negative_meaning": "prediction markets imply more crypto risk-off expectation",
}


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    if value is None:
        return default
    return bool(value)


def _parse_json_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _env_int(name: str, default: int) -> int:
    value = _safe_float(os.getenv(name), float(default))
    return int(value) if value is not None else default


def _env_float(name: str, default: float) -> float:
    value = _safe_float(os.getenv(name), default)
    return value if value is not None else default


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _round(value: Any, digits: int = 4) -> Optional[float]:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return round(parsed, digits)


def score_label(score: Optional[float]) -> str:
    if score is None:
        return "UNAVAILABLE"
    if score >= 0.50:
        return "STRONG_RISK_ON"
    if score >= 0.15:
        return "MILD_RISK_ON"
    if score > -0.15:
        return "NEUTRAL"
    if score > -0.50:
        return "MILD_RISK_OFF"
    return "STRONG_RISK_OFF"


def delta_label(delta: Optional[float]) -> str:
    if delta is None:
        return "UNAVAILABLE"
    if delta >= 0.05:
        return "IMPROVING"
    if delta >= 0.02:
        return "SLIGHTLY_IMPROVING"
    if delta > -0.02:
        return "STABLE"
    if delta > -0.05:
        return "SLIGHTLY_WEAKENING"
    return "WEAKENING"


def _horizon(days_to_expiry: float, end_dt: Optional[datetime], now: datetime) -> str:
    if 3 <= days_to_expiry <= 14:
        return "short_term"
    if 14 < days_to_expiry <= 90:
        return "medium_term"
    if 90 < days_to_expiry <= 450:
        if end_dt and end_dt.year in {now.year, now.year + 1}:
            return "year_end"
        return "long_term"
    return "out_of_scope"


def _asset_from_text(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(bitcoin|btc)\b", lowered):
        return "BTC"
    if re.search(r"\b(ethereum|ether|eth)\b", lowered):
        return "ETH"
    if re.search(r"\b(solana|sol)\b", lowered):
        return "SOL"
    return "CRYPTO"


def _market_type(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("hit", "reach", "touch", "ath", "all-time high")):
        return "touch_before_date"
    if any(word in lowered for word in ("between", "range")):
        return "price_range"
    if any(word in lowered for word in ("above", "over", "greater than", "at least", "below", "under", "less than")):
        return "terminal_price_threshold"
    if any(word in lowered for word in ("etf", "sec", "reserve", "regulation", "regulatory")):
        return "policy_regulation"
    return "ambiguous"


def _direction_sign(text: str) -> Optional[int]:
    lowered = text.lower()
    bearish = ("below", "under", "less than", "crash", "drop", "fall")
    bullish = ("above", "over", "greater than", "at least", "hit", "reach", "touch", "ath", "all-time high")
    if any(word in lowered for word in bearish):
        return -1
    if any(word in lowered for word in bullish):
        return 1
    return None


def _yes_price(market: Dict[str, Any]) -> Optional[float]:
    outcomes = [str(item).strip().lower() for item in _parse_json_list(market.get("outcomes"))]
    prices = _parse_json_list(market.get("outcomePrices"))
    yes_index = 0
    if "yes" in outcomes:
        yes_index = outcomes.index("yes")
    if len(prices) > yes_index:
        return _safe_float(prices[yes_index])
    return _safe_float(market.get("lastTradePrice"))


def _liquidity_value(market: Dict[str, Any]) -> float:
    for key in ("liquidityClob", "liquidity", "liquidityNum"):
        value = _safe_float(market.get(key))
        if value is not None:
            return value
    return 0.0


def _volume_24h_value(market: Dict[str, Any], event: Dict[str, Any]) -> float:
    for key in ("volume24hrClob", "volume24hr"):
        value = _safe_float(market.get(key))
        if value is not None:
            return value
    value = _safe_float(event.get("volume24hr"))
    return value if value is not None else 0.0


def _open_interest_value(market: Dict[str, Any], event: Dict[str, Any]) -> float:
    value = _safe_float(market.get("openInterest"))
    if value is not None:
        return value
    # Gamma often omits per-market open interest on crypto markets. Total volume
    # is a weaker proxy, so it is used only for filtering/weighting, not shown as
    # literal open interest.
    for key in ("volumeNum", "volumeClob", "volume"):
        proxy = _safe_float(market.get(key))
        if proxy is not None:
            return proxy
    proxy = _safe_float(event.get("openInterest"))
    return proxy if proxy is not None else 0.0


def _market_id(market: Dict[str, Any]) -> str:
    for key in ("conditionId", "questionID", "id", "slug"):
        value = market.get(key)
        if value:
            return str(value)
    digest = hashlib.sha1(str(market.get("question") or "").encode("utf-8")).hexdigest()
    return f"question:{digest}"


def _eligibility(
    market: Dict[str, Any],
    event: Dict[str, Any],
    now: datetime,
    *,
    min_volume_24h: float,
    min_liquidity: float,
    min_open_interest_proxy: float,
    max_spread: float,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    question = str(market.get("question") or event.get("title") or "")
    end_dt = _parse_datetime(market.get("endDate") or market.get("endDateIso") or event.get("endDate"))
    updated_dt = _parse_datetime(market.get("updatedAt") or event.get("updatedAt"))
    days_to_expiry = (end_dt - now).total_seconds() / 86400 if end_dt else None
    spread = _safe_float(market.get("spread"))
    liquidity = _liquidity_value(market)
    volume_24h = _volume_24h_value(market, event)
    oi_proxy = _open_interest_value(market, event)
    market_type = _market_type(question)
    direction = _direction_sign(question)
    price = _yes_price(market)

    reasons: List[str] = []
    if not _safe_bool(market.get("active"), default=False):
        reasons.append("inactive_market")
    if _safe_bool(market.get("closed"), default=False):
        reasons.append("closed_market")
    if not _safe_bool(market.get("enableOrderBook"), default=False):
        reasons.append("order_book_disabled")
    if days_to_expiry is None:
        reasons.append("missing_end_date")
    elif days_to_expiry < 3:
        reasons.append("expiry_too_close")
    elif days_to_expiry > 450:
        reasons.append("expiry_too_far")
    if updated_dt is None:
        reasons.append("missing_update_time")
    elif (now - updated_dt).total_seconds() > 36 * 3600:
        reasons.append("stale_update")
    if volume_24h < min_volume_24h:
        reasons.append("low_24h_volume")
    if liquidity < min_liquidity:
        reasons.append("low_liquidity")
    if oi_proxy < min_open_interest_proxy:
        reasons.append("low_open_interest_proxy")
    if spread is not None and spread > max_spread:
        reasons.append("wide_spread")
    if price is None or price <= 0.0 or price >= 1.0:
        reasons.append("invalid_yes_price")
    if market_type == "ambiguous":
        reasons.append("ambiguous_market_type")
    if direction is None:
        reasons.append("unclear_direction")

    meta = {
        "market_id": _market_id(market),
        "question": question,
        "asset": _asset_from_text(question),
        "market_type": market_type,
        "direction_sign": direction,
        "yes_price": price,
        "end_date": _iso(end_dt) if end_dt else None,
        "updated_at": _iso(updated_dt) if updated_dt else None,
        "days_to_expiry": _round(days_to_expiry, 2),
        "spread": _round(spread, 4),
        "volume_24h": _round(volume_24h, 2),
        "liquidity": _round(liquidity, 2),
        "open_interest_proxy": _round(oi_proxy, 2),
        "horizon": _horizon(days_to_expiry or -1, end_dt, now),
    }
    return not reasons, reasons, meta


def _market_weight(meta: Dict[str, Any]) -> float:
    volume_score = min(1.0, (_safe_float(meta.get("volume_24h"), 0.0) or 0.0) / 50_000.0)
    liquidity_score = min(1.0, (_safe_float(meta.get("liquidity"), 0.0) or 0.0) / 50_000.0)
    oi_score = min(1.0, (_safe_float(meta.get("open_interest_proxy"), 0.0) or 0.0) / 100_000.0)
    spread = _safe_float(meta.get("spread"))
    spread_score = 0.55 if spread is None else max(0.0, 1.0 - spread / 0.12)
    type_weight = {
        "terminal_price_threshold": 1.0,
        "touch_before_date": 0.35,
        "price_range": 0.55,
        "policy_regulation": 0.50,
    }.get(str(meta.get("market_type")), 0.25)
    horizon_weight = {
        "short_term": 0.70,
        "medium_term": 1.0,
        "long_term": 0.85,
        "year_end": 0.90,
    }.get(str(meta.get("horizon")), 0.25)
    raw = (0.35 * volume_score) + (0.35 * liquidity_score) + (0.15 * oi_score) + (0.15 * spread_score)
    return round(max(0.01, raw * type_weight * horizon_weight), 6)


def _market_score(meta: Dict[str, Any]) -> Optional[float]:
    price = _safe_float(meta.get("yes_price"))
    direction = _safe_float(meta.get("direction_sign"))
    if price is None or direction is None:
        return None
    if meta.get("market_type") == "touch_before_date":
        # A low Yes price on "will hit/reach an extreme target" usually means
        # "tail move unlikely", not "opposite direction is favored".
        tail_score = max(0.0, (price - 0.35) / 0.65)
        return round(tail_score * direction, 6)
    # Yes price is transformed from 0..1 probability into -1..1 expectation.
    return round((price - 0.5) * 2.0 * direction, 6)


def _flatten_markets(events: Iterable[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    min_volume_24h = _safe_float(os.getenv("POLYMARKET_MIN_VOLUME_24H"), 1000.0) or 1000.0
    min_liquidity = _safe_float(os.getenv("POLYMARKET_MIN_LIQUIDITY"), 2000.0) or 2000.0
    min_oi = _safe_float(os.getenv("POLYMARKET_MIN_OPEN_INTEREST_PROXY"), 5000.0) or 5000.0
    max_spread = _safe_float(os.getenv("POLYMARKET_MAX_SPREAD"), 0.12) or 0.12

    rows: List[Dict[str, Any]] = []
    seen = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        for market in event.get("markets") or []:
            if not isinstance(market, dict):
                continue
            eligible, reasons, meta = _eligibility(
                market,
                event,
                now,
                min_volume_24h=min_volume_24h,
                min_liquidity=min_liquidity,
                min_open_interest_proxy=min_oi,
                max_spread=max_spread,
            )
            market_id = meta["market_id"]
            if market_id in seen:
                continue
            seen.add(market_id)
            score = _market_score(meta)
            weight = _market_weight(meta) if eligible and score is not None else 0.0
            rows.append(
                {
                    **meta,
                    "eligible": eligible and score is not None,
                    "exclude_reasons": reasons,
                    "market_score": score,
                    "market_label": score_label(score),
                    "weight": weight,
                    "snapshot_at": _iso(now),
                }
            )
    return rows


def _watchlist_ids_from_env() -> List[str]:
    raw = os.getenv("POLYMARKET_WATCHLIST_MARKET_IDS", "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = []
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _watchlist_ids_from_rows(rows: Any) -> List[str]:
    if not isinstance(rows, list):
        return []
    out: List[str] = []
    for row in rows:
        if isinstance(row, str) and row.strip():
            out.append(row.strip())
            continue
        if not isinstance(row, dict):
            continue
        if row.get("active") is False or row.get("retired") is True:
            continue
        market_id = row.get("market_id") or row.get("conditionId") or row.get("id")
        if market_id:
            out.append(str(market_id).strip())
    return [item for item in out if item]


def load_watchlist_market_ids() -> List[str]:
    env_ids = _watchlist_ids_from_env()
    stored_ids = _watchlist_ids_from_rows(db.get_data(WATCHLIST_COLLECTION, []))
    seen = set()
    out = []
    for market_id in env_ids + stored_ids:
        if market_id in seen:
            continue
        seen.add(market_id)
        out.append(market_id)
    return out


def _market_history_stats(market_id: str, market_history: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    timestamps = []
    for row in market_history:
        if str(row.get("market_id")) != str(market_id):
            continue
        ts = _parse_datetime(row.get("snapshot_at"))
        if ts and ts <= now:
            timestamps.append(ts)
    if not timestamps:
        return {"observation_count": 0, "first_seen_at": None, "last_seen_at": None, "observed_age_hours": 0.0}
    timestamps.sort()
    first_seen = timestamps[0]
    last_seen = timestamps[-1]
    return {
        "observation_count": len(timestamps),
        "first_seen_at": _iso(first_seen),
        "last_seen_at": _iso(last_seen),
        "observed_age_hours": round((now - first_seen).total_seconds() / 3600.0, 2),
    }


def _annotate_reference_stability(
    markets: List[Dict[str, Any]],
    market_history: List[Dict[str, Any]],
    watchlist_market_ids: List[str],
    now: datetime,
) -> List[Dict[str, Any]]:
    explicit_ids = {str(item) for item in watchlist_market_ids}
    min_obs = _env_int("POLYMARKET_STABLE_MIN_OBSERVATIONS", DEFAULT_STABLE_MIN_OBSERVATIONS)
    min_age = _env_float("POLYMARKET_STABLE_MIN_AGE_HOURS", DEFAULT_STABLE_MIN_AGE_HOURS)
    annotated = []
    for market in markets:
        row = dict(market)
        stats = _market_history_stats(str(row.get("market_id")), market_history, now)
        explicitly_watched = str(row.get("market_id")) in explicit_ids
        history_stable = (
            bool(row.get("eligible"))
            and stats["observation_count"] >= min_obs
            and stats["observed_age_hours"] >= min_age
        )
        stable = bool(row.get("eligible")) and (explicitly_watched or history_stable)
        row.update(stats)
        row["explicit_watchlist"] = explicitly_watched
        row["stable_reference_market"] = stable
        if stable:
            row["reference_status"] = "WATCHLIST" if explicitly_watched else "HISTORY_STABLE"
        elif row.get("eligible"):
            row["reference_status"] = "REPLACEMENT_CANDIDATE"
        else:
            row["reference_status"] = "EXCLUDED"
        annotated.append(row)
    return annotated


def fetch_polymarket_events(
    *,
    queries: Iterable[str] = SEARCH_QUERIES,
    limit: int = 25,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    client = session or requests.Session()
    events: List[Dict[str, Any]] = []
    seen = set()
    timeout = _safe_float(os.getenv("POLYMARKET_REQUEST_TIMEOUT"), 8.0) or 8.0
    for query in queries:
        response = client.get(GAMMA_SEARCH_URL, params={"q": query, "limit": limit}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        for event in payload.get("events") or []:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("id") or event.get("slug") or event.get("title") or "")
            if not event_id or event_id in seen:
                continue
            seen.add(event_id)
            events.append(event)
    return events


def _composition_hash(markets: List[Dict[str, Any]]) -> str:
    market_ids = sorted(str(item.get("market_id")) for item in markets if item.get("stable_reference_market"))
    joined = "|".join(market_ids)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def _weighted_score(markets: List[Dict[str, Any]]) -> Optional[float]:
    numerator = 0.0
    denominator = 0.0
    for market in markets:
        score = _safe_float(market.get("market_score"))
        weight = _safe_float(market.get("weight"), 0.0) or 0.0
        if score is None or weight <= 0:
            continue
        numerator += score * weight
        denominator += weight
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _nearest_prior_signal(history: List[Dict[str, Any]], target_ts: datetime, max_age_hours: float) -> Optional[Dict[str, Any]]:
    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for row in history:
        ts = _parse_datetime(row.get("snapshot_at"))
        if not ts or ts > target_ts:
            continue
        age_hours = abs((target_ts - ts).total_seconds()) / 3600.0
        if age_hours <= max_age_hours:
            candidates.append((age_hours, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _nearest_market_by_id(
    history: List[Dict[str, Any]],
    market_id: str,
    target_ts: datetime,
    max_age_hours: float,
) -> Optional[Dict[str, Any]]:
    matches = [row for row in history if str(row.get("market_id")) == str(market_id)]
    return _nearest_prior_signal(matches, target_ts, max_age_hours)


def _delta_summary(
    current_signal: Dict[str, Any],
    current_markets: List[Dict[str, Any]],
    signal_history: List[Dict[str, Any]],
    market_history: List[Dict[str, Any]],
    now: datetime,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    current_score = _safe_float(current_signal.get("combined_score"))
    current_composition = current_signal.get("composition_hash")
    current_ids = {str(item.get("market_id")) for item in current_markets if item.get("stable_reference_market")}
    for hours in DELTA_WINDOWS_HOURS:
        key = f"{hours}h" if hours < 168 else ("7d" if hours == 168 else "30d")
        target = datetime.fromtimestamp(now.timestamp() - hours * 3600, tz=timezone.utc)
        prior = _nearest_prior_signal(signal_history, target, max_age_hours=max(6.0, hours * 0.35))
        prior_score = _safe_float(prior.get("combined_score")) if prior else None
        delta = round(current_score - prior_score, 6) if current_score is not None and prior_score is not None else None
        same_market_deltas = []
        for market in current_markets:
            if not market.get("stable_reference_market"):
                continue
            prior_market = _nearest_market_by_id(
                market_history,
                str(market.get("market_id")),
                target,
                max_age_hours=max(6.0, hours * 0.35),
            )
            if not prior_market:
                continue
            prior_market_score = _safe_float(prior_market.get("market_score"))
            current_market_score = _safe_float(market.get("market_score"))
            if prior_market_score is None or current_market_score is None:
                continue
            same_market_deltas.append(current_market_score - prior_market_score)
        overlap_count = len(same_market_deltas)
        same_market_delta = (
            round(sorted(same_market_deltas)[overlap_count // 2], 6)
            if overlap_count
            else None
        )
        prior_ids = set(prior.get("market_ids") or []) if prior else set()
        out[f"score_delta_{key}"] = _round(delta, 4)
        out[f"score_delta_{key}_label"] = delta_label(delta)
        out[f"same_market_delta_{key}"] = _round(same_market_delta, 4)
        out[f"same_market_overlap_{key}_count"] = overlap_count
        out[f"composition_changed_{key}"] = bool(prior and current_composition != prior.get("composition_hash"))
        out[f"market_set_overlap_{key}_count"] = len(current_ids & prior_ids) if prior else 0
    return out


def _confidence(signal: Dict[str, Any]) -> str:
    count = int(signal.get("stable_market_count") or 0)
    overlap_24h = int(signal.get("same_market_overlap_24h_count") or 0)
    changed = bool(signal.get("composition_changed_24h"))
    if count >= 6 and overlap_24h >= 3 and not changed:
        return "HIGH"
    if count >= 3:
        return "MEDIUM"
    if count > 0:
        return "LOW"
    return "UNAVAILABLE"


def _basket_scores(markets: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    baskets: Dict[str, Dict[str, Any]] = {}
    for horizon in ("short_term", "medium_term", "long_term", "year_end"):
        selected = [item for item in markets if item.get("stable_reference_market") and item.get("horizon") == horizon]
        score = _weighted_score(selected)
        baskets[horizon] = {
            "score": _round(score, 4),
            "label": score_label(score),
            "usable_market_count": len(selected),
            "total_weight": _round(sum(_safe_float(item.get("weight"), 0.0) or 0.0 for item in selected), 4),
        }
    return baskets


def _build_signal(
    markets: List[Dict[str, Any]],
    signal_history: List[Dict[str, Any]],
    market_history: List[Dict[str, Any]],
    now: datetime,
) -> Dict[str, Any]:
    eligible = [item for item in markets if item.get("eligible")]
    stable = [item for item in markets if item.get("stable_reference_market")]
    candidates = [item for item in markets if item.get("reference_status") == "REPLACEMENT_CANDIDATE"]
    baskets = _basket_scores(markets)
    horizon_weights = {"short_term": 0.20, "medium_term": 0.40, "long_term": 0.25, "year_end": 0.15}
    numerator = 0.0
    denominator = 0.0
    for horizon, basket in baskets.items():
        score = _safe_float(basket.get("score"))
        if score is None:
            continue
        weight = horizon_weights[horizon] * max(1.0, _safe_float(basket.get("total_weight"), 0.0) or 0.0)
        numerator += score * weight
        denominator += weight
    combined_score = round(numerator / denominator, 6) if denominator > 0 else None
    market_ids = sorted(str(item.get("market_id")) for item in stable)
    signal = {
        "available": combined_score is not None,
        "source": "polymarket_gamma_public_search",
        "calculation_owner": "program",
        "interpretation_scope": "prediction_market_expectation_reference_only",
        "primary_signal_basis": "same_market_momentum_preferred",
        "absolute_score_role": "background_only",
        "score_scale": SCORE_SCALE,
        "snapshot_at": _iso(now),
        "combined_score": _round(combined_score, 4),
        "combined_label": score_label(combined_score),
        "eligible_market_count": len(eligible),
        "stable_market_count": len(stable),
        "candidate_market_count": len(candidates),
        "excluded_market_count": len(markets) - len(eligible),
        "market_ids": market_ids,
        "reference_market_ids": market_ids,
        "composition_hash": _composition_hash(markets),
        "horizons": baskets,
        "markets_used": [
            {
                "market_id": item.get("market_id"),
                "asset": item.get("asset"),
                "horizon": item.get("horizon"),
                "market_type": item.get("market_type"),
                "question": item.get("question"),
                "yes_price": item.get("yes_price"),
                "market_score": _round(item.get("market_score"), 4),
                "market_label": item.get("market_label"),
                "weight": _round(item.get("weight"), 4),
                "days_to_expiry": item.get("days_to_expiry"),
                "volume_24h": item.get("volume_24h"),
                "liquidity": item.get("liquidity"),
                "spread": item.get("spread"),
                "reference_status": item.get("reference_status"),
                "observation_count": item.get("observation_count"),
                "observed_age_hours": item.get("observed_age_hours"),
            }
            for item in sorted(stable, key=lambda row: _safe_float(row.get("weight"), 0.0) or 0.0, reverse=True)[:12]
        ],
        "replacement_candidates": [
            {
                "market_id": item.get("market_id"),
                "asset": item.get("asset"),
                "horizon": item.get("horizon"),
                "market_type": item.get("market_type"),
                "question": item.get("question"),
                "yes_price": item.get("yes_price"),
                "market_score": _round(item.get("market_score"), 4),
                "market_label": item.get("market_label"),
                "weight": _round(item.get("weight"), 4),
                "days_to_expiry": item.get("days_to_expiry"),
                "reference_status": item.get("reference_status"),
                "observation_count": item.get("observation_count"),
                "observed_age_hours": item.get("observed_age_hours"),
            }
            for item in sorted(candidates, key=lambda row: _safe_float(row.get("weight"), 0.0) or 0.0, reverse=True)[:8]
        ],
        "exclude_reason_counts": _reason_counts(markets),
    }
    signal.update(_delta_summary(signal, stable, signal_history, market_history, now))
    for key in ("4h", "24h", "7d", "30d"):
        momentum = signal.get(f"same_market_delta_{key}")
        signal[f"expectation_momentum_{key}"] = momentum
        signal[f"expectation_momentum_{key}_label"] = delta_label(momentum)
    if combined_score is None:
        signal["missing_reason"] = "no_stable_reference_markets"
    signal["confidence"] = _confidence(signal)
    return signal


def _reason_counts(markets: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for market in markets:
        for reason in market.get("exclude_reasons") or []:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _history_cutoff(now: datetime) -> datetime:
    return datetime.fromtimestamp(now.timestamp() - MAX_HISTORY_DAYS * 86400, tz=timezone.utc)


def _trim_history(rows: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    cutoff = _history_cutoff(now)
    trimmed = []
    for row in rows:
        ts = _parse_datetime(row.get("snapshot_at"))
        if ts and ts >= cutoff:
            trimmed.append(row)
    return trimmed[-MAX_HISTORY_ROWS:]


def _append_and_persist(
    collection: str,
    current_rows: List[Dict[str, Any]],
    history_rows: List[Dict[str, Any]],
    now: datetime,
) -> None:
    if not current_rows:
        return
    merged = _trim_history(history_rows + current_rows, now)
    db.save_data(collection, merged)


def unavailable_signal(reason: str) -> Dict[str, Any]:
    return {
        "available": False,
        "source": "polymarket_gamma_public_search",
        "calculation_owner": "program",
        "interpretation_scope": "prediction_market_expectation_reference_only",
        "score_scale": SCORE_SCALE,
        "combined_score": None,
        "combined_label": "UNAVAILABLE",
        "confidence": "UNAVAILABLE",
        "missing_reason": reason,
        "eligible_market_count": 0,
        "stable_market_count": 0,
        "candidate_market_count": 0,
        "excluded_market_count": 0,
        "markets_used": [],
        "replacement_candidates": [],
        "horizons": {},
    }


def build_prediction_market_signal(
    *,
    now: Optional[datetime] = None,
    fetch_events: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    market_history: Optional[List[Dict[str, Any]]] = None,
    signal_history: Optional[List[Dict[str, Any]]] = None,
    watchlist_market_ids: Optional[List[str]] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fetched_events = fetch_events() if fetch_events is not None else fetch_polymarket_events()
    markets = _flatten_markets(fetched_events, now)
    existing_market_history = market_history if market_history is not None else db.get_data(MARKET_SNAPSHOT_COLLECTION, [])
    existing_signal_history = signal_history if signal_history is not None else db.get_data(SIGNAL_SNAPSHOT_COLLECTION, [])
    watchlist_ids = watchlist_market_ids if watchlist_market_ids is not None else load_watchlist_market_ids()
    markets = _annotate_reference_stability(markets, existing_market_history, watchlist_ids, now)
    signal = _build_signal(markets, existing_signal_history, existing_market_history, now)
    if persist:
        _append_and_persist(MARKET_SNAPSHOT_COLLECTION, markets, existing_market_history, now)
        _append_and_persist(SIGNAL_SNAPSHOT_COLLECTION, [signal], existing_signal_history, now)
    return signal
