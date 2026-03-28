import os
import requests
import base64
import json
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.env")
load_dotenv(dotenv_path=env_path)

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_URL_RAW = os.getenv("REPO_URL", "github.com/yuqiaowu/whale-watcher")
if "github.com/" in REPO_URL_RAW:
    REPO_slug = REPO_URL_RAW.split("github.com/")[-1].replace(".git", "")
else:
    REPO_slug = REPO_URL_RAW

API_BASE = f"https://api.github.com/repos/{REPO_slug}"
BRANCH_NAME = "data-history"

FILES_TO_PULL = [
    "frontend/data/trade_history.json",
    "frontend/data/agent_decision_log.json",
    "frontend/data/agent_memory.json",
    "frontend/data/nav_history.json",
    "frontend/data/portfolio_state.json",
    "frontend/data/whale_analysis.json"
]

def pull_file(file_path):
    """Download a single file from GitHub and update local version."""
    url = f"{API_BASE}/contents/{file_path}?ref={BRANCH_NAME}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    print(f"📡 Requesting {file_path} from GitHub...")
    resp = requests.get(url, headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        if "content" in data:
            content = base64.b64decode(data['content'])
            
            # Target local path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            abs_path = os.path.join(project_root, file_path)
            
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "wb") as f:
                f.write(content)
            print(f"✅ Successfully pulled and updated: {file_path}")
            return True
    elif resp.status_code == 404:
        print(f"⚠️ File not found on GitHub branch '{BRANCH_NAME}': {file_path}")
    else:
        print(f"❌ Failed to pull {file_path}. Status: {resp.status_code}. Response: {resp.text}")
    return False

if __name__ == "__main__":
    print(f"🔄 Starting Data Recall from '{BRANCH_NAME}' branch...")
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN not found! Please set it in .env")
    else:
        success_count = 0
        for f in FILES_TO_PULL:
            if pull_file(f):
                success_count += 1
        
        print(f"\n✨ Pull Complete. Updated {success_count}/{len(FILES_TO_PULL)} files.")
