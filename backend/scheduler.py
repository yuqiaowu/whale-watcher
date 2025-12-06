import schedule
import time
import os
import subprocess
from datetime import datetime
import whale_watcher

def run_job():
    print(f"[{datetime.now()}] Starting scheduled job...")
    
    # 1. Run the analysis
    try:
        whale_watcher.main()
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
        # Configure Git
        subprocess.run(["git", "config", "--global", "user.name", "Whale Watcher Bot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@whalewatcher.com"], check=True)
        
        # Add changes
        subprocess.run(["git", "add", "../frontend/data/whale_analysis.json"], check=True)
        
        # Check if there are changes
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("No changes to commit.")
            return

        # Commit (No [skip ci] so Vercel triggers)
        commit_msg = f"data: update whale analysis {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        
        # Push
        # Construct auth URL: https://TOKEN@github.com/user/repo.git
        auth_repo_url = f"https://{github_token}@{repo_url.replace('https://', '')}"
        subprocess.run(["git", "push", auth_repo_url, "main"], check=True)
        
        print("Successfully pushed data updates.")
        
    except Exception as e:
        print(f"Error during git operation: {e}")

def start_scheduler():
    print("Whale Watcher Scheduler Started...")
    print("Schedule: 08:00, 12:00, 14:00, 16:00 (Server Time)")
    
    # Schedule jobs
    schedule.every().day.at("08:00").do(run_job)
    schedule.every().day.at("12:00").do(run_job)
    schedule.every().day.at("14:00").do(run_job)
    schedule.every().day.at("16:00").do(run_job)
    
    # Also run once on startup to verify
    run_job() 

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    start_scheduler()
