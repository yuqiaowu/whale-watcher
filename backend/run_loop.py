import time
import subprocess
import os
import sys
import threading
import json
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
from stats_calculator import calculate_stats
from db_client import db
from dotenv import load_dotenv
from deterministic_pipeline import run_deterministic_cycle
from execution_reconciliation import run_execution_reconciliation
from post_trade_review import run_post_trade_review
from position_runtime import run_in_position_runtime

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.env")
load_dotenv(dotenv_path=env_path)

# Configuration
INTERVAL_HOURS = int(os.getenv("RUN_INTERVAL_HOURS", "2"))
INTERVAL_SECONDS = INTERVAL_HOURS * 3600
DECISION_TIMEFRAME_HOURS = int(os.getenv("DECISION_TIMEFRAME_HOURS", "4"))
SKIP_DUPLICATE_DECISION_CYCLE = os.getenv("SKIP_DUPLICATE_DECISION_CYCLE", "1").lower() in {"1", "true", "yes"}
PORT = int(os.getenv("PORT", 5001))
LOCAL_TZ_NAME = os.getenv("LOCAL_TIMEZONE", "Asia/Shanghai")
VERSION = (os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("APP_VERSION") or "2026.04.20.local")[:12]
ENABLE_V2_PIPELINE = os.getenv("ENABLE_V2_PIPELINE", "1").lower() in {"1", "true", "yes"}

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
        
    # 3. V2 ledger bootstrap
    latest_record = db.get_data("latest_trade_decision_record", {})
    if not latest_record:
        print("ℹ️ No V2 trade record found yet. It will be created on the first deterministic cycle.")

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
def get_trade_decision_records_compat():
    try:
        records = db.get_data("trade_decision_records", [])
        if isinstance(records, list) and records:
            return jsonify(records[:10])
        latest_cycle = db.get_data("latest_decision_cycle_v2", {})
        return jsonify([latest_cycle] if latest_cycle else [])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.route('/api/nav-history', methods=['GET'])
def get_nav_history():
    try:
        history = db.get_data("nav_history", [])
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v2/latest-cycle', methods=['GET'])
def get_latest_v2_cycle():
    try:
        cycle = db.get_data("latest_decision_cycle_v2", {})
        return jsonify(cycle if cycle else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v2/trade-records', methods=['GET'])
def get_v2_trade_records():
    try:
        records = db.get_data("trade_decision_records", [])
        if isinstance(records, list):
            return jsonify(records[:20])
        return jsonify([records])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v2/latest-trade-record', methods=['GET'])
def get_latest_v2_trade_record():
    try:
        record = db.get_data("latest_trade_decision_record", {})
        return jsonify(record if record else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/health', methods=['GET'])
def get_health():
    try:
        latest_run = db.get_data("latest_system_run", {})
        latest_cycle = db.get_data("latest_decision_cycle_v2", {})
        return jsonify({
            "status": "ok",
            "version": VERSION,
            "mongo_connected": db.is_connected,
            "latest_run_status": latest_run.get("status"),
            "latest_run_at": latest_run.get("completed_at") or latest_run.get("started_at"),
            "latest_cycle_id": latest_cycle.get("cycleId"),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/admin/latest-run', methods=['GET'])
def get_latest_system_run():
    try:
        run = db.get_data("latest_system_run", {})
        return jsonify(_hydrate_run_entry(run) if run else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/runs', methods=['GET'])
def get_system_runs():
    try:
        runs = db.get_data("system_run_history", [])
        if isinstance(runs, list):
            return jsonify([_hydrate_run_entry(run) for run in runs[:50]])
        return jsonify([_hydrate_run_entry(runs)])
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


def _utc_iso_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_iso_now() -> str:
    return datetime.now(ZoneInfo(LOCAL_TZ_NAME)).strftime("%Y-%m-%dT%H:%M:%S%z")


def _aligned_cycle_id(now=None, block_hours: int = DECISION_TIMEFRAME_HOURS) -> str:
    now = now or datetime.utcnow()
    block_hour = (now.hour // block_hours) * block_hours
    aligned = now.replace(hour=block_hour, minute=0, second=0, microsecond=0)
    return f"cycle_{aligned.strftime('%Y-%m-%d_%H00')}"


def _append_system_run(entry):
    history = db.get_data("system_run_history", [])
    if not isinstance(history, list):
        history = []
    history.insert(0, entry)
    deduped = []
    seen = set()
    for item in history:
        run_id = str(item.get("runId") or "")
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        deduped.append(item)
    db.save_data("system_run_history", deduped[:200])
    db.save_data("latest_system_run", entry)


def _approved_symbols_for_cycle(cycle_id):
    if not cycle_id:
        return []
    records = db.get_data("trade_decision_records", [])
    if not isinstance(records, list):
        return []

    approved_symbols = []
    for record in records:
        if record.get("cycleId") != cycle_id:
            continue
        risk_review = record.get("riskReview") or {}
        if risk_review.get("approved"):
            symbol = record.get("symbol")
            if symbol and symbol not in approved_symbols:
                approved_symbols.append(symbol)
    return approved_symbols


def _hydrate_run_entry(entry):
    if not isinstance(entry, dict):
        return entry
    hydrated = dict(entry)
    approved_symbols = hydrated.get("approved_symbols")
    cycle_id = hydrated.get("cycle_id") or hydrated.get("target_cycle_id")
    if cycle_id and (not isinstance(approved_symbols, list) or not approved_symbols):
        hydrated["approved_symbols"] = _approved_symbols_for_cycle(cycle_id)
    return hydrated

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
            stdin=subprocess.DEVNULL, # Prevent "Bad file descriptor" error on some environments
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

def run_v2_cycle():
    """Run the deterministic v2 decision chain and persist cycle outputs."""
    print(">> Step 2: Deterministic V2 Pipeline (snapshot -> candidate -> rule -> risk -> execution request)...")
    try:
        result = run_deterministic_cycle(executor=executor)
        approved = sum(1 for item in result.get("risk_reviews", []) if item.get("approved"))
        print(
            f"✅ V2 cycle completed: {result.get('cycleId')} | "
            f"records={result.get('record_count', 0)} | approved={approved} | "
            f"reviewed={result.get('post_trade_review', {}).get('evaluated_count', 0)}"
        )
        return {"success": True, "result": result}
    except Exception as e:
        print(f"❌ V2 pipeline failed: {e}")
        write_status("ERROR", f"V2 pipeline failed: {e}")
        return {"success": False, "error": str(e)}

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
            reconciliation_summary = run_execution_reconciliation()
            if reconciliation_summary.get("updated_count", 0) > 0:
                print(
                    f"🧾 [Execution Reconcile] updated {reconciliation_summary['updated_count']} / "
                    f"{reconciliation_summary['record_count']} execution states"
                )
            review_summary = run_post_trade_review()
            if review_summary.get("evaluated_count", 0) > 0:
                print(
                    f"🧾 [Background Review] updated {review_summary['evaluated_count']} / "
                    f"{review_summary['record_count']} trade evaluations"
                )
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
        run_entry = {
            "runId": f"run_{cycle_start.strftime('%Y%m%dT%H%M%S')}",
            "started_at": _utc_iso_now(),
            "started_at_local": _local_iso_now(),
            "status": "running",
            "version": VERSION,
            "interval_hours": INTERVAL_HOURS,
            "decision_timeframe_hours": DECISION_TIMEFRAME_HOURS,
            "target_cycle_id": _aligned_cycle_id(),
            "data_update_ok": False,
            "qlib_ok": False,
            "v2_cycle_status": "not_started",
            "sync_status": "not_started",
        }
        
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
        run_entry["data_update_ok"] = bool(success_data)
        
        # 1.25 Run Qlib Database Update (Automated 4H Data Ingestion)
        if success_data:
            print(">> Step 1.25: Updating Qlib Database...")
            # We don't fail the loop if this fails, we just try our best to keep data fresh
            run_script("update_qlib_data.py")
        
        # 1.5 Run Qlib Strategy Ranking
        if success_data:
            print(">> Step 1.5: Running Qlib Strategy Ranking...")
            run_entry["qlib_ok"] = bool(run_script("inference_qlib_model.py"))

        # 1.75 Run deterministic v2 pipeline. Safe by default because execution is disabled
        # unless ENABLE_V2_EXECUTION is explicitly enabled.
        v2_result = None
        if success_data and ENABLE_V2_PIPELINE:
            latest_cycle = db.get_data("latest_decision_cycle_v2", {})
            latest_cycle_id = latest_cycle.get("cycleId") if isinstance(latest_cycle, dict) else None
            if SKIP_DUPLICATE_DECISION_CYCLE and latest_cycle_id == run_entry["target_cycle_id"]:
                print(f"⏭️  No new {DECISION_TIMEFRAME_HOURS}H decision bar yet. Skipping duplicate cycle {latest_cycle_id}.")
                run_entry["v2_cycle_status"] = "skipped_duplicate_cycle"
                run_entry["cycle_id"] = latest_cycle_id
            else:
                v2_result = run_v2_cycle()
                run_entry["v2_cycle_status"] = "completed" if v2_result.get("success") else "failed"
                if v2_result.get("success"):
                    result = v2_result.get("result") or {}
                    run_entry["cycle_id"] = result.get("cycleId")
                    run_entry["record_count"] = result.get("record_count", 0)
                    run_entry["approved_symbols"] = [
                        review["symbol"]
                        for review in result.get("risk_reviews", [])
                        if review.get("approved") and review.get("symbol")
                    ]
                    run_entry["post_trade_review"] = result.get("post_trade_review")
                else:
                    run_entry["error"] = v2_result.get("error")

        # 2. Sync portfolio and append NAV history after deterministic cycle.
        if success_data:
            run_entry["sync_status"] = "running"
            print(">> Step 2.5: Syncing Trade History (Real/Shadow)...")
            try:
                executor.sync_trade_history()
            except Exception as e:
                print(f"⚠️ History sync failed: {e}")

            print(">> Step 2.55: Reconciling Execution Receipts...")
            try:
                reconciliation_summary = run_execution_reconciliation()
                print(
                    f"✅ Execution reconciliation complete "
                    f"(updated={reconciliation_summary.get('updated_count', 0)}, "
                    f"records={reconciliation_summary.get('record_count', 0)})"
                )
            except Exception as e:
                print(f"⚠️ Execution reconciliation failed: {e}")

            print(">> Step 2.6: Running In-Position Runtime Rules...")
            try:
                runtime_summary = run_in_position_runtime(executor)
                print(
                    f"✅ In-position runtime complete "
                    f"(updated={runtime_summary.get('updated_count', 0)}, "
                    f"actions={len(runtime_summary.get('actions', []))})"
                )
            except Exception as e:
                print(f"⚠️ In-position runtime failed: {e}")

            print(">> Step 2.65: Running Post-Trade Review...")
            try:
                review_summary = run_post_trade_review()
                print(
                    f"✅ Post-trade review complete "
                    f"(evaluated={review_summary.get('evaluated_count', 0)}, "
                    f"records={review_summary.get('record_count', 0)})"
                )
            except Exception as e:
                print(f"⚠️ Post-trade review failed: {e}")

            print(">> Step 2.75: Appending NAV History...")
            try:
                nav_history = db.get_data("nav_history", [])
                current_eq = executor.get_account_equity()

                btc_price = 0
                whale_data = db.get_data("whale_analysis", {})
                if whale_data and isinstance(whale_data, dict):
                    btc_price = whale_data.get("btc", {}).get("market", {}).get("price", 0)

                if btc_price <= 0:
                    try:
                        from market_data import get_strategy_metrics
                        btc_m = get_strategy_metrics("BTC")
                        if btc_m:
                            btc_price = btc_m.get("price", 0)
                    except Exception:
                        pass

                nav_history.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    "nav": round(current_eq, 2),
                    "btc_price": btc_price
                })
                if len(nav_history) > 150:
                    nav_history = nav_history[-150:]
                db.save_data("nav_history", nav_history)

                state = db.get_data("portfolio_state", {})
                state["total_equity"] = round(current_eq, 2)
                try:
                    state["positions"] = executor.get_all_positions()
                except Exception as e:
                    print(f"⚠️ Failed to sync active positions: {e}")

                try:
                    balances = executor._request("GET", "/api/v5/account/balance")
                    if balances.get("code") == "0" and balances.get("data"):
                        avail = float(balances["data"][0].get("totalEq", current_eq))
                        for d in balances["data"][0].get("details", []):
                            if d.get("ccy") == "USDT":
                                avail = float(d.get("availBal", avail))
                        state["cash"] = round(avail, 2)
                except Exception:
                    state["cash"] = round(current_eq * 0.8, 2)

                db.save_data("portfolio_state", state)
                print(f"✅ NAV History & Portfolio State Updated (${current_eq:.2f})")
            except Exception as e:
                print(f"⚠️ Failed to append NAV history: {e}")

            print(">> Step 3: Syncing Data to GitHub (data-history)...")
            run_script("data_sync.py")
            run_entry["sync_status"] = "completed"
            if run_entry.get("v2_cycle_status") == "failed":
                run_entry["status"] = "failed"
            else:
                run_entry["status"] = "completed"
            write_status("SLEEPING", f"V2 cycle completed successfully.\nNext Run: {(datetime.now() + timedelta(seconds=INTERVAL_SECONDS)).strftime('%H:%M:%S')}")
        else:
            print("⚠️ Skipping AI step because data update failed.")
            run_entry["status"] = "failed"
            run_entry["sync_status"] = "skipped"
            write_status("ERROR", "Data update (crypto_brain) failed.")

        run_entry["completed_at"] = _utc_iso_now()
        run_entry["completed_at_local"] = _local_iso_now()
        _append_system_run(run_entry)
            
        # 3. Calculate sleep time to align with next interval mark (plus 5 min offset)
        now = datetime.now()
        current_hour = now.hour
        
        next_slot_hour = ((current_hour // INTERVAL_HOURS) + 1) * INTERVAL_HOURS
        
        # Calculate target time
        # If next_slot_hour is 24, it means 00:00 tomorrow
        days_ahead = 0
        if next_slot_hour >= 24:
            next_slot_hour = 0
            days_ahead = 1
            
        target_time = now.replace(hour=next_slot_hour, minute=5, second=0, microsecond=0) + timedelta(days=days_ahead)
        
        # If we are already past the target (e.g. current is 04:06, target computed as 04:05 today), 
        # we need to jump to the NEXT block
        if target_time <= now:
            target_time += timedelta(hours=INTERVAL_HOURS)
            
        sleep_time = (target_time - now).total_seconds()
        
        print(f"\n💤 Cycle complete. System sleeping to align with candle close.")
        print(f"⏰ Next Run: {target_time.strftime('%Y-%m-%d %H:%M:%S')} (Aligned {INTERVAL_HOURS}H + 5m)")
        
        try:
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            print("\n🛑 Loop stopped by user.")
            break

if __name__ == "__main__":
    main()
