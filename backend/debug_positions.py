
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from okx_executor import OKXExecutor

print("🔍 Debugging OKX Algo Orders for Position Display...")

executor = OKXExecutor()

if executor.shadow_mode:
    print("⚠️ Executor is in SHADOW MODE. Algo orders are not fetched from OKX.")
    # In shadow mode, check if state has SL/TP stored.
    state = executor._load_shadow_state()
    print("Shadow State Positions:")
    for p in state["positions"]:
        print(f" - {p['symbol']}: SL={p.get('stop_loss')}, TP={p.get('take_profit')}")
else:
    print("✅ Executor is in CONNECTED MODE (Demo/Real). Fetching live data...")
    
    # 1. Get Positions
    print("\n--- POSITIONS (Raw) ---")
    pos_res = executor._request("GET", "/api/v5/account/positions?instType=SWAP")
    if pos_res.get("code") == "0":
        for p in pos_res["data"]:
            print(f"Position: {p['instId']} | Side: {p['posSide']} | Size: {p['pos']}")
    else:
        print(f"Error fetching positions: {pos_res}")

    # 2. Get Algo Orders (Pending)
    print("\n--- ALGO ORDERS (Pending) ---")
    # Try the same query as in get_all_positions
    algo_query = "/api/v5/trade/orders-algo-pending?instType=SWAP&ordType=conditional,move_order_stop,oco,trigger"
    algo_res = executor._request("GET", algo_query)
    
    if algo_res.get("code") == "0":
        data = algo_res.get("data", [])
        print(f"Found {len(data)} pending algo orders.")
        for order in data:
            print(f"Order: {order['instId']} | Type: {order['ordType']} | SL: {order.get('slTriggerPx')} | TP: {order.get('tpTriggerPx')}")
    else:
        print(f"Error fetching algo orders: {algo_res}")

    # 3. Test get_all_positions() output
    print("\n--- MAPPED OUTPUT (What Frontend Sees) ---")
    final_output = executor.get_all_positions()
    for item in final_output:
        print(f"Symbol: {item['symbol']} | StopLoss: {item['stopLoss']} | TakeProfit: {item['takeProfit']}")
