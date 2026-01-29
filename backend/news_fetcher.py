from __future__ import annotations

import json
import os
import re
import requests
import pandas as pd
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import yfinance as yf

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))

def _resolve_proxy() -> Optional[str]:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        return proxy.strip() or None
    use_local_proxy = os.environ.get("USE_LOCAL_PROXY", "0").lower()
    if use_local_proxy in {"1", "true", "yes"}:
        return "http://127.0.0.1:7890"
    return None


def _build_session() -> requests.Session:
    session = requests.Session()
    proxy = _resolve_proxy()
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update(
        {
            "User-Agent": os.environ.get(
                "HTTP_USER_AGENT",
                "CodexDataFetcher/1.0 (+https://defillama.com)",
            )
        }
    )
    return session


def _fetch_json(
    session: requests.Session, url: str, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    try:
        resp = session.get(url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return {"error": str(exc), "url": url, "params": params}
    try:
        return resp.json()
    except ValueError:
        preview = resp.text[:400]
        return {"error": "invalid_json", "url": url, "params": params, "preview": preview}


def _fetch_rss_items(session: requests.Session, url: str, limit: int = 5) -> Dict[str, Any]:
    try:
        resp = session.get(url, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return {"error": str(exc), "url": url}
    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as exc:
        preview = resp.text[:400]
        return {"error": f"rss_parse_error: {exc}", "url": url, "preview": preview}

    items: List[Dict[str, Any]] = []
    # Handle standard RSS <item> and Atom <entry> (basic support)
    # This simple parser focuses on RSS 2.0 <item> inside <channel>
    # but the original code used .//item which finds all items anywhere.
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()
        summary = (item.findtext("description") or "").strip()
        items.append(
            {
                "title": title,
                "link": link,
                "published": pub_date,
                "summary": summary,
            }
        )
    return {"items": items, "source": url}


def _fetch_cryptocompare_news(
    session: requests.Session,
    categories: str = "BTC,ETH,SOL,BNB,DOGE",
    lang: str = "EN",
    limit: int = 50,
) -> Dict[str, Any]:
    params = {
        "categories": categories,
        "lang": lang.upper(),
        "sortOrder": "latest",
    }
    data = _fetch_json(session, "https://min-api.cryptocompare.com/data/v2/news/", params)
    if isinstance(data, dict) and data.get("error"):
        return {"error": data.get("error"), "url": "cryptocompare", "params": params}
    items: List[Dict[str, Any]] = []
    entries = []
    if isinstance(data, dict):
        if isinstance(data.get("Data"), list):
            entries = data.get("Data")
        elif isinstance(data.get("data"), list):
            entries = data.get("data")
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("published_on")
        if ts:
            try:
                published = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
            except (ValueError, TypeError):
                published = ts
        else:
            published = None
        items.append(
            {
                "title": entry.get("title"),
                "link": entry.get("url"),
                "published": published,
                "source": entry.get("source"),
                "tags": entry.get("categories"),
                "summary": entry.get("body"),
            }
        )
    if not items:
        return {
            "items": items,
            "source": "CryptoCompare",
            "params": params,
            "note": "No news items returned; may be rate limited or category empty.",
            "raw": data,
        }
    return {"items": items, "source": "CryptoCompare", "params": params}


def _fetch_forex_factory(session: requests.Session, url: str) -> Dict[str, Any]:
    try:
        resp = session.get(url, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        # Parse XML manually since it's not standard RSS
        root = ElementTree.fromstring(resp.content)
        items = []
        for event in root.findall("event"):
            try:
                title = event.find("title").text or ""
                country = event.find("country").text or "Global"
                date_str = event.find("date").text or ""
                time_str = event.find("time").text or ""
                impact = event.find("impact").text or "Low"
                
                # Filter out Low impact to reduce noise? User wants "Fed", "CPI" etc.
                # Let's keep all and let keywords filter it.
                
                full_title = f"[{country}] {title} ({impact})"
                link = event.find("url").text if event.find("url") is not None else url
                
                # Construct timestamp for sorting
                # Format in XML: 12-06-2025
                # We want YYYY-MM-DD for string sort
                try:
                    mm, dd, yyyy = date_str.split("-")
                    sortable_date = f"{yyyy}-{mm}-{dd} {time_str}"
                except:
                    sortable_date = f"{date_str} {time_str}"

                items.append({
                    "title": full_title,
                    "link": link,
                    "published": sortable_date,
                    "summary": f"Impact: {impact}, Forecast: {event.find('forecast').text}, Previous: {event.find('previous').text}"
                })
            except Exception:
                continue
                
        return {"items": items}
    except Exception as e:
        return {"error": str(e), "url": url}


def gather_news(session: requests.Session = None) -> Dict[str, Any]:
    """
    Fetches news from various sources (RSS, CryptoCompare, ForexFactory) and filters by keywords.
    If no session is provided, a new one is created.
    """
    if session is None:
        session = _build_session()

    feeds = {
        "bitcoin": [
            "https://www.coindesk.com/tag/bitcoin/rss/",
            "https://cointelegraph.com/rss/tag/bitcoin",
        ],
        "ethereum": [
            "https://www.coindesk.com/tag/ethereum/rss/",
            "https://cointelegraph.com/rss/tag/ethereum",
        ],
        "general": [
            "https://decrypt.co/feed",
            "https://news.bitcoin.com/feed/",
        ],
        "macro": [
            "https://www.cnbc.com/id/100003114/device/rss/rss.html", # Top News (Fed, Economy)
            "https://finance.yahoo.com/news/rssindex", # Yahoo Finance Top
        ],
        "calendar": [
            "https://nfs.faireconomy.media/ff_calendar_thisweek.xml", # ForexFactory Calendar
        ]
    }
    
    # Keywords to filter MACRO news (English) - Regex optimized
    # 关键词：加密货币，比特币，以太坊，监管，美联储，加息，降息，关税，CPI, PCE
    # 使用单词边界 \b 防止匹配到 unrelated words (e.g. "sec" in "secondary")
    MACRO_KEYWORDS = [
        r"\bcrypto", r"\bbitcoin", r"\bbtc\b", r"\bethereum", r"\beth\b", r"\bdoge", 
        r"\bregulation", r"\bsec\b", r"\bgensler",
        r"\bfed\b", r"\bfederal reserve", r"\bpowell", r"\bfomc", 
        r"\brate", r"\binterest", r"\bhike", r"\bcut",
        r"\binflation", r"\bcpi\b", r"\bpce\b", r"\bppi\b", 
        r"\bjob", r"\bpayroll", r"\bunemployment",
        r"\btariff", r"\btax", r"\beconomy", r"\bbank", r"\bdefi\b", r"\bstablecoin", 
        r"\bliquidity", r"\btreasury"
    ]
    
    # Compile regex for performance
    keyword_pattern = re.compile("|".join(MACRO_KEYWORDS), re.IGNORECASE)

    news: Dict[str, Any] = {}
    crypto_compare_cache = _fetch_cryptocompare_news(session, categories="BTC,ETH", lang="EN", limit=30)
    
    for topic, urls in feeds.items():
        topic_items: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        
        # Increase fetch limit for macro/calendar to catch more candidates before filtering
        fetch_limit = 30 if topic in ["macro", "calendar"] else 5
        
        for url in urls:
            if "faireconomy.media" in url:
                result = _fetch_forex_factory(session, url)
            else:
                result = _fetch_rss_items(session, url, limit=fetch_limit)
                
            if "items" in result:
                fetched_items = result["items"]
                
                # Apply filtering for macro AND calendar topics
                if topic in ["macro", "calendar"]:
                    filtered_items = []
                    for item in fetched_items:
                        text_to_check = (item.get("title", "") + " " + item.get("summary", "")).lower()
                        if keyword_pattern.search(text_to_check):
                            filtered_items.append(item)
                    topic_items.extend(filtered_items)
                else:
                    topic_items.extend(fetched_items)
            else:
                errors.append(result)
                
        topic_items.sort(key=lambda x: x.get("published", ""), reverse=True)
        
        if topic == "general" and "items" in crypto_compare_cache:
            topic_items.extend(crypto_compare_cache["items"])
        
        topic_items.sort(key=lambda x: x.get("published", ""), reverse=True)
        
        note = None
        if not topic_items and errors:
            note = "所有新闻源均拉取失败，可能需要代理或额外认证。"
        elif topic in ["macro", "calendar"] and not topic_items:
             note = "拉取成功但未匹配到相关关键词的新闻。"

        extra_errors: List[Dict[str, Any]] = []
        if topic == "general" and crypto_compare_cache.get("error"):
            extra_errors.append(crypto_compare_cache)
            
        # Set limit based on topic
        final_limit = 5 if topic == "calendar" else 15
            
        news[topic] = {
            "items": topic_items[:final_limit], 
            "errors": errors + extra_errors,
            "note": note,
        }
        
    if "items" in crypto_compare_cache and crypto_compare_cache["items"]:
        news["cryptocompare"] = crypto_compare_cache
    else:
        news["cryptocompare"] = crypto_compare_cache
    return news

if __name__ == "__main__":
    print("Fetching news...")
    session = _build_session()
    all_news = gather_news(session)
    
    for category, data in all_news.items():
        print(f"\n=== {category.upper()} ===")
        if data.get("note"):
            print(f"Note: {data['note']}")
        
        items = data.get("items", [])
        if not items:
            print("No items.")
            continue
            
        for i, item in enumerate(items[:5]):
            print(f"{i+1}. {item.get('title')}")
            print(f"   Date: {item.get('published')}")
            print(f"   Link: {item.get('link')}")

def fetch_fed_futures() -> Dict[str, Any]:
    """
    Fetch 30-Day Fed Fund Futures (ZQ=F) to estimate market-implied rate.
    Returns implied rate and 5-day change trend.
    """
    try:
        # ZQ=F is the continuous contract for 30-Day Fed Funds
        ticker = yf.Ticker("ZQ=F")
        hist = ticker.history(period="5d")
        
        if hist.empty:
            return {"error": "No data found for ZQ=F"}
            
        # Get latest close
        latest_price = hist["Close"].iloc[-1]
        implied_rate = 100 - latest_price
        
        result = {
            "price": round(latest_price, 3),
            "implied_rate": round(implied_rate, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trend": "Neutral"
        }
        
        # Calculate 5-day change if enough data
        if len(hist) >= 2:
            prev_price = hist["Close"].iloc[0] # 5 days ago (approx)
            prev_rate = 100 - prev_price
            change_bps = (implied_rate - prev_rate) * 100
            
            result["change_5d_bps"] = round(change_bps, 1)
            
            # Determine trend
            if change_bps < -5:
                result["trend"] = "Dovish (Rate expectations dropping)"
            elif change_bps > 5:
                result["trend"] = "Hawkish (Rate expectations rising)"
            else:
                result["trend"] = "Neutral (Stable expectations)"
        
        # Determine Zone (Heuristic)
        if implied_rate > 3.0:
            result["zone"] = "Restrictive (High)"
        elif implied_rate < 2.0:
            result["zone"] = "Accommodative (Low)"
        else:
            result["zone"] = "Neutral"
            
        return result
        
    except Exception as e:
        return {"error": str(e)}

def fetch_japan_context() -> Dict[str, Any]:
    """
    Fetch USD/JPY (USDJPY=X) to estimate Japan Macro / Carry Trade context.
    Returns price, trend (Yen Strength/Weakness), and zone.
    """
    try:
        ticker = yf.Ticker("USDJPY=X")
        hist = ticker.history(period="5d")
        
        if hist.empty:
            return {"error": "No data found for USDJPY=X"}
            
        latest_price = hist["Close"].iloc[-1]
        
        result = {
            "price": round(latest_price, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trend": "Neutral"
        }
        
        # Calculate 5-day change
        if len(hist) >= 2:
            prev_price = hist["Close"].iloc[0]
            change_pct = ((latest_price - prev_price) / prev_price) * 100
            result["change_5d_pct"] = round(change_pct, 2)
            
            # Trend Logic (USD/JPY)
            # Price DROP = Yen STRENGTH = Hawkish/Risk Off (Carry Trade Unwind)
            # Price RISE = Yen WEAKNESS = Dovish/Risk On
            if change_pct < -0.5:
                result["trend"] = "Yen Strength (Risk Off)"
            elif change_pct > 0.5:
                result["trend"] = "Yen Weakness (Risk On)"
            else:
                result["trend"] = "Neutral"
                
        # Zone Logic
        if latest_price > 150:
            result["zone"] = "Weak Yen (Intervention Risk)"
        elif latest_price < 130:
            result["zone"] = "Strong Yen"
        else:
            result["zone"] = "Neutral"
            
        return result

    except Exception as e:
        return {"error": str(e)}

def fetch_liquidity_monitor() -> Dict[str, Any]:
    """
    Fetch Global Liquidity Indicators: DXY, US10Y, VIX.
    Returns prices, changes, and risk signals.
    """
    try:
        # DX-Y.NYB = Dollar Index, ^TNX = US 10Y Yield, ^VIX = Volatility Index
        tickers = {
            "dxy": {"symbol": "DX-Y.NYB", "name": "Dollar Index"},
            "us10y": {"symbol": "^TNX", "name": "US 10Y Yield"},
            "vix": {"symbol": "^VIX", "name": "VIX Index"}
        }
        
        result = {}
        
        for key, info in tickers.items():
            try:
                symbol = info["symbol"]
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                
                if hist.empty:
                    result[key] = None
                    continue
                
                latest = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[0]
                change_pct = ((latest - prev) / prev) * 100
                
                item = {
                    "price": round(latest, 2),
                    "change_5d_pct": round(change_pct, 2),
                    "trend": "Neutral"
                }
                
                # Risk Logic
                if key == "dxy":
                    if change_pct > 0.1: item["trend"] = "Stronger (Risk Off)"
                    elif change_pct < -0.1: item["trend"] = "Weaker (Risk On)"
                    else: item["trend"] = "Neutral"
                elif key == "us10y":
                    # Zone Logic
                    zone = "Neutral"
                    if latest > 4.5: zone = "Critical High"
                    elif latest > 4.2: zone = "High"
                    elif latest < 3.8: zone = "Low"
                    
                    # Movement Logic
                    move = ""
                    if change_pct > 0.5: move = "Rising"
                    elif change_pct < -0.5: move = "Falling"
                    
                    # Combine
                    item["trend"] = f"{zone} {move}".strip()
                elif key == "vix":
                    # Zone Logic
                    zone = "Normal" # Renamed from Neutral for clarity
                    if latest > 30: zone = "Extreme Panic"
                    elif latest > 20: zone = "High Fear"
                    elif latest < 15: zone = "Greed"
                    
                    # Movement Logic
                    move = ""
                    if change_pct > 2.0: move = "Rising"
                    elif change_pct < -2.0: move = "Subsiding"
                    
                    # Combine
                    item["trend"] = f"{zone} {move}".strip()
                
                result[key] = item
                
            except Exception as e:
                print(f"⚠️ Failed to fetch {key}: {e}")
                result[key] = None

        return _clean_nan(result)

    except Exception as e:
        return {"error": str(e)}

def _clean_nan(obj):
    """Recursively replace NaN with None for JSON compatibility."""
    if isinstance(obj, float):
        import math
        if math.isnan(obj):
            return None
    elif isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    return obj
