import os
import time
import subprocess
import datetime
import sys
import threading
import functools
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Configuration: Run every 1 hour (3600 seconds)
INTERVAL_SECONDS = 3600 

def start_web_server():
    port = int(os.getenv("PORT", 8080))
    # Serve files from 'frontend' directory so that index.html and data/ are accessible
    # Python 3.7+ supports directory argument
    handler = functools.partial(SimpleHTTPRequestHandler, directory="frontend")
    server = HTTPServer(('0.0.0.0', port), handler)
    print(f"Starting static web server on port {port} serving 'frontend/'")
    server.serve_forever()

def run_analysis():
    print(f"\n[Monitor] Starting analysis job at {datetime.datetime.now()}...")
    try:
        # Run the main analysis script using the current python interpreter
        result = subprocess.run([sys.executable, "backend/whale_watcher.py"], check=True)
        print(f"[Monitor] Job completed successfully at {datetime.datetime.now()}")
    except subprocess.CalledProcessError as e:
        print(f"[Monitor] Job failed with error: {e}")
    except Exception as e:
        print(f"[Monitor] Unexpected error: {e}")

def main():
    print("🚀 Whale Watcher Monitor Started!")
    
    # Start web server in background thread
    threading.Thread(target=start_web_server, daemon=True).start()
    
    print(f"⏱️  Schedule: Running every {INTERVAL_SECONDS/60:.0f} minutes.")
    
    # Run immediately on startup
    run_analysis()

    while True:
        try:
            # Calculate time until next fixed 4-hour mark (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC)
            now = datetime.datetime.utcnow()
            # fixed blocks: 0, 4, 8, 12, 16, 20
            # find next block
            next_hour = (now.hour // 4 + 1) * 4
            
            # handle overflow to next day
            if next_hour >= 24:
                next_hour = 0
                tomorrow = now + datetime.timedelta(days=1)
                next_run = tomorrow.replace(hour=next_hour, minute=0, second=0, microsecond=0)
            else:
                next_run = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
            
            # Calculate seconds to sleep
            sleep_seconds = (next_run - now).total_seconds()
            
            # Add a small buffer (e.g. 10s) to ensure we don't wake up slightly before and double run or drift
            sleep_seconds += 10 
            
            print(f"[Monitor] Next scheduled run at {next_run} UTC (in {sleep_seconds/3600:.2f} hours)")
            time.sleep(sleep_seconds)
            
            run_analysis()
        except KeyboardInterrupt:
            print("\n[Monitor] Stopped by user.")
            break

if __name__ == "__main__":
    main()
