
import json
from pathlib import Path
import datetime

# Construct Path
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "frontend" / "data"
AGENT_LOG_PATH = DATA_DIR / "agent_decision_log.json"

print(f"Testing write to: {AGENT_LOG_PATH}")

try:
    # Read existing
    if AGENT_LOG_PATH.exists():
        with open(AGENT_LOG_PATH, "r") as f:
            data = json.load(f)
            print(f"Current entries: {len(data)}")
    else:
        data = []

    # Append dummy
    dummy = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "analysis_summary": {"en": "TEST WRITE"},
        "actions": []
    }
    data.insert(0, dummy)
    
    # Write back
    with open(AGENT_LOG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    
    print("✅ Write successful!")

except Exception as e:
    print(f"❌ Write failed: {e}")
