
import os
import time
import hmac
import base64
import hashlib
import json
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_API_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

def sign(timestamp, method, request_path, body):
    message = str(timestamp) + method.upper() + request_path + str(body)
    mac = hmac.new(bytes(API_SECRET, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d)

def request_okx(method, path, params=None):
    url = "https://www.okx.com" + path
    timestamp = str(float(time.time()))[:-2]
    
    # For GET, params go into URL query string? No, checking docs.
    # Yes, manual construction for sig.
    
    if method == "GET" and params:
        # Simple param encoding
        q = "&".join([f"{k}={v}" for k,v in params.items()])
        path = f"{path}?{q}"
        url = "https://www.okx.com" + path

    signature = sign(timestamp, method, path, '')
    
    headers = {
        'OK-ACCESS-KEY': API_KEY,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': PASSPHRASE,
        'x-simulated-trading': '1' # DEMO MODE
    }
    
    print(f"📡 Sending {method} {url}...")
    try:
        resp = requests.request(method, url, headers=headers)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# 1. Check Positions
print("\n=== CHECKING POSITIONS ===")
pos_res = request_okx("GET", "/api/v5/account/positions?instType=SWAP")
print(json.dumps(pos_res, indent=2))

# 2. Check Algo Orders (Broad Search)
print("\n=== CHECKING ALGO ORDERS (Broad) ===")
# Try retrieving ALL pending algos
algo_res = request_okx("GET", "/api/v5/trade/orders-algo-pending?instType=SWAP&ordType=conditional,oco,trigger,move_order_stop")
print(json.dumps(algo_res, indent=2))
