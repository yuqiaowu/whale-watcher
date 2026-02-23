
import os
import json
import requests
from datetime import datetime, timedelta
from db_client import db

def fix_btc_prices():
    print("🛠️ Starting Nav History Fix...")
    history = db.get_data("nav_history", [])
    if not history:
        print("❌ No history found in DB.")
        return

    # Fetch recent BTC prices as fallback
    # OKX Public Candles for BTC-USDT-SWAP 4H
    print("📡 Fetching historical BTC prices from OKX...")
    url = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=4H&limit=50"
    res = requests.get(url, timeout=10)
    price_map = {} # timestamp (rounded to 4h) -> price
    
    if res.status_code == 200:
        data = res.json().get("data", [])
        for candle in data:
            ts = int(candle[0])
            dt = datetime.fromtimestamp(ts / 1000)
            # Round down to 4H mark for matching
            rounded_dt = dt.replace(minute=0, second=0, microsecond=0)
            price_map[rounded_dt.strftime("%Y-%m-%dT%H")] = float(candle[4]) # close price
            
    # Also get current price
    current_btc = 0
    try:
        ticker = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP", timeout=5).json()
        current_btc = float(ticker['data'][0]['last'])
        print(f"✅ Current BTC Price: ${current_btc}")
    except:
        pass

    last_valid_price = current_btc
    
    # Sort history newest first for filling
    history.sort(key=lambda x: x["timestamp"], reverse=True)

    updated_count = 0
    for entry in history:
        price = entry.get("btc_price", 0)
        if price <= 0:
            ts_str = entry["timestamp"]
            try:
                dt = datetime.fromisoformat(ts_str.split('.')[0])
                # 1. Try exact hour match
                match_key = dt.strftime("%Y-%m-%dT%H")
                
                found = False
                for i in range(5): # Check last 5 hours for a candle
                    check_dt = dt - timedelta(hours=i)
                    check_key = check_dt.strftime("%Y-%m-%dT%H")
                    if check_key in price_map:
                        entry["btc_price"] = price_map[check_key]
                        last_valid_price = entry["btc_price"]
                        updated_count += 1
                        found = True
                        break
                
                if not found and last_valid_price > 0:
                    entry["btc_price"] = last_valid_price
                    updated_count += 1
            except Exception as e:
                print(f"⚠️ Error processing {ts_str}: {e}")
        else:
            last_valid_price = price

    if updated_count > 0:
        # Sort back to chronological
        history.sort(key=lambda x: x["timestamp"])
        db.save_data("nav_history", history)
        print(f"✅ Successfully updated {updated_count} history points with BTC prices.")
    else:
        print("ℹ️ No points needed updating or no matches found.")

if __name__ == "__main__":
    fix_btc_prices()
