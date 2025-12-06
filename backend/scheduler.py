import schedule
import time
import os
import subprocess
from datetime import datetime
import whale_watcher

print("DEBUG: scheduler.py loaded...", flush=True)

def run_job():
    print(f"[{datetime.now()}] Starting scheduled job...")
    
    # 1. Run the analysis
    try:
        print(f"[{datetime.now()}] Running whale_watcher.main()...")
        whale_watcher.main()
        print(f"[{datetime.now()}] whale_watcher.main() completed.")
    except Exception as e:
        print(f"Error running whale_watcher: {e}")
        return

    # 2. Git Commit & Push
    # Note: This requires GITHUB_TOKEN to be set in environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    repo_url = os.getenv("REPO_URL") # e.g. github.com/username/repo.git
    
    if not github_token or not repo_url:
        print("Skipping Git Push: GITHUB_TOKEN or REPO_URL not set.")
        return

    try:
        # Strategy: Clone -> Copy -> Commit -> Push
        # This avoids issues where the container doesn't have .git folder
        
        import shutil
        
        temp_dir = "/tmp/whale-watcher-deploy"
        
        # Clean up previous temp dir if exists
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            
        # Construct auth URL: https://TOKEN@github.com/user/repo.git
        # Remove https:// if present to avoid double protocol
        clean_repo_url = repo_url.replace("https://", "")
        auth_repo_url = f"https://{github_token}@{clean_repo_url}"
        
        print(f"Cloning repo to {temp_dir}...")
        subprocess.run(["git", "clone", "-q", auth_repo_url, temp_dir], check=True)
        
        # Configure Git in temp dir
        subprocess.run(["git", "config", "user.name", "Whale Watcher Bot"], cwd=temp_dir, check=True)
        subprocess.run(["git", "config", "user.email", "bot@whalewatcher.com"], cwd=temp_dir, check=True)
        
        # Copy updated data file to temp repo
        # Source: ../frontend/data/whale_analysis.json (relative to backend/scheduler.py) -> /app/frontend/data/whale_analysis.json
        # Dest: temp_dir/frontend/data/whale_analysis.json
        
        source_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/data/whale_analysis.json"))
        dest_file = os.path.join(temp_dir, "frontend/data/whale_analysis.json")
        
        print(f"Copying data from {source_file} to {dest_file}...")
        shutil.copy2(source_file, dest_file)
        
        # Check for changes
        status = subprocess.run(["git", "status", "--porcelain"], cwd=temp_dir, capture_output=True, text=True)
        if not status.stdout.strip():
            print("No changes to commit.")
            return

        # Commit (No [skip ci] so Vercel triggers)
        commit_msg = f"data: update whale analysis {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=temp_dir, check=True)
        
        # Push
        print("Pushing updates...")
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=temp_dir, check=True)
        
        print("Successfully pushed data updates.")
        
        # Cleanup
        shutil.rmtree(temp_dir)
        
    except Exception as e:
        print(f"Error during git operation: {e}")

def start_scheduler():
    print("Whale Watcher Scheduler Started...")
    print("Schedule: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 (UTC)")
    
    # Schedule jobs
    # Schedule jobs (UTC Time)
    # 00:00 UTC = 08:00 CST
    # 04:00 UTC = 12:00 CST
    # 08:00 UTC = 16:00 CST
    # 12:00 UTC = 20:00 CST
    # 16:00 UTC = 00:00 CST
    # 20:00 UTC = 04:00 CST
    schedule.every().day.at("00:00").do(run_job)
    schedule.every().day.at("04:00").do(run_job)
    schedule.every().day.at("08:00").do(run_job)
    schedule.every().day.at("12:00").do(run_job)
    schedule.every().day.at("16:00").do(run_job)
    schedule.every().day.at("20:00").do(run_job)
    
    # Start a dummy web server to satisfy Railway's port binding requirement
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

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

    # Start web server in background thread
    threading.Thread(target=start_web_server, daemon=True).start()

    # Also run once on startup to verify
    run_job() 

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    start_scheduler()
