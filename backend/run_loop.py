import time
import subprocess
import os
import sys
import json
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta

# Configuration
INTERVAL_HOURS = 4
INTERVAL_SECONDS = INTERVAL_HOURS * 3600
PORT = int(os.getenv("PORT", 8080))

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
    
    # 0. Start Web Server
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
                print(">> Step 3: Syncing Data to GitHub (data-history)...")
                run_script("data_sync.py")
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
