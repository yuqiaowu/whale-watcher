
import sys
import os
import requests
import json

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_fetcher import gather_news, _fetch_cryptocompare_news, _build_session

def test_fetch():
    print("Testing News Fetcher with LANG=ZH...")
    session = _build_session()
    
    # 1. Test CryptoCompare ZH specifically
    print("\n--- 1. Testing CryptoCompare (ZH) ---")
    try:
        cc_news = _fetch_cryptocompare_news(session, lang="ZH")
        if cc_news and "items" in cc_news:
            print(f"✅ CryptoCompare returned {len(cc_news['items'])} items.")
            for item in cc_news['items'][:3]:
                print(f"   - {item['title']} ({item.get('sentiment')})")
        else:
            print("❌ CryptoCompare returned empty or invalid.")
            print(f"Raw Response: {cc_news}")
    except Exception as e:
        print(f"❌ CryptoCompare Exception: {e}")

    # 2. Test Full Gather News
    print("\n--- 2. Testing Full gather_news() ---")
    try:
        all_news = gather_news(session)
        print(f"Full Result Keys: {all_news.keys()}")
        if not all_news:
            print("❌ gather_news returned Empty!")
        else:
            for cat, data in all_news.items():
                items = data.get("items", [])
                print(f"   Category '{cat}': {len(items)} items")
                if items:
                    print(f"     Example: {items[0]['title']}")
    except Exception as e:
        print(f"❌ gather_news Exception: {e}")

if __name__ == "__main__":
    test_fetch()
