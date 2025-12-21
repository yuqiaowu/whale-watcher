import os
import time
import subprocess
import datetime
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration: Run every 1 hour (3600 seconds)
INTERVAL_SECONDS = 3600 

# Dummy Web Server for Railway Port Binding
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_web_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Starting dummy web server on port {port}")
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
