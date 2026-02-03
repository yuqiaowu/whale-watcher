import time
import subprocess
import os
import sys
import threading
import functools
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timedelta

# Configuration
INTERVAL_HOURS = 4
INTERVAL_SECONDS = INTERVAL_HOURS * 3600
PORT = int(os.getenv("PORT", 8080))

def start_web_server():
    """Start a simple HTTP server to serve the frontend dashboard."""
    # Serve files from 'frontend' directory (relative to project root)
    # We assume run_loop.py is in backend/, so we go up one level then into frontend
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(project_root, "frontend")
    
    handler = functools.partial(SimpleHTTPRequestHandler, directory=frontend_dir)
    # Allow address reuse to prevent "Address already in use" errors on restart
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(('0.0.0.0', PORT), handler)
    print(f"🌍 Web Server running at http://localhost:{PORT}")
    server.serve_forever()

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
                write_status("SLEEPING", f"Cycle completed successfully.\nNext Run: {(datetime.now() + timedelta(seconds=INTERVAL_SECONDS)).strftime('%H:%M:%S')}")
            else:
                write_status("ERROR", "AI Trader failed to execute.")
        else:
            print("⚠️ Skipping AI step because data update failed.")
            write_status("ERROR", "Data update (crypto_brain) failed.")
            
        # 3. Wait for next cycle
        elapsed = (datetime.now() - cycle_start).total_seconds()
        sleep_time = max(0, INTERVAL_SECONDS - elapsed)
        
        next_run = datetime.now() + timedelta(seconds=sleep_time)
        print(f"\n💤 Cycle complete. System sleeping.")
        print(f"⏰ Next Run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            print("\n🛑 Loop stopped by user.")
            break

if __name__ == "__main__":
    main()
