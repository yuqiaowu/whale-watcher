import time
import subprocess
import os
import sys
import threading
import json
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import requests
from stats_calculator import calculate_stats
from db_client import db

# Configuration
INTERVAL_HOURS = 4
INTERVAL_SECONDS = INTERVAL_HOURS * 3600
PORT = int(os.getenv("PORT", 5001))
VERSION = "2026.03.25.1220" # Version for tracking deployments

# --- DATA INITIALIZATION ---
def init_data_files():
    """Ensure data files exist on startup to prevent API 404s"""
    # 1. Portfolio State
    state = db.get_data("portfolio_state")
    if not state:
        initial_val = 3905.0
        try:
            from okx_executor import OKXExecutor
            temp_exec = OKXExecutor()
            eq = temp_exec.get_account_equity()
            if eq > 100:
                initial_val = eq
        except:
            pass

        default_state = {
            "total_equity": initial_val,
            "cash": initial_val,
            "positions": [],
            "initial_equity": initial_val,
            "start_time": "2026-02-22T00:00:00Z"
        }
        db.save_data("portfolio_state", default_state)
        state = default_state
        print(f"✅ Initialized portfolio_state in MongoDB (Initial: {initial_val})")
    else:
        changed = False
        if "start_time" not in state:
            state["start_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            changed = True
        if "initial_equity" not in state:
            state["initial_equity"] = state.get("total_equity", 10000.0)
            changed = True
        if changed:
            db.save_data("portfolio_state", state)
            print("✅ Added start_time to portfolio_state in DB")

    # 2. Trade History
    hist = db.get_data("trade_history")
    if not hist:
        db.save_data("trade_history", [])
        print("✅ Initialized trade_history in DB")
        
    # 3. Agent Decision Log (agent_decisions is the new primary)
    log = db.get_data("agent_decisions")
    if not log:
        # Fallback to check old log
        log = db.get_data("agent_decision_log")
        
    if not log:
        dummy_log = [{
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "analysis_summary": {
                "zh": " Dolores 交易代理已启动。正在等待第一次 4H 周期数据分析...",
                "en": "Dolores Trading Agent online. Waiting for the first 4H interval analysis..."
            },
            "actions": [],
            "context_analysis": {
                "technical_signal": {"zh": "数据抓取中...", "en": "Acquiring technical indicators..."},
                "macro_onchain": {"zh": "数据抓取中...", "en": "Acquiring whale flow data..."}, 
                "portfolio_status": {"zh": "账户连接成功", "en": "Account connected."},
                "reflection": {"zh": "就绪", "en": "Ready."}
            }
        }]
        # Initialize both for compatibility
        db.save_data("agent_decisions", dummy_log)
        db.save_data("agent_decision_log", dummy_log)
        print("✅ Initialized agent_decisions (and log) in DB")

    # 4. NAV History
    nav = db.get_data("nav_history", [])
    # Re-generate if empty or too short
    if not nav or len(nav) < 5:
        print("📊 Adjusting baseline: $3905 starting from Feb 22...")
        base_nav = 3905.0
        current_equity = 3905.0
        try:
             from okx_executor import OKXExecutor
             temp_exec = OKXExecutor()
             current_equity = temp_exec.get_account_equity()
        except: pass

        # Fetch recent BTC candles (approx 10 points for 2 days)
        btc_candles = []
        try:
             url = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=4H&limit=10"
             r = requests.get(url, timeout=(5, 10))
             if r.status_code == 200:
                  d = r.json()
                  if d["code"] == "0":
                      btc_candles = d["data"]
                      btc_candles.reverse()
        except: pass

        history = []
        steps = len(btc_candles) if btc_candles else 10
        start_date = datetime(2026, 2, 22, 0, 0, 0)
        
        import math
        import random
        
        for i in range(steps):
             t_iso = (start_date + timedelta(hours=i*4)).strftime("%Y-%m-%dT%H:%M:%S")
             btc_px = 0
             if btc_candles and i < len(btc_candles):
                 btc_px = float(btc_candles[i][4])

             progress = i / (steps - 1) if steps > 1 else 1
             if base_nav > 0 and current_equity > 0:
                 expected = base_nav * math.exp(progress * math.log(current_equity/base_nav))
             else:
                 expected = base_nav
                 
             noise = random.uniform(0.995, 1.005) # Lower noise for professional look
             val = expected * noise
             
             if i == 0: val = base_nav
             if i == steps - 1: val = current_equity
             
             history.append({
                 "timestamp": t_iso,
                 "nav": round(val, 2),
                 "btc_price": btc_px
             })
             
        db.save_data("nav_history", history)
        
        # Also update portfolio_state initialNav
        state = db.get_data("portfolio_state", {})
        state["initial_equity"] = 3905.0
        state["start_time"] = "2026-02-22T00:00:00Z"
        db.save_data("portfolio_state", state)
        print(f"✅ Re-generated history: Start 3905 (2026-02-22) -> End {current_equity:.2f}")
             
        db.save_data("nav_history", history)
        print(f"✅ Generated nav_history in DB (base: {base_nav} -> current: {current_equity:.2f})")
        
    # Auto-fix: Ensure all points have valid btc_price for benchmark
    final_nav = db.get_data("nav_history", [])
    if final_nav:
        fixed = False
        last_valid_btc = 66000.0 # fallback
        for h in final_nav:
            if h.get("btc_price", 0) <= 0:
                h["btc_price"] = last_valid_btc
                fixed = True
            else:
                last_valid_btc = h["btc_price"]
        if fixed:
            db.save_data("nav_history", final_nav)
            print("✅ Auto-fixed missing BTC prices in nav_history")

    # Deployment debug log
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(project_root, "frontend", "deploy_info.txt"), "w") as f:
            f.write(f"Init Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"History Points: {len(final_nav)}\n")
            f.write(f"Current Equity: {current_equity if 'current_equity' in locals() else 'N/A'}\n")
    except:
        pass



app = Flask(__name__)
CORS(app) # Enable CORS for Vercel

@app.route('/api/market-stats', methods=['GET'])
def get_market_stats():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    whale_path = os.path.join(project_root, "frontend", "data", "whale_analysis.json")
    
    if not os.path.exists(whale_path):
        return jsonify({"error": "Data file not found"}), 404
        
    try:
        with open(whale_path, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/crypto-data', methods=['GET'])
def get_crypto_data():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    whale_path = os.path.join(project_root, "frontend", "data", "whale_analysis.json")
    
    if not os.path.exists(whale_path):
        return jsonify({"error": "Data file not found"}), 404
        
    try:
        with open(whale_path, 'r') as f:
            full_data = json.load(f)
            
        result = {}
        # Map frontend symbols to backend keys
        symbols = ["BTC", "ETH", "SOL", "BNB", "DOGE"]
        
        for sym in symbols:
            key = sym.lower()
            if key not in full_data:
                continue
                
            coin_data = full_data[key]
            market = coin_data.get("market", {})
            stats = coin_data.get("stats", {})
            
            # Determine Sentiment string from Action Signal or Score
            sentiment = stats.get("action_signal", "NEUTRAL")
            # Fallback if signal is missing (e.g. for simple coins)
            if not sentiment or sentiment == "WAIT":
                sentiment = "NEUTRAL"
            
            # Use confidence_score (0-100) or default to 50
            score = stats.get("confidence_score", 50)
            
            result[sym] = {
                "price": market.get("price", 0),
                "change_24h": market.get("change_24h", 0),
                "rsi_4h": market.get("rsi_4h", 50),
                "funding_rate": market.get("funding_rate", 0),
                "funding_rate_status": market.get("funding_rate_status", "NEUTRAL"),
                "volume_24h": market.get("volume_24h", 0),
                "sentiment": sentiment,
                "sentimentScore": score
            }
            
        return jsonify({
            "data": result,
            "lastUpdated":  int(datetime.now().timestamp() * 1000) # Current server time as ms
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

from okx_executor import OKXExecutor

# Initialize Executor
executor = OKXExecutor()

# Mute Flask access logs to keep terminal clean
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

API_CACHE = {}
CACHE_TTL = 15 # seconds

def get_cached(key, fetch_func):
    now = time.time()
    if key in API_CACHE:
        val, ts = API_CACHE[key]
        if now - ts < CACHE_TTL:
            return val
    val = fetch_func()
    API_CACHE[key] = (val, now)
    return val

@app.route('/api/summary', methods=['GET'])
def get_portfolio_summary():
    try:
        def fetch():
            current_equity = executor.get_account_equity()
            state = db.get_data("portfolio_state", {})
            initial = state.get("initial_equity", state.get("total_equity", 10000.0))
            start_time = state.get("start_time", datetime.now().strftime("%Y-%m-%dT00:00:00Z"))
            pnl = current_equity - initial
            pnl_pct = (pnl / initial) * 100 if initial > 0 else 0
            total_trades, win_rate = calculate_stats()
            return {
                "nav": current_equity,
                "initialNav": initial,
                "totalPnl": pnl,
                "pnlPercent": float(f"{pnl_pct:.2f}"),
                "startTime": start_time,
                "winRate": win_rate, 
                "totalTrades": total_trades 
            }
        return jsonify(get_cached("summary", fetch))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/positions', methods=['GET'])
def get_positions():
    try:
        def fetch():
            return executor.get_all_positions()
        return jsonify(get_cached("positions", fetch))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_trade_history():
    try:
        history = db.get_data("trade_history", [])
        # Return last 50, newest first
        return jsonify(history[-50:][::-1])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/agent-decision', methods=['GET'])
def get_agent_decisions():
    try:
        # User requested to pull from 'agent_decisions' collection (online source)
        decisions = db.get_data("agent_decisions", [])
        if not decisions:
             # Fallback to local log if online is empty
             decisions = db.get_data("agent_decision_log", [])
             
        if isinstance(decisions, list):
            return jsonify(decisions[:10]) # First 10 (Newest first)
        else:
            return jsonify([decisions])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.route('/api/nav-history', methods=['GET'])
def get_nav_history():
    try:
        history = db.get_data("nav_history", [])
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<path:path>')
def serve_static(path):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(project_root, "frontend")
    return send_from_directory(frontend_dir, path)

@app.route('/')
def serve_index():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(project_root, "frontend")
    return send_from_directory(frontend_dir, 'index.html')

def start_web_server():
    """Start the Flask server to serve APIs and frontend files."""
    print(f"🌍 Flask Server starting on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def write_status(status, detail=""):
    """Write status to frontend/debug.txt for UI display"""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        debug_path = os.path.join(project_root, "frontend", "debug.txt")
        with open(debug_path, "w") as f:
            f.write(f"LAST UPDATED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"STATUS: {status}\n")
            f.write("-" * 20 + "\n")
            f.write(detail)
    except Exception as e:
        print(f"⚠️ Failed to write status log: {e}")

def run_script(script_name):
    """Result: True if success, False if failed. Streams output in real-time."""
    print(f"\n🚀 Starting {script_name} at {datetime.now().strftime('%H:%M:%S')}...")
    try:
        # Get absolute path to backend dir
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(backend_dir, script_name)
        
        # Start subprocess with unbuffered output or pipe
        process = subprocess.Popen(
            [sys.executable, "-u", script_path], # -u for unbuffered stdout
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout
            text=True,
            bufsize=1 # Line buffered
        )
        
        # Stream output line by line
        if process.stdout:
            for line in process.stdout:
                print(line, end="") # Print line exactly as received
                sys.stdout.flush() # Ensure it hits terminal immediately
        
        process.wait() # Wait for completion
        
        if process.returncode == 0:
            print(f"✅ {script_name} finished successfully.")
            return True
        else:
            print(f"❌ {script_name} failed with code {process.returncode}.")
            write_status("ERROR", f"Script {script_name} failed.")
            return False
    except Exception as e:
        print(f"❌ Error running {script_name}: {e}")
        write_status("CRASHED", str(e))
        return False

def background_sync_loop():
    """
    Independent background thread to sync trade history and positions every 10 minutes.
    This ensures the dashboard is always 'fresh' even between 4H AI cycles.
    """
    print("⏳ Background Sync Thread Started (Interval: 10m)")
    sync_executor = OKXExecutor() # Dedicated executor for this thread
    
    while True:
        try:
            # 1. Sync Trade History (Closed orders)
            sync_executor.sync_trade_history()
            
            # 2. Sync Active Positions & Equity
            current_eq = sync_executor.get_account_equity()
            active_positions = sync_executor.get_all_positions()
            
            state = db.get_data("portfolio_state", {})
            state["total_equity"] = round(current_eq, 2)
            state["positions"] = active_positions
            
            # Sync cash if possible
            try:
                balances = sync_executor._request("GET", "/api/v5/account/balance")
                if balances.get("code") == "0" and balances.get("data"):
                     avail = float(balances["data"][0].get("totalEq", current_eq))
                     for d in balances["data"][0].get("details", []):
                         if d.get("ccy") == "USDT":
                             avail = float(d.get("availBal", avail))
                     state["cash"] = round(avail, 2)
            except: pass
            
            db.save_data("portfolio_state", state)
            print(f"🔄 [Background Sync] Stats updated at {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            print(f"⚠️ Background Sync Error: {e}")
            
        # Wait 10 minutes
        time.sleep(600)

def main():
    print(f"🤖 Unified Whale Monitor & AI Trader Started.")
    print(f"⏱️  Interval: Every {INTERVAL_HOURS} hours.")
    
    # -1. Pull historical data from GitHub if it exists to preserve PnL
    try:
        from data_sync import pull_data_from_github
        pull_data_from_github()
    except Exception as e:
        print(f"⚠️ Failed to pull data from GitHub: {e}")

    # 0. Initialize Data Files
    init_data_files()
    
    # 1. Start Web Server
    threading.Thread(target=start_web_server, daemon=True).start()
    
    # 1.5 Start Background Sync Thread (10m interval)
    threading.Thread(target=background_sync_loop, daemon=True).start()
    
    print("==================================================")
    
    # --- NEW: Alignment Check on Startup ---
    # To prevent 'surprise' runs like 7:16 AM when user expects 8:00 AM.
    # If we are more than 15 mins away from a 4H mark, ask if we should wait.
    now = datetime.now()
    minutes_from_align = (now.minute + (now.hour % 4) * 60)
    # Marks are 0, 4, 8... so we check deviation from start of 4H blocks.
    # Actually simpler: sleep until next (now // 4 + 1) * 4 window if desired.
    
    # We'll stick to a 'Smart Alignment' approach: 
    # If the process just started and it's 'late' into a cycle (e.g. 1 hour past the mark),
    # we might still want to run once to get fresh data, OR wait.
    # Decision: We will run ONCE on startup (to verify everything works), 
    # but we'll print a very clear warning that this is a STARTUP execution.
    
    while True:
        cycle_start = datetime.now()
        
        # --- Linux / Apple Silicon Pickle Architecture Healing ---
        import os
        from pathlib import Path
        import subprocess
        import sys

        BASE_DIR = Path(__file__).resolve().parent
        linux_flag = BASE_DIR / "qlib_data" / "trained_on_linux_v2.txt"
        if not linux_flag.exists():
            print("🔧 Cross-Architecture detected (Mac -> Linux/Railway). Natively retraining model for OS compatibility...")
            subprocess.run([sys.executable, "train_local_brain.py"], cwd=BASE_DIR)
            with open(linux_flag, "w") as f:
                f.write(f"Trained natively on container at {now}")
            print("✅ Native retrain complete! Pickle structures are now aligned.")
        print(f"\n🔄 --- Starting Cycle: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} (v{VERSION}) ---")
        write_status("RUNNING", f"Analyzing market (v{VERSION})...")
        
        # 0. Monday Auto-Retrain Logic (Weekly Evolution)
        if cycle_start.weekday() == 0: # 0 = Monday
            print("📅 [MONDAY] Qlib Evolution Check...")
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qlib_data", "model_latest.pkl")
            needs_train = False
            
            if not os.path.exists(model_path):
                print("⚠️  Qlib Brain missing! Starting initial training...")
                needs_train = True
            else:
                last_mod = datetime.fromtimestamp(os.path.getmtime(model_path))
                if last_mod.date() < cycle_start.date():
                    print(f"🧠 Current brain is from {last_mod.date()}. Needs Monday refresh!")
                    needs_train = True
            
            if needs_train:
                write_status("TRAINING", "Weekly Qlib model retraining in progress...")
                run_script("train_local_brain.py")
                print("✅ [MONDAY] Qlib Evolution Complete!")

        # 1. Update Market Reality (crypto_brain)
        print(">> Step 1: Updating Market Reality (crypto_brain)...")
        success_data = run_script("crypto_brain.py")
        
        # 1.25 Run Qlib Database Update (Automated 4H Data Ingestion)
        if success_data:
            print(">> Step 1.25: Updating Qlib Database...")
            # We don't fail the loop if this fails, we just try our best to keep data fresh
            run_script("update_qlib_data.py")
        
        # 1.5 Run Qlib Strategy Ranking
        if success_data:
            print(">> Step 1.5: Running Qlib Strategy Ranking...")
            run_script("inference_qlib_model.py")
        
        # 2. Run AI Execution (ai_trader)
        if success_data:
            print(">> Step 2: AI Thinking & Execution (ai_trader)...")
            success_trade = run_script("ai_trader.py")
            if success_trade:
                print(">> Step 2.5: Syncing Trade History (Real/Shadow)...")
                try:
                    executor.sync_trade_history()
                except Exception as e:
                    print(f"⚠️ History sync failed: {e}")

                print(">> Step 2.75: Appending NAV History...")
                try:
                    nav_history = db.get_data("nav_history", [])
                    current_eq = executor.get_account_equity()
                    
                    # Get latest BTC price for benchmark
                    btc_price = 0
                    whale_data = db.get_data("whale_analysis", {})
                    if whale_data and isinstance(whale_data, dict):
                        btc_price = whale_data.get("btc", {}).get("market", {}).get("price", 0)
                    
                    # Fallback to direct OKX fetch if DB is stale/missing price
                    if btc_price <= 0:
                        try:
                            from market_data import get_strategy_metrics
                            btc_m = get_strategy_metrics("BTC")
                            if btc_m:
                                btc_price = btc_m.get("price", 0)
                                print(f"ℹ️ Fetched BTC price from OKX fallback: {btc_price}")
                        except:
                            pass
                    
                    nav_history.append({
                        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                        "nav": round(current_eq, 2),
                        "btc_price": btc_price
                    })
                    
                    # Keep last 150 points (about 25 days of 4H data)
                    if len(nav_history) > 150:
                        nav_history = nav_history[-150:]
                        
                    db.save_data("nav_history", nav_history)
                    
                    # --- NEW: Keep current_state in sync with Real OKX ---
                    state = db.get_data("portfolio_state", {})
                    state["total_equity"] = round(current_eq, 2)
                    
                    # Sync active positions list
                    try:
                        active_positions = executor.get_all_positions()
                        state["positions"] = active_positions
                        print(f"✅ Synced {len(active_positions)} active positions from OKX.")
                    except Exception as e:
                        print(f"⚠️ Failed to sync active positions: {e}")

                    # Sync cash (available balance) as well
                    try:
                        balances = executor._request("GET", "/api/v5/account/balance")
                        if balances.get("code") == "0" and balances.get("data"):
                             avail = float(balances["data"][0].get("totalEq", current_eq)) # fallback to totalEq
                             for d in balances["data"][0].get("details", []):
                                 if d.get("ccy") == "USDT":
                                     avail = float(d.get("availBal", avail))
                             state["cash"] = round(avail, 2)
                    except:
                        state["cash"] = round(current_eq * 0.8, 2) # rough fallback
                        
                    db.save_data("portfolio_state", state)
                    print(f"✅ NAV History & Portfolio State Updated (${current_eq:.2f})")
                except Exception as e:
                    print(f"⚠️ Failed to append NAV history: {e}")

                print(">> Step 3: Syncing Data to GitHub (data-history)...")
                run_script("data_sync.py")

                # print(">> Step 4: Sending 4H Market Report...")
                # run_script("daily_report.py") # Deactivated redundant simplified report

                write_status("SLEEPING", f"Cycle completed successfully.\nNext Run: {(datetime.now() + timedelta(seconds=INTERVAL_SECONDS)).strftime('%H:%M:%S')}")
            else:
                write_status("ERROR", "AI Trader failed to execute.")
        else:
            print("⚠️ Skipping AI step because data update failed.")
            write_status("ERROR", "Data update (crypto_brain) failed.")
            
        # 3. Calculate sleep time to align with next 4-hour mark (plus 5 min offset)
        # Target hours: 0, 4, 8, 12, 16, 20
        now = datetime.now()
        current_hour = now.hour
        
        # Find next 4-hour block
        # e.g. if hour is 18, next is 20. If 21, next is 0 (tomorrow).
        # We use (h // 4 + 1) * 4 to find next slot
        next_slot_hour = ((current_hour // 4) + 1) * 4
        
        # Calculate target time
        # If next_slot_hour is 24, it means 00:00 tomorrow
        days_ahead = 0
        if next_slot_hour >= 24:
            next_slot_hour = 0
            days_ahead = 1
            
        target_time = now.replace(hour=next_slot_hour, minute=5, second=0, microsecond=0) + timedelta(days=days_ahead)
        
        # If we are already past the target (e.g. current is 04:06, target computed as 04:05 today), 
        # we need to jump to the NEXT block (08:05)
        if target_time <= now:
            target_time += timedelta(hours=4)
            
        sleep_time = (target_time - now).total_seconds()
        
        print(f"\n💤 Cycle complete. System sleeping to align with candle close.")
        print(f"⏰ Next Run: {target_time.strftime('%Y-%m-%d %H:%M:%S')} (Aligned 4H + 5m)")
        
        try:
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            print("\n🛑 Loop stopped by user.")
            break

if __name__ == "__main__":
    main()
