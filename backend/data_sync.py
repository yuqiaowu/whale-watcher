import os
import json
import base64
import requests
import datetime

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# Extract Owner/Repo from "github.com/owner/repo" or similar
REPO_URL_RAW = os.getenv("REPO_URL", "github.com/yuqiaowu/whale-watcher")
if "github.com/" in REPO_URL_RAW:
    REPO_slug = REPO_URL_RAW.split("github.com/")[-1].replace(".git", "")
else:
    REPO_slug = REPO_URL_RAW

API_BASE = f"https://api.github.com/repos/{REPO_slug}"
BRANCH_NAME = "data-history"
FILE_PATH = "frontend/data/whale_analysis.json"

def get_file_sha(path, branch):
    """Get the SHA of an existing file to update it."""
    url = f"{API_BASE}/contents/{path}?ref={branch}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None

def create_branch_if_missing(branch, source_branch="main"):
    """Check if branch exists, if not create it from source."""
    # 1. Check if branch exists
    url = f"{API_BASE}/git/ref/heads/{branch}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        print(f"✅ Branch '{branch}' exists.")
        return True
    
    print(f"⚠️ Branch '{branch}' not found. Creating from '{source_branch}'...")
    # 2. Get source branch SHA
    url_source = f"{API_BASE}/git/ref/heads/{source_branch}"
    resp_source = requests.get(url_source, headers=headers)
    if resp_source.status_code != 200:
        print(f"❌ Source branch '{source_branch}' not found. Cannot create '{branch}'.")
        return False
    source_sha = resp_source.json()['object']['sha']
    
    # 3. Create new branch ref
    url_create = f"{API_BASE}/git/refs"
    payload = {
        "ref": f"refs/heads/{branch}",
        "sha": source_sha
    }
    resp_create = requests.post(url_create, headers=headers, json=payload)
    if resp_create.status_code == 201:
        print(f"✅ Created branch '{branch}'.")
        return True
    else:
        print(f"❌ Failed to create branch: {resp_create.text}")
        return False

def sync_data_to_github():
    print(f"🔄 Starting Data Sync (Serverless Mode) to '{BRANCH_NAME}'...")
    
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN not found. Skipping sync.")
        return

    # 1. Ensure Branch Exists
    if not create_branch_if_missing(BRANCH_NAME):
        return

    # 2. Read Local File
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_path = os.path.join(base_dir, FILE_PATH)
    
    if not os.path.exists(abs_path):
        print(f"❌ File not found: {abs_path}")
        return

    with open(abs_path, "rb") as f:
        content = f.read()
    
    content_b64 = base64.b64encode(content).decode("utf-8")
    
    # 3. Get existing SHA (if update)
    sha = get_file_sha(FILE_PATH, BRANCH_NAME)
    
    # 4. Push (PUT Request)
    url = f"{API_BASE}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    message = f"Data Update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    payload = {
        "message": message,
        "content": content_b64,
        "branch": BRANCH_NAME
    }
    if sha:
        payload["sha"] = sha
        print(f"📝 Updating existing file (SHA: {sha[:7]})...")
    else:
        print("Mw Creating new file...")
        
    resp = requests.put(url, headers=headers, json=payload)
    
    if resp.status_code in [200, 201]:
        print(f"✅ Sync Successful! URL: {resp.json().get('content', {}).get('html_url')}")
    else:
        print(f"❌ Sync Failed ({resp.status_code}): {resp.text}")

if __name__ == "__main__":
    sync_data_to_github()
