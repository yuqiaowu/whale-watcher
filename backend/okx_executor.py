import os
import json
import time
import hmac
import base64
import hashlib
import requests
import datetime
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

class OKXExecutor:
    """
    Handles execution of trades on OKX V5 API.
    Supports both REAL execution and SHADOW mode (dry-run).
    """
    def __init__(self, shadow_mode=None):
        self.api_key = os.getenv("OKX_API_KEY")
        self.secret_key = os.getenv("OKX_SECRET_KEY")
        self.passphrase = os.getenv("OKX_PASSPHRASE")
        self.base_url = "https://www.okx.com"
        
        # Determine Mode
        env_mode = os.getenv("TRADING_MODE", "SHADOW").upper()
        
        # If user explicitly passed a bool to init, respect it (legacy compat)
        if shadow_mode is not None:
             self.shadow_mode = shadow_mode
        else:
             # "REAL" or "DEMO" -> shadow_mode = False (Network Enabled)
             # "SHADOW" -> shadow_mode = True (Network Blocked)
             self.shadow_mode = False if env_mode in ["REAL", "DEMO"] else True
             
        self.trading_mode = env_mode # store for header check
        
        print(f"🤖 OKXExecutor initialized in {self.trading_mode} mode (Shadow={self.shadow_mode})")
        self.instrument_cache = {} # Cache for ctVal (contract value)

        if not self.api_key:
            print("⚠️ OKX_API_KEY not found. Executor will fail in REAL mode.")

    def _get_timestamp(self):
        return datetime.datetime.utcnow().isoformat("T", "milliseconds") + "Z"

    def _sign(self, timestamp, method, request_path, body):
        message = str(timestamp) + str(method) + str(request_path) + str(body)
        mac = hmac.new(
            bytes(self.secret_key, encoding="utf-8"),
            bytes(message, encoding="utf-8"),
            digestmod=hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _request(self, method, path, params=None):
        """
        Internal helper to send signed requests to OKX.
        """
        url = self.base_url + path
        timestamp = self._get_timestamp()
        body = json.dumps(params) if params else ""
        
        sign = self._sign(timestamp, method, path, body)
        
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        
        # Demo Trading Header
        if self.trading_mode == "DEMO":
            headers["x-simulated-trading"] = "1"
        
        # Simulation flag in header is custom logic, but standard OKX also has a separate demo trading URL.
        # Here we just use the shadow mode boolean to block requests.
        
        print(f"📡 Sending {method} {path}...")
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            else:
                response = requests.post(url, headers=headers, data=body)
                
            return response.json()
        except Exception as e:
            return {"code": "-1", "msg": f"Network Error: {str(e)}"}

    def get_market_ticker(self, instId):
        """Get full ticker data (Ask/Bid/Last)"""
        res = requests.get(f"{self.base_url}/api/v5/market/ticker?instId={instId}")
        data = res.json()
        if data["code"] == "0":
            return data["data"][0]
        return None

    def get_instrument_info(self, instId):
        """
        Get contract face value (ctVal) to convert USDT -> Contracts.
        Example: BTC-USDT-SWAP, ctVal = 0.01 (1 contract = 0.01 BTC)
        """
        if instId in self.instrument_cache:
            return self.instrument_cache[instId]

        res = requests.get(f"{self.base_url}/api/v5/public/instruments?instType=SWAP&instId={instId}")
        data = res.json()
        
        if data["code"] == "0" and data["data"]:
            info = data["data"][0]
            # ctVal: Contract value (e.g., 0.01 BTC)
            # ctMult: Multiplier (usually 1 for crypto)
            self.instrument_cache[instId] = {
                "ctVal": float(info["ctVal"]),
                "ctMult": float(info.get("ctMult", 1)),
                "minSz": float(info["minSz"])
            }
            return self.instrument_cache[instId]
        return None

    def calculate_position_size(self, instId, amount_usd, price):
        """
        Convert USDT Amount -> Number of Contracts (sz)
        Logic:
           Contracts = (Amount_USD / Price) / ctVal
        """
        info = self.get_instrument_info(instId)
        if not info:
            print(f"⚠️ Could not fetch instrument info for {instId}")
            return 0
        
        ctVal = info["ctVal"]
        # Approximate USD value of 1 contract
        one_contract_val = price * ctVal 
        
        contracts = amount_usd / one_contract_val
        sz = int(contracts)
        
        # --- SMART ROUND UP LOGIC ---
        if sz == 0 and amount_usd > 50:
            equity = self.get_account_equity()
            # Safety Rule: 1 contract shouldn't be more than 10% of total equity
            if equity > 0 and (one_contract_val / equity) < 0.10: 
                print(f"💡 Smart Round-Up: {instId} alloc ${amount_usd} < 1 contract (${one_contract_val:.2f}). Bumped to 1.")
                sz = 1
            else:
                print(f"⚠️ {instId} alloc ${amount_usd} too small for 1 contract (${one_contract_val:.2f}). Skipped.")

        return sz

    def set_leverage(self, instId, leverage, posSide=None):
        """
        Set leverage for a specific instrument.
        Corresponds to POST /api/v5/account/set-leverage
        """
        if self.shadow_mode:
            print(f"🌑 [SHADOW] Set Leverage: {instId} -> {leverage}x (Cross, Side={posSide})")
            return True

        payload = {
            "instId": instId,
            "lever": str(leverage),
            "mgnMode": "isolated"
        }
        if posSide:
            payload["posSide"] = posSide
            
        res = self._request("POST", "/api/v5/account/set-leverage", payload)
        if res["code"] == "0":
            print(f"✅ Leverage set to {leverage}x for {instId} ({posSide})")
            return True
        elif res["code"] == "51000" and posSide: 
            # Fallback: If 'long/short' fails (maybe account is Net mode), try without posSide
            print(f"⚠️ Set leverage failed with posSide={posSide}. Retrying generic set...")
            del payload["posSide"]
            res_retry = self._request("POST", "/api/v5/account/set-leverage", payload)
            if res_retry["code"] == "0":
                 print(f"✅ Leverage set to {leverage}x for {instId} (Generic)")
                 return True
            else:
                 print(f"❌ Failed to set leverage (Retry): {res_retry['msg']}")
                 return False
        else:
            print(f"❌ Failed to set leverage: {res['msg']} (Code: {res['code']})")
            return False

    def execute_trade(self, symbol, action, amount_usd, leverage, stop_loss=None, take_profit=None):
        """
        Main entry point for AI Trader.
        """
        instId = f"{symbol}-USDT-SWAP"
        
        # Determine strict posSide for Dual Mode
        target_pos_side = "long" if "long" in action else "short" if "short" in action else "net"
        # If 'close', we don't strictly need to set leverage, but good practice to keep consistent context
        
        # 0. Set Leverage First (with explicit side)
        # Only set if opening (optimization)
        if "open" in action:
             self.set_leverage(instId, leverage, posSide=target_pos_side)
        
        # 1. Get Ticker (Ask/Bid)
        ticker = self.get_market_ticker(instId)
        if not ticker:
            print(f"❌ Failed to get ticker for {instId}")
            return

        last_price = float(ticker['last'])
        ask_price = float(ticker['askPx'])
        bid_price = float(ticker['bidPx'])

        # 2. Calculate Size in Contracts (Use 'last' for approximation)
        sz = self.calculate_position_size(instId, amount_usd, last_price)
        if sz <= 0:
            print(f"⚠️ Calculated size is 0 for ${amount_usd}. Minimum not met?")
            return

        print(f"🤖 Execution Request: {action} {symbol} | Last: {last_price} | Val: ${amount_usd} | Size: {sz} contracts")

        # 3. Determine Side & Limit Price
        side = "buy" if "long" in action else "sell"
        limit_px = 0
        
        # DYNAMIC SLIPPAGE PROTECTION
        if symbol in ["BTC", "ETH"]:
            SLIPPAGE_TOLERANCE = 0.002 # 0.2%
        else:
            SLIPPAGE_TOLERANCE = 0.005 # 0.5% for SOL etc.

        if side == "buy":
            # Buy Limit = Best Ask * (1 + Slippage)
            # Meaning: I am willing to buy up to this price
            limit_px = ask_price * (1 + SLIPPAGE_TOLERANCE)
        else:
            # Sell Limit = Best Bid * (1 - Slippage)
            # Meaning: I am willing to sell down to this price
            limit_px = bid_price * (1 - SLIPPAGE_TOLERANCE)
            
        # Round price (naive rounding, ideally should use tickSz from instrument info)
        limit_px = round(limit_px, 2) 

        if self.shadow_mode:
            print(f"🌑 [SHADOW] Order: {side} {sz} contracts of {instId}")
            print(f"   Type: LIMIT (Protected)")
            print(f"   Slippage Buf: {SLIPPAGE_TOLERANCE*100}%")
            print(f"   Limit Px: {limit_px} (vs Market: {ask_price if side=='buy' else bid_price})")
            return {
                "ordId": "SHADOW_12345",
                "clOrdId": f"ai_{int(time.time())}",
                "sCode": "0",
                "msg": "Shadow Execution Success"
            }



        # 5. Place Limit Order
        payload = {
            "instId": instId,
            "tdMode": "isolated",
            "side": side,
            "ordType": "limit", 
            "px": str(limit_px), 
            "sz": str(sz),
            "posSide": target_pos_side
        }

        # Attach One-Cancels-Other (TPSL) if provided
        if stop_loss or take_profit:
            algo_order = {
                "attachAlgoId": f"tpsl_{int(time.time())}",
                "tpOrdPx": "-1", # Market Price
                "slOrdPx": "-1"  # Market Price
            }
            if take_profit:
                algo_order["tpTriggerPx"] = str(take_profit)
                # OKX requires Trigger Px Type (Last/Index/Mark). Default usually Last.
                algo_order["tpTriggerPxType"] = "last"
            
            if stop_loss:
                algo_order["slTriggerPx"] = str(stop_loss)
                algo_order["slTriggerPxType"] = "last"
            
            # attachAlgoOrds expects a List of objects
            payload["attachAlgoOrds"] = [algo_order]
        
        print(f"📡 Sending POST /api/v5/trade/order...")
        res = self._request("POST", "/api/v5/trade/order", payload)
        
        if res["code"] == "0":
            order_id = res["data"][0]["ordId"]
            print(f"✅ Order Placed: ID={order_id}")
            return order_id
        
        # --- RETRY LOGIC FOR NET MODE (ONE-WAY) ---
        # If failed due to posSide error (51000) or mode mismatch, try 'net' mode
        error_code = res.get("code")
        error_msg = res.get("data", [{}])[0].get("sMsg", "") if res.get("data") else res.get("msg", "")
        
        if error_code in ["1", "51000"] and ("posSide" in error_msg or "mode" in error_msg):
            print(f"⚠️ Initial Order Failed ({error_msg}). Retrying without posSide param (Auto-Detect Mode)...")
            if "posSide" in payload:
                del payload["posSide"]
            else:
                # If it wasn't there (shouldn't happen), try 'net' as last resort
                payload["posSide"] = "net"
            
            # Retry Request
            res_retry = self._request("POST", "/api/v5/trade/order", payload)
            if res_retry["code"] == "0":
                 order_id = res_retry["data"][0]["ordId"]
                 print(f"✅ Retry Order Placed (Net Mode): ID={order_id}")
                 return order_id
            else:
                 print(f"❌ Retry Failed: {res_retry.get('msg')} | {res_retry.get('data')}")
                 
        else:
            print(f"❌ Order Failed: {res['msg']} (Code: {res['code']})")
            if "data" in res and res["data"]:
                 print(f"   Details: {res['data']}")
        return None

    def get_open_position_count(self):
        """
        Get number of currently open positions.
        Used for Risk Management (Max Positions).
        """
        if self.shadow_mode:
            # In shadow mode, we can't easily know "shadow positions" without a DB.
            # For now, assume 0 to allow trading logic to flow.
            return 0 

        res = self._request("GET", "/api/v5/account/positions?instType=SWAP")
        if res["code"] == "0":
            return len(res["data"]) # List of positions
        return 0

    def get_total_exposure(self):
        """
        Get total notional USD value of Longs and Shorts.
        Returns: {'long': 1200.0, 'short': 500.0}
        """
        exposure = {'long': 0.0, 'short': 0.0}
        
        if self.shadow_mode:
            # Mock exposure for shadow mode
            return exposure

        res = self._request("GET", "/api/v5/account/positions?instType=SWAP")
        if res["code"] == "0":
            for pos in res["data"]:
                # notionalUsd is the position value
                notional = float(pos.get("notionalUsd", 0))
                # posSide: long/short. OR use 'side' if net mode.
                # In net mode, if size > 0 it is long (usually).
                # But V5 usually returns 'posSide'.
                side = pos.get("posSide") # long, short, net
                
                # If 'net', we check valid logic or amount sign?
                # Usually 'net' mode with 'pos' > 0 is long, < 0 is short?
                # Let's rely on 'posSide' first as we set 'mgnMode' to cross execution.
                
                if side == "long":
                    exposure['long'] += abs(notional)
                elif side == "short":
                    exposure['short'] += abs(notional)
                elif side == "net":
                    # Fallback for net mode
                    if float(pos.get("pos", 0)) > 0:
                         exposure['long'] += abs(notional)
                    else:
                         exposure['short'] += abs(notional)
                         
        return exposure

    def get_account_equity(self):
        """
        Get total account equity in USDT.
        """
        if self.shadow_mode:
            return 10000.0 # Mock $10k
            
        res = self._request("GET", "/api/v5/account/balance?ccy=USDT")
        if res["code"] == "0" and res["data"]:
            # details[0].eq is equity
            return float(res["data"][0]["details"][0]["eq"])
        return 1.0 # Avoid division by zero

# Simple Test
if __name__ == "__main__":
    # Test in Shadow Mode
    executor = OKXExecutor(shadow_mode=True)
    # executor.execute_trade("ETH", "open_long", 100, 5)
    print(f"Shadow Open Positions: {executor.get_open_position_count()}")
    print(f"Shadow Exposure: {executor.get_total_exposure()}")
    print(f"Shadow Equity: ${executor.get_account_equity()}")
