import json
from typing import Any, Dict, List

from llm_client import call_llm_json


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


def _base_event_facts(fear_greed: Dict[str, Any], macro_data: Dict[str, Any]) -> Dict[str, Any]:
    fed = macro_data.get("fed_futures", {}) or {}
    japan = macro_data.get("japan_macro", {}) or {}
    liquidity = macro_data.get("liquidity_monitor", {}) or {}
    dxy = liquidity.get("dxy", {}) or {}
    vix = liquidity.get("vix", {}) or {}
    us10y = liquidity.get("us10y", {}) or {}
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
        "global_stable_flow": _safe_float(macro_data.get("global_stable_flow")),
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
    if any(token in text for token in ["restrictive", "高位", "hawk"]) or change_bps > 2:
        return "HAWKISH"
    if any(token in text for token in ["easing", "dovish", "宽松"]) or change_bps < -5:
        return "DOVISH"
    return "NEUTRAL"


def _key_tags(facts: Dict[str, Any], macro_data: Dict[str, Any], headlines: List[str]) -> List[str]:
    tags: List[str] = []
    stance = _policy_stance(macro_data)
    if stance == "HAWKISH":
        tags.append("FED_HAWKISH")
    elif stance == "DOVISH":
        tags.append("FED_DOVISH")

    if facts["dxy_change_5d_pct"] >= 0.2:
        tags.append("USD_STRENGTH")
    elif facts["dxy_change_5d_pct"] <= -0.2:
        tags.append("USD_WEAKNESS")

    if facts["usdjpy_change_5d_pct"] <= -0.4:
        tags.append("YEN_STRESS")
    elif facts["usdjpy_change_5d_pct"] >= 0.4:
        tags.append("YEN_RELIEF")

    if facts["fear_greed_index"] <= 35 or facts["vix_level"] >= 24 or facts["vix_change_5d_pct"] >= 8:
        tags.append("RISK_OFF_NEWS")
    elif facts["fear_greed_index"] >= 65 and facts["vix_level"] < 18:
        tags.append("RISK_ON_NEWS")

    if facts["global_stable_flow"] >= 50_000_000:
        tags.append("LIQUIDITY_EXPANDING")
    elif facts["global_stable_flow"] <= -50_000_000:
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
    risk_off = {"FED_HAWKISH", "USD_STRENGTH", "YEN_STRESS", "RISK_OFF_NEWS", "LIQUIDITY_CONTRACTING", "CPI_HOT"}
    risk_on = {"FED_DOVISH", "USD_WEAKNESS", "YEN_RELIEF", "RISK_ON_NEWS", "LIQUIDITY_EXPANDING", "CPI_COOL"}
    off = len(risk_off.intersection(tags))
    on = len(risk_on.intersection(tags))
    if off and on:
        return "MIXED"
    if off:
        return "RISK_OFF"
    if on:
        return "RISK_ON"
    return "NO_CLEAR_IMPACT"


def _impact_horizon(facts: Dict[str, Any], tags: List[str], headlines: List[str]) -> str:
    joined = " ".join(headlines).lower()
    if any(token in joined for token in ["fomc", "powell", "cpi", "payroll", "pce"]) or "FED_HAWKISH" in tags or "FED_DOVISH" in tags:
        return "INTRADAY"
    if abs(facts["dxy_change_5d_pct"]) >= 0.6 or abs(facts["usdjpy_change_5d_pct"]) >= 0.6 or abs(facts["global_stable_flow"]) >= 200_000_000:
        return "SWING"
    if "MACRO_NOISE" in tags:
        return "NOISE"
    return "SWING"


def _crypto_relevance(tags: List[str], facts: Dict[str, Any]) -> str:
    if any(tag in tags for tag in ["FED_HAWKISH", "FED_DOVISH", "USD_STRENGTH", "USD_WEAKNESS", "YEN_STRESS", "RISK_OFF_NEWS", "RISK_ON_NEWS"]):
        return "HIGH"
    if abs(facts["global_stable_flow"]) >= 100_000_000:
        return "HIGH"
    if any(tag in tags for tag in ["LIQUIDITY_EXPANDING", "LIQUIDITY_CONTRACTING", "MACRO_NOISE"]):
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
    joined = " ".join(headlines).lower()
    if any(token in joined for token in ["powell", "fomc", "fed", "rate", "cut", "hike"]):
        event_type = "FED_SPEECH"
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
    if not headlines:
        return classification
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
    result = call_llm_json(
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
        return classification
    merged = dict(classification)
    for key in ["news_summary", "brief_rationale", "market_impact", "impact_horizon", "crypto_relevance"]:
        value = result.get(key)
        if isinstance(value, str) and value:
            merged[key] = value
    tags = result.get("key_tags")
    if isinstance(tags, list) and tags:
        filtered_tags = [tag for tag in tags if isinstance(tag, str) and tag in classification["key_tags"]]
        if filtered_tags:
            merged["key_tags"] = sorted(set(filtered_tags))
            merged["key_events"] = merged["key_tags"]
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
