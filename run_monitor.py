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
            print(f"[Monitor] Sleeping for {INTERVAL_SECONDS} seconds...")
            time.sleep(INTERVAL_SECONDS)
            run_analysis()
        except KeyboardInterrupt:
            print("\n[Monitor] Stopped by user.")
            break

if __name__ == "__main__":
    main()
