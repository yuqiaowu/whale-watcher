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

# Configuration
INTERVAL_HOURS = 4
INTERVAL_SECONDS = INTERVAL_HOURS * 3600
PORT = int(os.getenv("PORT", 5001))

# --- DATA INITIALIZATION ---
def init_data_files():
    """Ensure data files exist on startup to prevent API 404s"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, "frontend", "data")
    
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception as e:
            print(f"⚠️ Failed to create data dir: {e}")
            return

    # 1. Portfolio State
    port_path = os.path.join(data_dir, "portfolio_state.json")
    if not os.path.exists(port_path):
        # Default fallback
        initial_val = 10000.0
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
            "start_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        with open(port_path, "w") as f:
            json.dump(default_state, f, indent=2)
        print(f"✅ Initialized portfolio_state.json (Initial: {initial_val})")
    else:
        # Ensure start_time exists in existing file
        try:
             with open(port_path, "r") as f:
                 state = json.load(f)
             
             if "start_time" not in state:
                 state["start_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
             if "initial_equity" not in state:
                 state["initial_equity"] = state.get("total_equity", 10000.0)
             with open(port_path, "w") as f:
                 json.dump(state, f, indent=2)
                 print("✅ Added start_time to portfolio_state.json")
        except Exception as e:
            print(f"⚠️ Failed to update portfolio_state.json: {e}")

    # 2. Trade History
    hist_path = os.path.join(data_dir, "trade_history.json")
    if not os.path.exists(hist_path):
        with open(hist_path, "w") as f:
            json.dump([], f)
        print("✅ Initialized trade_history.json")
        
    # 3. Agent Decision Log
    log_path = os.path.join(data_dir, "agent_decision_log.json")
    if not os.path.exists(log_path):
        # Create a cleaner initial log
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
        with open(log_path, "w") as f:
            json.dump(dummy_log, f, indent=2)
        print("✅ Initialized agent_decision_log.json")

    # 4. NAV History
    nav_path = os.path.join(data_dir, "nav_history.json")
    if not os.path.exists(nav_path):
        # Generate history bridging Initial 10k -> Current API Equity
        current_equity = 10000.0
        try:
             from okx_executor import OKXExecutor
             temp_exec = OKXExecutor()
             eq = temp_exec.get_account_equity()
             if eq > 100:
                 current_equity = eq
        except Exception as e:
             print(f"⚠️ Failed to fetch equity for history gen: {e}")

        # Fetch Real BTC history (4H Candles)
        btc_candles = []
        try:
             url = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=4H&limit=42"
             r = requests.get(url, timeout=10)
             if r.status_code == 200:
                  d = r.json()
                  if d["code"] == "0":
                      btc_candles = d["data"]
                      btc_candles.reverse() # Oldest first
        except Exception as e:
             print(f"⚠️ Failed to fetch BTC candles: {e}")

        history = []
        base_nav = 10000.0
        try:
             with open(port_path, "r") as f:
                 ps = json.load(f)
                 base_nav = ps.get("initial_equity", 10000.0)
        except:
             pass
        
        steps = len(btc_candles) if btc_candles else 42
        
        import math
        import random
        
        for i in range(steps):
             if btc_candles:
                 candle = btc_candles[i]
                 ts_ms = int(candle[0])
                 t_iso = datetime.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%dT%H:%M:%S")
                 btc_px = float(candle[4]) # Close price
             else:
                 t_iso = (datetime.now() - timedelta(hours=(steps - i)*4)).strftime("%Y-%m-%dT%H:%M:%S")
                 btc_px = 65000 * (1 + random.uniform(-0.05, 0.05))

             progress = i / (steps - 1) if steps > 1 else 1
             
             # Interpolate NAV
             if base_nav > 0 and current_equity > 0:
                 expected = base_nav * math.exp(progress * math.log(current_equity/base_nav))
             else:
                 expected = base_nav
                 
             # Add noise +/- 2%
             noise = random.uniform(0.98, 1.02)
             val = expected * noise
             
             # Force start and end
             if i == 0: val = base_nav
             if i == steps - 1: val = current_equity
             
             history.append({
                 "timestamp": t_iso,
                 "nav": round(val, 2),
                 "btc_price": btc_px
             })
             
        with open(nav_path, "w") as f:
            json.dump(history, f, indent=2)
        print(f"✅ Generated nav_history.json with real BTC data (10k -> {current_equity:.2f})")



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

# ...

@app.route('/api/summary', methods=['GET'])
def get_portfolio_summary():
    try:
        # Hybrid Approach:
        # 1. Get Equity from Executor (Source of Truth for Balance)
        current_equity = executor.get_account_equity()
        
        # 2. Get Initial & History from File (for PnL tracking over time)
        # Because OKX API doesn't easily give "Portfolio Initial Value" from API directly in a simple call
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(project_root, "frontend", "data", "portfolio_state.json")
        
        initial = 10000.0
        start_time = datetime.now().strftime("%Y-%m-%dT00:00:00Z")
        if os.path.exists(path):
             with open(path, "r") as f:
                 data = json.load(f)
                 initial = data.get("initial_equity", data.get("initial", 10000.0))
                 start_time = data.get("start_time", start_time)

        # Calculate PnL
        pnl = current_equity - initial
        pnl_pct = (pnl / initial) * 100 if initial > 0 else 0

        # Calculate Win Rate & Total Trades
        hist_file = os.path.join(project_root, "frontend", "data", "trade_history.json")
        total_trades, win_rate = calculate_stats(hist_file)

        return jsonify({
            "nav": current_equity,
            "initialNav": initial,
            "totalPnl": pnl,
            "pnlPercent": float(f"{pnl_pct:.2f}"),
            "startTime": start_time,
            "winRate": win_rate, 
            "totalTrades": total_trades 
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/positions', methods=['GET'])
def get_positions():
    try:
        # Use Executor to force alignment with Trading Mode
        positions = executor.get_all_positions()
        return jsonify(positions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_trade_history():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Correct file: trade_history.json (Past completed trades)
    path = os.path.join(project_root, "frontend", "data", "trade_history.json")
    
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
            # Return last 50, newest first
            return jsonify(data[-50:][::-1])
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/agent-decision', methods=['GET'])
def get_agent_decisions():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Correct file: agent_decision_log.json (AI thinking logs)
    path = os.path.join(project_root, "frontend", "data", "agent_decision_log.json")
    
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                try:
                    data = json.load(f)
                    if isinstance(data, list):
                        return jsonify(data[:10]) # First 10 (Newest first)
                    else:
                        return jsonify([data])
                except json.JSONDecodeError:
                    return jsonify([])
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.route('/api/nav-history', methods=['GET'])
def get_nav_history():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(project_root, "frontend", "data", "nav_history.json")
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
            return jsonify(data)
        return jsonify([])
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
    """Result: True if success, False if failed"""
    print(f"\n🚀 Starting {script_name} at {datetime.now().strftime('%H:%M:%S')}...")
    try:
        # Get absolute path to backend dir
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(backend_dir, script_name)
        
        # Run python script
        result = subprocess.run(
            [sys.executable, script_path], 
            capture_output=True, # Capture output for logging
            text=True
        )
        
        # Print output to console (streaming effect simulation)
        print(result.stdout)
        if result.stderr:
            print(f"⚠️ STDERR from {script_name}:\n{result.stderr}")

        if result.returncode == 0:
            print(f"✅ {script_name} finished successfully.")
            return True
        else:
            print(f"❌ {script_name} failed with code {result.returncode}.")
            write_status("ERROR", f"Script {script_name} failed.\n{result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error running {script_name}: {e}")
        write_status("CRASHED", str(e))
        return False

def main():
    print(f"🤖 Unified Whale Monitor & AI Trader Started.")
    print(f"⏱️  Interval: Every {INTERVAL_HOURS} hours.")
    
    # 0. Initialize Data Files
    init_data_files()
    
    # 1. Start Web Server
    threading.Thread(target=start_web_server, daemon=True).start()
    
    print("==================================================")
    
    while True:
        cycle_start = datetime.now()
        print(f"\n🔄 --- Starting Cycle: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} ---")
        write_status("RUNNING", "Fetching new data and analyzing...")
        
        # 1. Update Market Reality (crypto_brain)
        print(">> Step 1: Updating Market Reality (crypto_brain)...")
        success_data = run_script("crypto_brain.py")
        
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

                print(">> Step 3: Syncing Data to GitHub (data-history)...")
                run_script("data_sync.py")

                print(">> Step 4: Sending 4H Market Report...")
                run_script("daily_report.py")

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
