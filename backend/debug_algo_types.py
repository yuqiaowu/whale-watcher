
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from okx_executor import OKXExecutor

print("🔍 Debugging OKX Algo Order Types...")
executor = OKXExecutor()

types_to_test = ["conditional", "oco", "trigger", "move_order_stop"]

for t in types_to_test:
    print(f"\n--- Testing ordType={t} ---")
    res = executor._request("GET", f"/api/v5/trade/orders-algo-pending?instType=SWAP&ordType={t}")
    if res.get("code") == "0":
        data = res.get("data", [])
        print(f"✅ Success! Found {len(data)} orders.")
        for o in data:
            print(f"   > ID: {o['algoId']} | Type: {o['ordType']} | SL: {o.get('slTriggerPx')} | TP: {o.get('tpTriggerPx')}")
    else:
        print(f"❌ Failed: {res.get('msg')} (Code: {res.get('code')})")

print("\n--- Testing Multiple ---")
res = executor._request("GET", "/api/v5/trade/orders-algo-pending?instType=SWAP&ordType=conditional,oco")
print(f"Result: {res.get('msg')}")
