import os
import json
from pymongo import MongoClient
from okx_executor import OKXExecutor
from dotenv import load_dotenv

load_dotenv()

# We need to bypass SSL for this local environment to hit MongoDB
uri = os.getenv("MONGODB_URI")
client = MongoClient(uri, serverSelectionTimeoutMS=10000, tlsAllowInvalidCertificates=True)
db = client.whale_watcher

# Initialize Executor in REAL mode for sync
# Since we know the keys are for REAL trading
executor = OKXExecutor()
executor.shadow_mode = False 
executor.trading_mode = "REAL"

print("🔄 Forcing manual sync of trade history to MongoDB...")
try:
    # 1. Fetch from OKX
    res = executor._request("GET", "/api/v5/trade/orders-history?instType=SWAP&state=filled")
    if res["code"] != "0":
        print(f"❌ OKX Error: {res.get('msg')}")
        exit(1)
    
    okx_orders = res.get("data", [])
    print(f"Fetched {len(okx_orders)} orders from OKX.")

    # 2. Get local/DB history
    # Helper to get data with SSL bypass
    cursor = db.trade_history.find({}, {"_id": 0})
    local_history = list(cursor)
    existing_ids = set(item['id'] for item in local_history)
    
    new_records = []
    for ord in okx_orders:
        pnl = float(ord.get("pnl", 0))
        # Logic from okx_executor sync_trade_history
        if pnl == 0 and ord.get("reduceOnly") != "true":
            continue
            
        trade_id = ord["ordId"]
        if trade_id in existing_ids:
            continue

        symbol = ord["instId"].split("-")[0]
        side, posSide = ord["side"], ord["posSide"]
        trade_type = posSide if posSide in ["long", "short"] else side
        avg_px = float(ord.get("avgPx", 0))
        sz = float(ord.get("sz", 0))
        
        # Simple entry price estimation for now
        instId = ord["instId"]
        info = executor.get_instrument_info(instId)
        ctVal = info["ctVal"] if info else 1.0
        entry_px = avg_px - (pnl / (sz * ctVal)) if trade_type == "long" else (pnl / (sz * ctVal)) + avg_px
        
        ts_ms = int(ord.get("uTime", 0))
        from datetime import datetime
        exit_time = datetime.fromtimestamp(ts_ms/1000).strftime("%Y-%m-%d %H:%M:%S")

        record = {
            "id": trade_id,
            "symbol": symbol,
            "type": trade_type,
            "entryPrice": float(f"{entry_px:.4f}"),
            "exitPrice": avg_px,
            "amount": sz,
            "leverage": int(float(ord.get("lever", 1))),
            "pnl": float(f"{pnl:.2f}"),
            "pnlPercent": 0.0, # Will fix if needed
            "entryTime": "---",
            "exitTime": exit_time,
            "reason": "Manual Sync (Fixed)"
        }
        new_records.append(record)
        existing_ids.add(trade_id)

    if new_records:
        print(f"Adding {len(new_records)} new records to MongoDB...")
        # Since the bot might run and overwrite, we should append carefully
        # But for this debug, let's just insert them
        db.trade_history.insert_many(new_records)
        print("✅ Success!")
    else:
        print("No new records found.")

except Exception as e:
    print(f"Error: {e}")
