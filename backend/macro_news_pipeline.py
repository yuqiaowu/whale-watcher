import json
import os
import re
from typing import Any, Dict, List

from llm_client import call_llm_json_with_audit


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _event_headlines(news_obj: Dict[str, Any], limit: int = 5) -> List[str]:
    headlines: List[str] = []
    for bucket_name in ["macro", "calendar", "general"]:
        bucket = news_obj.get(bucket_name, {})
        if not isinstance(bucket, dict):
            continue
        for item in bucket.get("items", [])[:limit]:
            title = str(item.get("title") or "").strip()
            if title:
                headlines.append(title)
    deduped: List[str] = []
    seen = set()
    for headline in headlines:
        normalized = headline.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(headline)
    return deduped[:limit]


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
    us_labor_context = any(token in text for token in [
        "nonfarm",
        "non-farm",
        "nfp",
        "us payroll",
        "u.s. payroll",
        "payrolls report",
        "jobs report",
    ])
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
        "fed_implied_rate": _safe_float(fed.get("implied_rate")),
        "fed_change_5d_bps": _safe_float(fed.get("change_5d_bps")),
        "usdjpy_level": _safe_float(japan.get("price")),
        "usdjpy_change_5d_pct": _safe_float(japan.get("change_5d_pct")),
        "dxy_level": _safe_float(dxy.get("price")),
        "dxy_change_5d_pct": _safe_float(dxy.get("change_5d_pct")),
        "vix_level": _safe_float(vix.get("price")),
        "vix_change_5d_pct": _safe_float(vix.get("change_5d_pct")),
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
        ], default=4.0),
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
    stable_flow_thresholds = _stable_flow_thresholds(macro_data)
    if stance == "HAWKISH":
        tags.append("FED_HAWKISH")
    elif stance == "DOVISH":
        tags.append("FED_DOVISH")

    if facts["dxy_change_5d_pct"] >= dxy_threshold:
        tags.append("USD_STRENGTH")
    elif facts["dxy_change_5d_pct"] <= -dxy_threshold:
        tags.append("USD_WEAKNESS")

    if facts["usdjpy_change_5d_pct"] <= -yen_threshold:
        tags.append("YEN_STRESS")
    elif facts["usdjpy_change_5d_pct"] >= yen_threshold:
        tags.append("YEN_RELIEF")

    if facts["fear_greed_index"] <= 35 or facts["vix_level"] >= 24 or facts["vix_change_5d_pct"] >= 8:
        tags.append("RISK_OFF_NEWS")
    elif facts["fear_greed_index"] >= 65 and facts["vix_level"] < 18:
        tags.append("RISK_ON_NEWS")

    if facts["global_stable_flow"] >= stable_flow_thresholds["tag"]:
        tags.append("LIQUIDITY_EXPANDING")
    elif facts["global_stable_flow"] <= -stable_flow_thresholds["tag"]:
        tags.append("LIQUIDITY_CONTRACTING")

    joined = " ".join(headlines).lower()
    if "cpi" in joined and any(token in joined for token in ["hot", "sticky", "higher-than-expected", "inflation"]):
        tags.append("CPI_HOT")
    elif "cpi" in joined and any(token in joined for token in ["cool", "below expectations", "softer"]):
        tags.append("CPI_COOL")

    if not tags:
        tags.append("MACRO_NOISE")
    return sorted(set(tags))


def _market_impact(tags: List[str]) -> str:
    weights = {
        "FED_HAWKISH": -5,
        "FED_DOVISH": 5,
        "USD_STRENGTH": -2,
        "USD_WEAKNESS": 2,
        "YEN_STRESS": -2,
        "YEN_RELIEF": 2,
        "RISK_OFF_NEWS": -3,
        "RISK_ON_NEWS": 3,
        "LIQUIDITY_CONTRACTING": -4,
        "LIQUIDITY_EXPANDING": 4,
        "CPI_HOT": -4,
        "CPI_COOL": 4,
    }
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
    if "FED_HAWKISH" in tags:
        parts.append("Fed pricing remains restrictive")
    if "FED_DOVISH" in tags:
        parts.append("Fed pricing is easing")
    if "USD_STRENGTH" in tags:
        parts.append(f"DXY is stronger ({facts['dxy_change_5d_pct']:+.2f}%/5d)")
    if "USD_WEAKNESS" in tags:
        parts.append(f"DXY is weaker ({facts['dxy_change_5d_pct']:+.2f}%/5d)")
    if "YEN_STRESS" in tags:
        parts.append(f"yen stress is rising ({facts['usdjpy_change_5d_pct']:+.2f}%/5d)")
    if "RISK_OFF_NEWS" in tags:
        parts.append(f"fear/vix imply risk-off ({facts['fear_greed_index']:.0f}, VIX {facts['vix_level']:.2f})")
    if "RISK_ON_NEWS" in tags:
        parts.append(f"sentiment supports risk-on ({facts['fear_greed_index']:.0f}, VIX {facts['vix_level']:.2f})")
    if "LIQUIDITY_EXPANDING" in tags or "LIQUIDITY_CONTRACTING" in tags:
        parts.append(f"stablecoin flow is ${facts['global_stable_flow']:,.0f}")
    if not parts:
        parts.append("macro inputs are mixed and lack a dominant directional signal")
    return f"{'; '.join(parts)}. Classified as {market_impact} with {impact_horizon} horizon."


def _deterministic_classification(fear_greed: Dict[str, Any], macro_data: Dict[str, Any], news_obj: Dict[str, Any]) -> Dict[str, Any]:
    facts = _base_event_facts(fear_greed, macro_data)
    headlines = _event_headlines(news_obj)
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


def build_macro_news_snapshot(whale_analysis: Dict[str, Any]) -> Dict[str, Any]:
    fear_greed = whale_analysis.get("fear_greed", {}) if isinstance(whale_analysis.get("fear_greed"), dict) else {}
    macro_data = whale_analysis.get("macro", {}) if isinstance(whale_analysis.get("macro"), dict) else {}
    news_obj = whale_analysis.get("news", {}) if isinstance(whale_analysis.get("news"), dict) else {}

    classification = _deterministic_classification(fear_greed, macro_data, news_obj)
    headlines = _event_headlines(news_obj)
    classification = _llm_summary_override(classification, headlines)
    facts = classification.get("event_facts", {})

    market_impact = classification.get("market_impact", "NO_CLEAR_IMPACT")
    if market_impact == "RISK_OFF":
        macro_mode = "RISK_OFF"
        macro_permission = "ALLOW_SHORT"
    elif market_impact == "RISK_ON":
        macro_mode = "RISK_ON"
        macro_permission = "ALLOW_LONG"
    elif "FED_HAWKISH" in classification.get("key_tags", []) or "RISK_OFF_NEWS" in classification.get("key_tags", []):
        macro_mode = "RISK_OFF"
        macro_permission = "ALLOW_SHORT"
    elif "FED_DOVISH" in classification.get("key_tags", []) or "RISK_ON_NEWS" in classification.get("key_tags", []):
        macro_mode = "RISK_ON"
        macro_permission = "ALLOW_LONG"
    else:
        macro_mode = "MIXED"
        macro_permission = "ALLOW_BOTH"

    event_window = classification.get("event_type") in {"FED_SPEECH", "MACRO_DATA_RELEASE"}
    risk_off_score = 0.5
    if market_impact == "RISK_OFF":
        risk_off_score = 0.8
    elif market_impact == "RISK_ON":
        risk_off_score = 0.2
    elif market_impact == "MIXED":
        risk_off_score = 0.5

    classification["macro_mode"] = macro_mode
    classification["macro_horizon"] = classification.get("impact_horizon", "INTRADAY")
    classification["macro_permission"] = macro_permission
    classification["fear_greed_index"] = facts.get("fear_greed_index", 50.0)
    classification["fear_greed_state"] = facts.get("fear_greed_state", "NEUTRAL")
    classification["dxy_level"] = facts.get("dxy_level", 0.0)
    classification["dxy_trend"] = _trend_label(_safe_float(facts.get("dxy_change_5d_pct")), positive_label="UP", negative_label="DOWN")
    classification["usdjpy_level"] = facts.get("usdjpy_level", 0.0)
    classification["usdjpy_trend"] = _trend_label(_safe_float(facts.get("usdjpy_change_5d_pct")), positive_label="UP", negative_label="DOWN")
    classification["fed_event_risk"] = "HIGH" if event_window and classification.get("policy_stance") != "NOT_APPLICABLE" else "LOW"
    classification["macro_event_window"] = event_window
    classification["risk_off_score"] = round(risk_off_score, 2)
    classification["news_headlines"] = headlines
    return classification
