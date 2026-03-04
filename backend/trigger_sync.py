import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv
from okx_executor import OKXExecutor

load_dotenv()

# Force REAL or DEMO mode to enable sync
os.environ["TRADING_MODE"] = "DEMO" # Or REAL if that's what the user uses. 
# Looking at the history, PnLs are small, so maybe DEMO? 
# But user said "线上开了一个eth", usually implies real.
# Let's try to detect if we have real/demo API keys.

executor = OKXExecutor()
# Override shadow_mode to ensure sync runs
executor.shadow_mode = False 

print(f"--- Syncing History (Mode: {executor.trading_mode}) ---")
executor.sync_trade_history()

print("\n--- Verifying Trade History in DB ---")
from db_client import db
history = list(db.trade_history.find().sort("exitTime", -1).limit(5))
for h in history:
    print(f"[{h.get('exitTime')}] {h.get('symbol')} {h.get('type')} PnL: {h.get('pnl')} ID: {h.get('id')}")
