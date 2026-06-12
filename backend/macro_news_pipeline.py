import json
import os
import re
from typing import Any, Dict, List, Optional

from llm_client import call_llm_json_with_audit
from polymarket_signal import build_prediction_market_signal, unavailable_signal

ALLOWED_MARKET_IMPACTS = {"RISK_ON", "RISK_OFF", "MIXED", "NO_CLEAR_IMPACT"}
ALLOWED_IMPACT_HORIZONS = {"INTRADAY", "SWING", "MULTI_DAY", "NOISE"}
ALLOWED_CRYPTO_RELEVANCE = {"HIGH", "MEDIUM", "LOW"}
EVENT_NEWS_BUCKETS = ["macro", "calendar", "general", "bitcoin", "ethereum", "solana", "bnb", "doge"]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _optional_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.replace("%", "").replace(",", "").strip()
            if cleaned == "":
                return None
            return float(cleaned)
        return float(value)
    except Exception:
        return None


def _news_text(item: Dict[str, Any]) -> str:
    return f"{item.get('title') or ''} {item.get('summary') or ''} {item.get('tags') or ''}".lower()


def _word_hit(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


def _news_relevance_score(bucket_name: str, item: Dict[str, Any]) -> int:
    text = _news_text(item)
    score = {
        "calendar": 7,
        "macro": 6,
        "general": 4,
        "bitcoin": 3,
        "ethereum": 3,
        "solana": 3,
        "bnb": 3,
        "doge": 3,
    }.get(bucket_name, 1)

    macro_patterns = [
        r"\bfed\b|\bfomc\b|\bpowell\b|\bfederal reserve\b",
        r"\bcpi\b|\bpce\b|\bppi\b|\binflation\b",
        r"\bpayroll|\bnfp\b|\bjobs report\b|\bunemployment\b",
        r"\bdxy\b|\bdollar\b|\busd\b|\btreasury|\byield",
        r"\bliquidity\b|\bcredit\b|\bbank",
    ]
    crypto_patterns = [
        r"\bcrypto|\bbitcoin\b|\bbtc\b|\bethereum\b|\beth\b",
        r"\bsolana\b|\bsol\b|\bbnb\b|\bdoge\b",
        r"\bstablecoin\b|\busdt\b|\busdc\b",
        r"\betf\b|\bsec\b|\bregulation\b|\bexchange\b",
        r"\bliquidation\b|\bleverage\b|\bhack\b|\bexploit\b",
    ]
    risk_event_patterns = [
        r"\bshock\b|\bcrisis\b|\bsanction\b|\bdefault\b",
        r"\bplunge\b|\bcrash\b|\bdrop\b|\bselloff\b|\bdump\b",
        r"\bsurge\b|\brally\b|\bbreakout\b|\brebound\b",
        r"\bceasefire\b|\bde-escalation\b|\bescalation\b|\bstrike\b",
        r"\bapproval\b|\breject\b|\blawsuit\b|\bprobe\b",
    ]

    score += 4 * sum(1 for pattern in macro_patterns if _word_hit(text, pattern))
    score += 5 * sum(1 for pattern in crypto_patterns if _word_hit(text, pattern))
    score += 3 * sum(1 for pattern in risk_event_patterns if _word_hit(text, pattern))
    if _has_labor_context(text):
        score += 8

    sentiment = str(item.get("sentiment") or "").upper()
    if sentiment in {"BULLISH", "BEARISH"}:
        score += 1
    if item.get("source"):
        score += 1
    return score


def _rank_event_news(news_obj: Dict[str, Any], limit: int = 12, scan_per_bucket: int = 15) -> Dict[str, Any]:
    ranked: List[Dict[str, Any]] = []
    seen = set()
    for bucket_name in EVENT_NEWS_BUCKETS:
        bucket = news_obj.get(bucket_name, {})
        if not isinstance(bucket, dict):
            continue
        for item in bucket.get("items", [])[:scan_per_bucket]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            normalized = title.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            ranked.append({
                "title": title,
                "bucket": bucket_name,
                "score": _news_relevance_score(bucket_name, item),
                "published": item.get("published"),
                "source": item.get("source") or item.get("link"),
                "sentiment": item.get("sentiment"),
            })
    ranked.sort(key=lambda event: (event["score"], str(event.get("published") or "")), reverse=True)
    return {
        "selected": ranked[:limit],
        "dropped": ranked[limit:limit + 20],
        "candidate_count": len(ranked),
    }


def _event_headlines(news_obj: Dict[str, Any], limit: int = 12) -> List[str]:
    return [event["title"] for event in _rank_event_news(news_obj, limit=limit)["selected"]]


def _nested_float(obj: Dict[str, Any], *path: str, default: float = 0.0) -> float:
    current: Any = obj
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return _safe_float(current, default)


def _first_positive_float(values: List[float], default: float = 0.0) -> float:
    for value in values:
        if value > 0:
            return value
    return default


def _scaled_threshold(*, baseline: float, floor: float, scale: float = 1.0) -> float:
    return max(floor, baseline * scale)


def _stable_flow_thresholds(macro_data: Dict[str, Any]) -> Dict[str, float]:
    liquidity = macro_data.get("liquidity_monitor", {}) or {}
    market_cap = _first_positive_float([
        _safe_float(macro_data.get("global_stable_market_cap")),
        _safe_float(macro_data.get("global_stablecoin_market_cap")),
        _safe_float(macro_data.get("total_stablecoin_market_cap")),
        _safe_float(liquidity.get("global_stable_market_cap")),
    ])
    flow_std = _first_positive_float([
        _safe_float(macro_data.get("global_stable_flow_30d_std")),
        _safe_float(macro_data.get("global_stable_flow_std")),
        _safe_float(liquidity.get("global_stable_flow_30d_std")),
    ])
    return {
        "tag": max(100_000_000, market_cap * 0.001, flow_std * 1.5),
        "high_relevance": max(150_000_000, market_cap * 0.0015, flow_std * 2.0),
        "swing": max(250_000_000, market_cap * 0.003, flow_std * 2.5),
    }


def _contains_unnegated(text: str, keywords: List[str]) -> bool:
    negations = r"(?:not|no|less|non|without|isn't|aren't|wasn't|weren't|never)"
    for keyword in keywords:
        pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
        for match in re.finditer(pattern, text):
            prefix = text[max(0, match.start() - 24):match.start()]
            if re.search(rf"{negations}\s+(?:\w+\s+){{0,2}}$", prefix):
                continue
            return True
    return False


def _headline_text(headlines: List[str]) -> str:
    return " ".join(headlines).lower()


def _has_labor_context(text: str) -> bool:
    return any(token in text for token in [
        "nonfarm",
        "non-farm",
        "nfp",
        "us payroll",
        "u.s. payroll",
        "payrolls",
        "jobs report",
        "unemployment rate",
        "jobless rate",
        "labor market",
    ])


def _has_us_core_macro_event(text: str) -> bool:
    fed_policy_context = any(token in text for token in [
        "fomc",
        "fed decision",
        "federal reserve decision",
        "fed meeting",
        "fomc minutes",
        "fed minutes",
        "fed press conference",
        "federal reserve press conference",
    ])
    powell_policy_context = (
        "powell" in text
        and any(token in text for token in [
            "says",
            "speech",
            "testimony",
            "press conference",
            "rates",
            "rate cut",
            "rate hike",
            "inflation",
            "policy",
        ])
    )
    us_inflation_context = any(token in text for token in [
        "us cpi",
        "u.s. cpi",
        "core cpi",
        "cpi report",
        "cpi hotter",
        "cpi cooler",
        "us pce",
        "u.s. pce",
        "core pce",
        "pce report",
    ])
    us_labor_context = _has_labor_context(text)
    return fed_policy_context or powell_policy_context or us_inflation_context or us_labor_context


def _has_foreign_central_bank_event(text: str) -> bool:
    return any(token in text for token in [
        "boj",
        "bank of japan",
        "ecb",
        "european central bank",
        "boe",
        "bank of england",
        "jgb",
    ])


def _has_fed_leadership_event(text: str) -> bool:
    return any(token in text for token in [
        "fed chair nominee",
        "fed chair successor",
        "powell term",
        "warsh",
        "senate confirmation",
        "fed leadership",
    ])


def _base_event_facts(fear_greed: Dict[str, Any], macro_data: Dict[str, Any]) -> Dict[str, Any]:
    fed = macro_data.get("fed_futures", {}) or {}
    japan = macro_data.get("japan_macro", {}) or {}
    liquidity = macro_data.get("liquidity_monitor", {}) or {}
    dxy = liquidity.get("dxy", {}) or {}
    vix = liquidity.get("vix", {}) or {}
    us10y = liquidity.get("us10y", {}) or {}
    stable_market_cap = _first_positive_float([
        _safe_float(macro_data.get("global_stable_market_cap")),
        _safe_float(macro_data.get("global_stablecoin_market_cap")),
        _safe_float(macro_data.get("total_stablecoin_market_cap")),
        _safe_float(liquidity.get("global_stable_market_cap")),
    ])
    stable_flow = _safe_float(macro_data.get("global_stable_flow"))
    return {
        "fear_greed_index": _safe_float(fear_greed.get("value"), 50.0),
        "fear_greed_state": str(fear_greed.get("value_classification") or "NEUTRAL").upper(),
        "fear_greed_change_5d": _optional_float(macro_data.get("fear_greed_change_5d")),
        "fed_implied_rate": _safe_float(fed.get("implied_rate")),
        "fed_change_5d_bps": _safe_float(fed.get("change_5d_bps")),
        "usdjpy_level": _safe_float(japan.get("price")),
        "usdjpy_change_5d_pct": _safe_float(japan.get("change_5d_pct")),
        "dxy_level": _safe_float(dxy.get("price")),
        "dxy_change_5d_pct": _safe_float(dxy.get("change_5d_pct")),
        "vix_level": _optional_float(vix.get("price")),
        "vix_change_1d_pct": _optional_float(vix.get("change_1d_pct")),
        "vix_change_5d_pct": _optional_float(vix.get("change_5d_pct")),
        "us10y_level": _safe_float(us10y.get("price")),
        "us10y_change_5d_pct": _safe_float(us10y.get("change_5d_pct")),
        "global_stable_flow": stable_flow,
        "global_stable_market_cap": stable_market_cap,
        "global_stable_flow_ratio_pct": (stable_flow / stable_market_cap * 100.0) if stable_market_cap > 0 else 0.0,
    }


def _trend_label(change_pct: float, *, positive_label: str = "UP", negative_label: str = "DOWN", threshold: float = 0.2) -> str:
    if change_pct >= threshold:
        return positive_label
    if change_pct <= -threshold:
        return negative_label
    return "FLAT"


def _policy_stance(macro_data: Dict[str, Any]) -> str:
    fed = macro_data.get("fed_futures", {}) or {}
    text = " ".join(
        str(fed.get(key, ""))
        for key in ["trend", "trend_zh", "zone", "zone_zh"]
    ).lower()
    change_bps = _safe_float(fed.get("change_5d_bps"))
    move_threshold = _scaled_threshold(
        baseline=_first_positive_float([
            _safe_float(fed.get("change_30d_std_bps")),
            _safe_float(fed.get("vol_30d_bps")),
            _safe_float(fed.get("change_std_bps")),
        ], default=2.5),
        floor=2.5,
    )
    if _contains_unnegated(text, ["restrictive", "hawkish", "hawk"]) or "高位" in text or change_bps >= move_threshold:
        return "HAWKISH"
    if _contains_unnegated(text, ["easing", "dovish"]) or "宽松" in text or change_bps <= -move_threshold:
        return "DOVISH"
    return "NEUTRAL"


def _key_tags(facts: Dict[str, Any], macro_data: Dict[str, Any], headlines: List[str]) -> List[str]:
    tags: List[str] = []
    stance = _policy_stance(macro_data)
    dxy_threshold = _scaled_threshold(
        baseline=_first_positive_float([
            _nested_float(macro_data, "liquidity_monitor", "dxy", "change_30d_std_pct"),
            _nested_float(macro_data, "liquidity_monitor", "dxy", "vol_30d_pct"),
        ], default=0.35),
        floor=0.25,
    )
    yen_threshold = _scaled_threshold(
        baseline=_first_positive_float([
            _nested_float(macro_data, "japan_macro", "change_30d_std_pct"),
            _nested_float(macro_data, "japan_macro", "vol_30d_pct"),
        ], default=0.6),
        floor=0.45,
    )
    fed_move_threshold = _scaled_threshold(
        baseline=_first_positive_float([
            _nested_float(macro_data, "fed_futures", "change_30d_std_bps"),
            _nested_float(macro_data, "fed_futures", "vol_30d_bps"),
            _nested_float(macro_data, "fed_futures", "change_std_bps"),
        ], default=2.5),
        floor=2.5,
    )
    vix_relief_threshold = _scaled_threshold(
        baseline=_first_positive_float([
            _nested_float(macro_data, "liquidity_monitor", "vix", "change_30d_std_pct"),
            _nested_float(macro_data, "liquidity_monitor", "vix", "vol_30d_pct"),
        ], default=0.75),
        floor=0.75,
    )
    stable_flow_thresholds = _stable_flow_thresholds(macro_data)
    if stance == "HAWKISH":
        tags.append("FED_HAWKISH")
    elif stance == "DOVISH":
        tags.append("FED_DOVISH")

    fed_change_5d_bps = facts.get("fed_change_5d_bps")
    if fed_change_5d_bps <= -fed_move_threshold:
        tags.append("RATE_EXPECTATION_EASING")
    elif fed_change_5d_bps >= fed_move_threshold:
        tags.append("RATE_EXPECTATION_TIGHTENING")

    if facts["dxy_change_5d_pct"] >= dxy_threshold:
        tags.append("USD_STRENGTH")
    elif facts["dxy_change_5d_pct"] <= -dxy_threshold:
        tags.append("USD_WEAKNESS")

    vix_level = _safe_float(facts.get("vix_level"))
    vix_change_1d_pct = _safe_float(facts.get("vix_change_1d_pct"), _safe_float(facts.get("vix_change_5d_pct")))
    vix_change_5d_pct = _safe_float(facts.get("vix_change_5d_pct"))
    us10y_change_5d_pct = _safe_float(facts.get("us10y_change_5d_pct"))
    yen_risk_context = (
        facts["fear_greed_index"] <= 35
        or vix_level >= 24
        or vix_change_1d_pct >= vix_relief_threshold
        or facts["dxy_change_5d_pct"] >= dxy_threshold
        or us10y_change_5d_pct >= 0.5
    )
    yen_relief_context = (
        fed_change_5d_bps <= -fed_move_threshold
        or facts["dxy_change_5d_pct"] <= -dxy_threshold
        or us10y_change_5d_pct <= -0.5
        or (vix_level > 0 and vix_level < 18 and vix_change_1d_pct <= -vix_relief_threshold)
    )
    if facts["usdjpy_change_5d_pct"] <= -yen_threshold and yen_risk_context and not yen_relief_context:
        tags.append("YEN_STRESS")
    elif facts["usdjpy_change_5d_pct"] >= yen_threshold and not yen_risk_context:
        tags.append("YEN_RELIEF")

    fear_greed_change_5d = facts.get("fear_greed_change_5d")
    if fear_greed_change_5d is not None:
        if fear_greed_change_5d <= -10:
            tags.append("SENTIMENT_COOLING")
        elif fear_greed_change_5d >= 10:
            tags.append("SENTIMENT_RELIEF")

    if facts["fear_greed_index"] <= 35 or vix_level >= 24 or vix_change_1d_pct >= 8:
        tags.append("RISK_OFF_NEWS")
    elif facts["fear_greed_index"] >= 65 and vix_level > 0 and vix_level < 18:
        tags.append("RISK_ON_NEWS")
    if vix_level > 0 and vix_level < 18 and vix_change_1d_pct <= -vix_relief_threshold:
        tags.append("VOL_PRESSURE_EASING")
    elif vix_change_1d_pct >= vix_relief_threshold:
        tags.append("VOL_PRESSURE_RISING")

    if facts["global_stable_flow"] >= stable_flow_thresholds["tag"]:
        tags.append("LIQUIDITY_EXPANDING")
    elif facts["global_stable_flow"] <= -stable_flow_thresholds["tag"]:
        tags.append("LIQUIDITY_CONTRACTING")

    joined = " ".join(headlines).lower()
    if any(token in joined for token in ["ceasefire", "cease-fire", "truce", "de-escalation", "deescalation", "peace talks", "peace deal"]):
        tags.append("GEOPOLITICAL_RISK_EASING")
    elif any(token in joined for token in ["war risk", "war risks", "war poses", "escalation", "strike", "missile", "invasion"]):
        tags.append("GEOPOLITICAL_RISK_RISING")

    if "cpi" in joined and any(token in joined for token in ["hot", "sticky", "higher-than-expected", "inflation"]):
        tags.append("CPI_HOT")
    elif "cpi" in joined and any(token in joined for token in ["cool", "below expectations", "softer"]):
        tags.append("CPI_COOL")
    if _has_labor_context(joined):
        labor_resilient = any(token in joined for token in [
            "payrolls jump",
            "payrolls rose",
            "payroll employment edged up",
            "jobs beat",
            "beat expectations",
            "more than expected",
            "above expectations",
            "unemployment rate unchanged",
            "unemployment held",
            "labor market remains steady",
        ])
        labor_weak = any(token in joined for token in [
            "payrolls miss",
            "jobs miss",
            "below expectations",
            "less than expected",
            "unemployment rate rose",
            "unemployment rises",
            "jobless rate rose",
            "jobless rate rises",
            "layoffs",
            "job cuts",
            "federal government employment continued to decline",
            "labor market slowdown",
            "labor market cooling",
        ])
        if labor_resilient:
            tags.append("LABOR_RESILIENT")
        if labor_weak:
            tags.append("LABOR_WEAKNESS")

    if not tags:
        tags.append("MACRO_NOISE")
    return sorted(set(tags))


MACRO_TAG_WEIGHTS = {
    "FED_HAWKISH": -5,
    "FED_DOVISH": 5,
    "USD_STRENGTH": -2,
    "USD_WEAKNESS": 2,
    "YEN_STRESS": -2,
    "YEN_RELIEF": 2,
    "RISK_OFF_NEWS": -3,
    "RISK_ON_NEWS": 3,
    "SENTIMENT_COOLING": -3,
    "SENTIMENT_RELIEF": 3,
    "RATE_EXPECTATION_TIGHTENING": -2,
    "RATE_EXPECTATION_EASING": 2,
    "VOL_PRESSURE_RISING": -2,
    "VOL_PRESSURE_EASING": 2,
    "GEOPOLITICAL_RISK_RISING": -2,
    "GEOPOLITICAL_RISK_EASING": 2,
    "LIQUIDITY_CONTRACTING": -4,
    "LIQUIDITY_EXPANDING": 4,
    "CPI_HOT": -4,
    "CPI_COOL": 4,
    "LABOR_RESILIENT": 3,
    "LABOR_WEAKNESS": -4,
}
ALLOWED_MACRO_TAGS = set(MACRO_TAG_WEIGHTS) | {"MACRO_NOISE"}


def _market_impact_score(tags: List[str]) -> int:
    return sum(MACRO_TAG_WEIGHTS.get(tag, 0) for tag in tags)


def _market_impact(tags: List[str]) -> str:
    weights = MACRO_TAG_WEIGHTS
    score = sum(weights.get(tag, 0) for tag in tags)
    positive = any(weights.get(tag, 0) > 0 for tag in tags)
    negative = any(weights.get(tag, 0) < 0 for tag in tags)
    if score <= -3:
        return "RISK_OFF"
    if score >= 3:
        return "RISK_ON"
    if positive and negative:
        return "MIXED"
    if score != 0:
        return "MIXED"
    return "NO_CLEAR_IMPACT"


def _macro_bias_tier(score: int, market_impact: str) -> str:
    if market_impact in {"MIXED", "NO_CLEAR_IMPACT"}:
        return "NO_CLEAR_EDGE"
    if score <= -6:
        return "STRONG_RISK_OFF"
    if score <= -3 or (market_impact == "RISK_OFF" and score < 0):
        return "MILD_RISK_OFF"
    if score >= 6:
        return "STRONG_RISK_ON"
    if score >= 3 or (market_impact == "RISK_ON" and score > 0):
        return "MILD_RISK_ON"
    return "NO_CLEAR_EDGE"


def _macro_bias_policy(tier: str) -> Dict[str, Any]:
    if tier == "STRONG_RISK_OFF":
        return {
            "macro_mode": "RISK_OFF",
            "macro_permission": "ALLOW_SHORT",
            "risk_off_score": 0.85,
        }
    if tier == "MILD_RISK_OFF":
        return {
            "macro_mode": "MIXED",
            "macro_permission": "ALLOW_BOTH",
            "risk_off_score": 0.65,
        }
    if tier == "MILD_RISK_ON":
        return {
            "macro_mode": "MIXED",
            "macro_permission": "ALLOW_BOTH",
            "risk_off_score": 0.35,
        }
    if tier == "STRONG_RISK_ON":
        return {
            "macro_mode": "RISK_ON",
            "macro_permission": "ALLOW_LONG",
            "risk_off_score": 0.15,
        }
    return {
        "macro_mode": "MIXED",
        "macro_permission": "ALLOW_BOTH",
        "risk_off_score": 0.5,
    }


def _impact_horizon(facts: Dict[str, Any], tags: List[str], headlines: List[str]) -> str:
    joined = _headline_text(headlines)
    us_core_macro_event = _has_us_core_macro_event(joined)
    foreign_central_bank_event = _has_foreign_central_bank_event(joined)
    fed_leadership_event = _has_fed_leadership_event(joined)
    directional_macro = any(tag in tags for tag in [
        "FED_HAWKISH", "FED_DOVISH", "CPI_HOT", "CPI_COOL", "LIQUIDITY_EXPANDING", "LIQUIDITY_CONTRACTING"
    ])
    stable_flow_ratio_abs = abs(facts.get("global_stable_flow_ratio_pct", 0.0))
    strong_cross_asset_move = (
        abs(facts["dxy_change_5d_pct"]) >= 0.6
        or abs(facts["usdjpy_change_5d_pct"]) >= 0.8
        or abs(facts["global_stable_flow"]) >= 250_000_000
    )
    if us_core_macro_event and directional_macro:
        return "MULTI_DAY"
    if (
        any(tag in tags for tag in ["LIQUIDITY_EXPANDING", "LIQUIDITY_CONTRACTING"])
        and (abs(facts["global_stable_flow"]) >= 500_000_000 or stable_flow_ratio_abs >= 0.20)
    ):
        return "MULTI_DAY"
    if us_core_macro_event:
        return "INTRADAY"
    if foreign_central_bank_event and directional_macro:
        return "SWING"
    if fed_leadership_event and directional_macro:
        return "SWING"
    if strong_cross_asset_move:
        return "SWING"
    if "MACRO_NOISE" in tags and not directional_macro:
        return "NOISE"
    if directional_macro:
        return "SWING"
    return "NOISE"


def _crypto_relevance(tags: List[str], facts: Dict[str, Any]) -> str:
    if tags == ["MACRO_NOISE"]:
        return "LOW"
    if any(tag in tags for tag in ["FED_HAWKISH", "FED_DOVISH", "CPI_HOT", "CPI_COOL"]):
        return "HIGH"
    if abs(facts["global_stable_flow"]) >= max(150_000_000, facts.get("global_stable_market_cap", 0.0) * 0.0015):
        return "HIGH"
    if (
        any(tag in tags for tag in ["RISK_OFF_NEWS", "RISK_ON_NEWS", "USD_STRENGTH", "USD_WEAKNESS", "YEN_STRESS", "YEN_RELIEF"])
        and (abs(facts["dxy_change_5d_pct"]) >= 0.5 or abs(facts["usdjpy_change_5d_pct"]) >= 0.8)
    ):
        return "HIGH"
    if any(tag in tags for tag in ["LIQUIDITY_EXPANDING", "LIQUIDITY_CONTRACTING", "RISK_OFF_NEWS", "RISK_ON_NEWS", "USD_STRENGTH", "USD_WEAKNESS", "YEN_STRESS", "YEN_RELIEF"]):
        return "MEDIUM"
    return "LOW"


def _brief_rationale(tags: List[str], facts: Dict[str, Any], market_impact: str, impact_horizon: str) -> str:
    parts: List[str] = []
    vix_text = f"{facts['vix_level']:.2f}" if facts.get("vix_level") is not None else "N/A"
    vix_change = facts.get("vix_change_1d_pct")
    vix_change_label = "1d"
    if vix_change is None:
        vix_change = facts.get("vix_change_5d_pct")
        vix_change_label = "5d"
    if "FED_HAWKISH" in tags:
        parts.append("Fed pricing remains restrictive")
    if "FED_DOVISH" in tags:
        parts.append("Fed pricing is easing")
    if "RATE_EXPECTATION_EASING" in tags:
        parts.append(f"rate expectations eased ({facts['fed_change_5d_bps']:+.1f} bps/5d)")
    if "RATE_EXPECTATION_TIGHTENING" in tags:
        parts.append(f"rate expectations tightened ({facts['fed_change_5d_bps']:+.1f} bps/5d)")
    if "USD_STRENGTH" in tags:
        parts.append(f"DXY is stronger ({facts['dxy_change_5d_pct']:+.2f}%/5d)")
    if "USD_WEAKNESS" in tags:
        parts.append(f"DXY is weaker ({facts['dxy_change_5d_pct']:+.2f}%/5d)")
    if "YEN_STRESS" in tags:
        parts.append(f"yen stress is rising ({facts['usdjpy_change_5d_pct']:+.2f}%/5d)")
    if "RISK_OFF_NEWS" in tags:
        parts.append(f"fear/vix imply risk-off ({facts['fear_greed_index']:.0f}, VIX {vix_text})")
    if "RISK_ON_NEWS" in tags:
        parts.append(f"sentiment supports risk-on ({facts['fear_greed_index']:.0f}, VIX {vix_text})")
    if "VOL_PRESSURE_EASING" in tags:
        parts.append(f"volatility pressure eased (VIX {vix_text}, {_safe_float(vix_change):+.2f}%/{vix_change_label})")
    if "VOL_PRESSURE_RISING" in tags:
        parts.append(f"volatility pressure rose (VIX {vix_text}, {_safe_float(vix_change):+.2f}%/{vix_change_label})")
    if "SENTIMENT_COOLING" in tags:
        parts.append(f"fear/greed cooled ({facts['fear_greed_change_5d']:+.1f}/5d)")
    if "SENTIMENT_RELIEF" in tags:
        parts.append(f"fear/greed recovered ({facts['fear_greed_change_5d']:+.1f}/5d)")
    if "GEOPOLITICAL_RISK_EASING" in tags:
        parts.append("geopolitical risk is easing")
    if "GEOPOLITICAL_RISK_RISING" in tags:
        parts.append("geopolitical risk is rising")
    if "LIQUIDITY_EXPANDING" in tags or "LIQUIDITY_CONTRACTING" in tags:
        parts.append(f"stablecoin flow is ${facts['global_stable_flow']:,.0f}")
    if "LABOR_RESILIENT" in tags:
        parts.append("labor data lowers recession risk")
    if "LABOR_WEAKNESS" in tags:
        parts.append("labor data raises recession risk")
    if not parts:
        parts.append("macro inputs are mixed and lack a dominant directional signal")
    return f"{'; '.join(parts)}. Classified as {market_impact} with {impact_horizon} horizon."


def _deterministic_classification(fear_greed: Dict[str, Any], macro_data: Dict[str, Any], news_obj: Dict[str, Any]) -> Dict[str, Any]:
    facts = _base_event_facts(fear_greed, macro_data)
    news_selection = _rank_event_news(news_obj)
    headlines = [event["title"] for event in news_selection["selected"]]
    tags = _key_tags(facts, macro_data, headlines)
    market_impact = _market_impact(tags)
    impact_horizon = _impact_horizon(facts, tags, headlines)
    crypto_relevance = _crypto_relevance(tags, facts)
    policy_stance = _policy_stance(macro_data)
    joined = _headline_text(headlines)
    if _has_us_core_macro_event(joined):
        event_type = "FED_SPEECH"
    elif _has_fed_leadership_event(joined):
        event_type = "FED_LEADERSHIP"
    elif _has_foreign_central_bank_event(joined):
        event_type = "FOREIGN_CENTRAL_BANK"
    elif any(token in joined for token in ["cpi", "payroll", "pce", "inflation", "jobs", "nonfarm"]):
        event_type = "MACRO_DATA_RELEASE"
    elif "yen" in joined or "jpy" in joined:
        event_type = "YEN_MOVE"
    elif "dxy" in joined or "dollar" in joined or "usd" in joined:
        event_type = "USD_MOVE"
    elif headlines:
        event_type = "MACRO_REGIME_UPDATE"
    else:
        event_type = "NOISE"
    news_summary = " | ".join(headlines[:3])
    return {
        "event_type": event_type,
        "policy_stance": policy_stance if headlines else "NOT_APPLICABLE",
        "market_impact": market_impact,
        "impact_horizon": impact_horizon,
        "crypto_relevance": crypto_relevance,
        "key_tags": tags,
        "brief_rationale": _brief_rationale(tags, facts, market_impact, impact_horizon),
        "news_summary": news_summary,
        "classification_basis": facts,
        "key_events": tags,
        "event_facts": facts,
        "news_selection": news_selection,
    }


def _llm_summary_override(classification: Dict[str, Any], headlines: List[str]) -> Dict[str, Any]:
    llm_enabled = os.getenv("ENABLE_MACRO_NEWS_LLM", "").strip() == "1"
    if not headlines:
        merged = dict(classification)
        merged["provenance"] = {
            "generation_mode": "deterministic_only",
            "llm_enabled": llm_enabled,
            "llm_attempted": False,
            "llm_applied": False,
            "llm_override_fields": [],
        }
        return merged
    few_shot_examples = [
        {
            "headline": "Powell says rates may stay higher for longer as inflation remains sticky",
            "expected_output": {
                "news_summary": "Fed rhetoric remains restrictive and adds short-term pressure to risk assets.",
                "brief_rationale": "Higher-for-longer Fed language is hawkish and usually weighs on crypto in the short term.",
                "market_impact": "RISK_OFF",
                "impact_horizon": "INTRADAY",
                "crypto_relevance": "HIGH",
                "key_tags": ["FED_HAWKISH", "RISK_OFF_NEWS"],
            },
        },
        {
            "headline": "US inflation cools faster than expected and traders price earlier rate cuts",
            "expected_output": {
                "news_summary": "Cooling inflation supports easier policy expectations and improves risk appetite.",
                "brief_rationale": "Softer inflation and rate-cut pricing are dovish for macro and generally help crypto sentiment.",
                "market_impact": "RISK_ON",
                "impact_horizon": "SWING",
                "crypto_relevance": "HIGH",
                "key_tags": ["FED_DOVISH", "CPI_COOL", "RISK_ON_NEWS"],
            },
        },
        {
            "headline": "Analysts debate mixed macro outlook ahead of next month policy meeting",
            "expected_output": {
                "news_summary": "The headline is mostly commentary and does not create a clear immediate macro signal.",
                "brief_rationale": "No concrete policy or market shock is described, so this should be treated as mixed or noise.",
                "market_impact": "NO_CLEAR_IMPACT",
                "impact_horizon": "NOISE",
                "crypto_relevance": "LOW",
                "key_tags": ["MACRO_NOISE"],
            },
        },
    ]
    prompt = (
        "Read the provided macro news headlines and structured facts. "
        "Follow this fixed order: identify event type -> classify impact horizon -> classify market impact -> summarize briefly. "
        "Return only valid JSON with keys: news_summary, brief_rationale, market_impact, impact_horizon, "
        "crypto_relevance, key_tags. "
        "Allowed market_impact: RISK_ON, RISK_OFF, MIXED, NO_CLEAR_IMPACT. "
        "Allowed impact_horizon: INTRADAY, SWING, MULTI_DAY, NOISE. "
        "Allowed crypto_relevance: HIGH, MEDIUM, LOW. "
        "Do not invent tags outside the provided candidate tag list.\n\n"
        f"FEW_SHOT_EXAMPLES: {json.dumps(few_shot_examples, ensure_ascii=False)}\n"
        f"HEADLINES: {json.dumps(headlines, ensure_ascii=False)}\n"
        f"CURRENT_CLASSIFICATION: {json.dumps(classification, ensure_ascii=False)}\n"
        f"CANDIDATE_TAGS: {json.dumps(classification['key_tags'], ensure_ascii=False)}"
    )
    result, llm_audit = call_llm_json_with_audit(
        prompt,
        system_prompt=(
            "You are a constrained macro-news classifier. "
            "Use fixed reasoning order: event type -> impact horizon -> market impact -> brief rationale -> summary. "
            "Output only a JSON object."
        ),
        temperature=0.0,
        enable_env_flag="ENABLE_MACRO_NEWS_LLM",
    )
    if not isinstance(result, dict):
        merged = dict(classification)
        merged["provenance"] = {
            "generation_mode": "deterministic_only",
            "llm_enabled": llm_enabled,
            "llm_attempted": llm_enabled,
            "llm_applied": False,
            "llm_override_fields": [],
            "llm_audit": llm_audit,
        }
        return merged

    merged = dict(classification)
    override_fields: List[str] = []
    allow_classification_override = os.getenv("ALLOW_MACRO_LLM_CLASSIFICATION_OVERRIDE", "").strip() == "1"
    overrideable_keys = ["news_summary", "brief_rationale"]
    if allow_classification_override:
        overrideable_keys.extend(["market_impact", "impact_horizon", "crypto_relevance"])
    for key in overrideable_keys:
        value = result.get(key)
        if isinstance(value, str) and value:
            if merged.get(key) != value:
                override_fields.append(key)
            merged[key] = value
    tags = result.get("key_tags")
    if isinstance(tags, list) and tags:
        filtered_tags = [tag for tag in tags if isinstance(tag, str) and tag in classification["key_tags"]]
        if filtered_tags:
            if sorted(set(filtered_tags)) != merged.get("key_tags"):
                override_fields.append("key_tags")
            merged["key_tags"] = sorted(set(filtered_tags))
            merged["key_events"] = merged["key_tags"]
    merged["provenance"] = {
        "generation_mode": "llm_refined" if override_fields else "llm_noop",
        "llm_enabled": llm_enabled,
        "llm_attempted": llm_enabled,
        "llm_applied": bool(override_fields),
        "llm_override_fields": sorted(set(override_fields)),
        "llm_audit": llm_audit,
    }
    return merged


def _macro_view(classification: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_type": classification.get("event_type"),
        "policy_stance": classification.get("policy_stance"),
        "market_impact": classification.get("market_impact"),
        "impact_horizon": classification.get("impact_horizon"),
        "crypto_relevance": classification.get("crypto_relevance"),
        "key_tags": classification.get("key_tags", []),
        "news_summary": classification.get("news_summary"),
        "brief_rationale": classification.get("brief_rationale"),
    }


def _normalize_llm_macro_view(result: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(result, dict):
        return None
    tags = result.get("key_tags")
    return {
        "market_impact": result.get("market_impact"),
        "impact_horizon": result.get("impact_horizon"),
        "crypto_relevance": result.get("crypto_relevance"),
        "key_tags": tags if isinstance(tags, list) else [],
        "news_summary": result.get("news_summary"),
        "brief_rationale": result.get("brief_rationale"),
    }


def _filtered_macro_tags(tags: Any) -> List[str]:
    if not isinstance(tags, list):
        return []
    deduped: List[str] = []
    seen = set()
    for tag in tags:
        if not isinstance(tag, str):
            continue
        normalized = tag.strip().upper()
        if normalized not in ALLOWED_MACRO_TAGS or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _prediction_market_enabled() -> bool:
    return os.getenv("ENABLE_POLYMARKET_SIGNAL", "0").strip().lower() in {"1", "true", "yes"}


def _load_prediction_market_signal() -> Dict[str, Any]:
    if not _prediction_market_enabled():
        return unavailable_signal("disabled")
    try:
        return build_prediction_market_signal(persist=True)
    except Exception as exc:
        return unavailable_signal(f"fetch_or_calculation_failed:{exc.__class__.__name__}")


def _final_macro_decision_fallback(
    classification: Dict[str, Any],
    deterministic_view: Dict[str, Any],
    *,
    source: str,
    reason: str,
    audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged = dict(classification)
    final_decision = {
        "source": source,
        "selected_view": "deterministic",
        "market_impact": merged.get("market_impact"),
        "impact_horizon": merged.get("impact_horizon"),
        "crypto_relevance": merged.get("crypto_relevance"),
        "key_tags": merged.get("key_tags", []),
        "confidence": "LOW",
        "reason": reason,
        "deterministic_view": deterministic_view,
        "llm_view": _normalize_llm_macro_view(
            ((merged.get("provenance") or {}).get("llm_audit") or {}).get("parsed_response")
        ),
        "prediction_market": merged.get("prediction_market"),
        "adjudication_audit": audit,
    }
    merged["final_macro_decision"] = final_decision
    merged["macro_decision_source"] = final_decision["source"]
    return merged


def _llm_final_macro_adjudication(
    classification: Dict[str, Any],
    deterministic_classification: Dict[str, Any],
    headlines: List[str],
) -> Dict[str, Any]:
    llm_enabled = os.getenv("ENABLE_MACRO_NEWS_LLM", "").strip() == "1"
    deterministic_view = _macro_view(deterministic_classification)
    llm_view = _normalize_llm_macro_view(
        ((classification.get("provenance") or {}).get("llm_audit") or {}).get("parsed_response")
    )
    if not llm_enabled or not llm_view:
        return _final_macro_decision_fallback(
            classification,
            deterministic_view,
            source="deterministic",
            reason="LLM adjudication unavailable; using deterministic macro classification.",
        )

    facts = classification.get("event_facts") or classification.get("classification_basis") or {}
    prediction_market = classification.get("prediction_market") or unavailable_signal("not_loaded")
    prompt = (
        "You are the final macro decision adjudicator for a crypto trading system. "
        "Compare the deterministic program conclusion with the first-pass LLM conclusion. "
        "Use the structured facts, including marginal 5-day changes and prediction-market expectation data, to decide which conclusion is better or whether a blended final conclusion is needed. "
        "Treat prediction_market as reference-only market expectation, not as a hard trading signal. "
        "Prefer MIXED or NO_CLEAR_IMPACT when evidence is contradictory or weak. "
        "Do not blindly defer to either side. "
        "Return only valid JSON with keys: selected_view, final_market_impact, final_impact_horizon, "
        "final_crypto_relevance, final_key_tags, confidence, reason. "
        "Allowed selected_view: deterministic, llm, blended. "
        "Allowed final_market_impact: RISK_ON, RISK_OFF, MIXED, NO_CLEAR_IMPACT. "
        "Allowed final_impact_horizon: INTRADAY, SWING, MULTI_DAY, NOISE. "
        "Allowed final_crypto_relevance: HIGH, MEDIUM, LOW. "
        "Allowed final_key_tags must come from ALLOWED_TAGS.\n\n"
        f"HEADLINES: {json.dumps(headlines, ensure_ascii=False)}\n"
        f"STRUCTURED_FACTS: {json.dumps(facts, ensure_ascii=False)}\n"
        f"PREDICTION_MARKET: {json.dumps(prediction_market, ensure_ascii=False)}\n"
        f"DETERMINISTIC_VIEW: {json.dumps(deterministic_view, ensure_ascii=False)}\n"
        f"LLM_VIEW: {json.dumps(llm_view, ensure_ascii=False)}\n"
        f"ALLOWED_TAGS: {json.dumps(sorted(ALLOWED_MACRO_TAGS), ensure_ascii=False)}"
    )
    result, audit = call_llm_json_with_audit(
        prompt,
        system_prompt=(
            "You are a constrained final macro adjudicator. "
            "Choose the best final macro conclusion from deterministic and LLM evidence. "
            "Output only a JSON object."
        ),
        temperature=0.0,
        enable_env_flag="ENABLE_MACRO_NEWS_LLM",
    )
    if not isinstance(result, dict):
        return _final_macro_decision_fallback(
            classification,
            deterministic_view,
            source="deterministic",
            reason="LLM adjudication failed; using deterministic macro classification.",
            audit=audit,
        )

    market_impact = result.get("final_market_impact")
    impact_horizon = result.get("final_impact_horizon")
    crypto_relevance = result.get("final_crypto_relevance")
    if (
        market_impact not in ALLOWED_MARKET_IMPACTS
        or impact_horizon not in ALLOWED_IMPACT_HORIZONS
        or crypto_relevance not in ALLOWED_CRYPTO_RELEVANCE
    ):
        return _final_macro_decision_fallback(
            classification,
            deterministic_view,
            source="deterministic",
            reason="LLM adjudication returned invalid classification fields; using deterministic macro classification.",
            audit=audit,
        )

    final_tags = _filtered_macro_tags(result.get("final_key_tags"))
    if not final_tags:
        final_tags = ["MACRO_NOISE"] if market_impact in {"MIXED", "NO_CLEAR_IMPACT"} else list(classification.get("key_tags", []))

    merged = dict(classification)
    merged["market_impact"] = market_impact
    merged["impact_horizon"] = impact_horizon
    merged["crypto_relevance"] = crypto_relevance
    merged["key_tags"] = final_tags
    merged["key_events"] = final_tags
    if isinstance(result.get("reason"), str) and result["reason"].strip():
        merged["brief_rationale"] = result["reason"].strip()

    selected_view = result.get("selected_view") if result.get("selected_view") in {"deterministic", "llm", "blended"} else "blended"
    confidence = result.get("confidence") if result.get("confidence") in {"LOW", "MEDIUM", "HIGH"} else "MEDIUM"
    final_decision = {
        "source": "llm_adjudicated",
        "selected_view": selected_view,
        "market_impact": market_impact,
        "impact_horizon": impact_horizon,
        "crypto_relevance": crypto_relevance,
        "key_tags": final_tags,
        "confidence": confidence,
        "reason": merged.get("brief_rationale"),
        "deterministic_view": deterministic_view,
        "llm_view": llm_view,
        "prediction_market": prediction_market,
        "adjudication_audit": audit,
    }
    merged["final_macro_decision"] = final_decision
    merged["macro_decision_source"] = final_decision["source"]
    return merged


def build_macro_news_snapshot(whale_analysis: Dict[str, Any]) -> Dict[str, Any]:
    fear_greed = whale_analysis.get("fear_greed", {}) if isinstance(whale_analysis.get("fear_greed"), dict) else {}
    macro_data = whale_analysis.get("macro", {}) if isinstance(whale_analysis.get("macro"), dict) else {}
    news_obj = whale_analysis.get("news", {}) if isinstance(whale_analysis.get("news"), dict) else {}

    deterministic_classification = _deterministic_classification(fear_greed, macro_data, news_obj)
    deterministic_classification["prediction_market"] = _load_prediction_market_signal()
    headlines = [event["title"] for event in (deterministic_classification.get("news_selection") or {}).get("selected", [])]
    classification = _llm_summary_override(deterministic_classification, headlines)
    classification = _llm_final_macro_adjudication(classification, deterministic_classification, headlines)
    facts = classification.get("event_facts", {})

    key_tags = classification.get("key_tags", [])
    market_impact = classification.get("market_impact", "NO_CLEAR_IMPACT")
    macro_impact_score = _market_impact_score(key_tags)
    macro_bias_tier = _macro_bias_tier(macro_impact_score, market_impact)
    macro_policy = _macro_bias_policy(macro_bias_tier)
    event_window = classification.get("event_type") in {"FED_SPEECH", "MACRO_DATA_RELEASE"}

    classification["macro_mode"] = macro_policy["macro_mode"]
    classification["macro_horizon"] = classification.get("impact_horizon", "INTRADAY")
    classification["macro_permission"] = macro_policy["macro_permission"]
    classification["macro_impact_score"] = macro_impact_score
    classification["macro_bias_tier"] = macro_bias_tier
    classification["fear_greed_index"] = facts.get("fear_greed_index", 50.0)
    classification["fear_greed_state"] = facts.get("fear_greed_state", "NEUTRAL")
    classification["fear_greed_change_5d"] = facts.get("fear_greed_change_5d")
    classification["vix_level"] = facts.get("vix_level")
    classification["vix_change_1d_pct"] = facts.get("vix_change_1d_pct")
    classification["vix_change_5d_pct"] = facts.get("vix_change_5d_pct")
    classification["dxy_level"] = facts.get("dxy_level", 0.0)
    classification["dxy_trend"] = _trend_label(_safe_float(facts.get("dxy_change_5d_pct")), positive_label="UP", negative_label="DOWN")
    classification["usdjpy_level"] = facts.get("usdjpy_level", 0.0)
    classification["usdjpy_trend"] = _trend_label(_safe_float(facts.get("usdjpy_change_5d_pct")), positive_label="UP", negative_label="DOWN")
    classification["fed_event_risk"] = "HIGH" if event_window and classification.get("policy_stance") != "NOT_APPLICABLE" else "LOW"
    classification["macro_event_window"] = event_window
    classification["risk_off_score"] = round(macro_policy["risk_off_score"], 2)
    classification["news_headlines"] = headlines
    classification["news_selection"] = deterministic_classification.get("news_selection", classification.get("news_selection"))
    return classification
