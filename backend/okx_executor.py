import os
import json
import time
import hmac
import base64
import hashlib
import requests
import datetime
import math
from decimal import Decimal, ROUND_HALF_UP
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

    def round_step_size(self, value, step_size):
        """
        Round a value to the nearest multiple of step_size for OKX API compliance.
        """
        if not step_size or step_size <= 0: return value
        
        # Calculate precision based on step_size string representation
        d_step = Decimal(str(step_size))
        d_val = Decimal(str(value))
        
        rounded = (d_val / d_step).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * d_step
        
        # Extract precision for float conversion
        precision = abs(d_step.as_tuple().exponent) if "." in str(step_size) else 0
        fmt = "{:." + str(precision) + "f}"
        return float(fmt.format(rounded))

    def get_market_ticker(self, instId):
        """Get full ticker data (Ask/Bid/Last)"""
        res = requests.get(f"{self.base_url}/api/v5/market/ticker?instId={instId}")
        data = res.json()
        if data["code"] == "0":
            return data["data"][0]
        return None

    def get_instrument_info(self, instId):
        """
        Get contract info (ctVal, lotSz, tickSz) to convert USDT -> Contracts correctly.
        """
        if instId in self.instrument_cache:
            return self.instrument_cache[instId]

        res = requests.get(f"{self.base_url}/api/v5/public/instruments?instType=SWAP&instId={instId}")
        data = res.json()
        
        if data["code"] == "0" and data["data"]:
            info = data["data"][0]
            self.instrument_cache[instId] = {
                "ctVal": float(info["ctVal"]),
                "ctMult": float(info.get("ctMult", 1)),
                "minSz": float(info["minSz"]),
                "lotSz": float(info["lotSz"]),
                "tickSz": float(info["tickSz"])
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
        lotSz = info["lotSz"]
        # Approximate USD value of 1 contract
        one_contract_val = price * ctVal 
        
        contracts = amount_usd / one_contract_val
        # Round to nearest Lot Size
        sz = self.round_step_size(contracts, lotSz)
        
        if lotSz >= 1:
            sz = int(sz)
        
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

    def _get_portfolio_path(self):
        # Resolve path to frontend/data/portfolio_state.json
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "frontend", "data", "portfolio_state.json")

    def _load_shadow_state(self):
        from db_client import db
        state = db.get_data("portfolio_state")
        if state:
            return state
        # Default State
        return {
            "total_equity": 10000.0,
            "cash": 10000.0,
            "positions": [] # {symbol, size, entry_price, type}
        }

    def _save_shadow_state(self, state):
        from db_client import db
        try:
            db.save_data("portfolio_state", state)
        except Exception as e:
            print(f"⚠️ Failed to save shadow state: {e}")

    def execute_trade(self, symbol, action, amount_usd, leverage, stop_loss=None, take_profit=None):
        """
        Main entry point for AI Trader.
        """
        instId = f"{symbol}-USDT-SWAP"
        
        # Determine strict posSide for Dual Mode
        target_pos_side = "long" if "long" in action else "short" if "short" in action else "net"
        
        # 1. Get Ticker (Ask/Bid)
        ticker = self.get_market_ticker(instId)
        if not ticker:
            print(f"❌ Failed to get ticker for {instId}")
            return
            
        last_price = float(ticker['last'])
        ask_price = float(ticker['askPx'])
        bid_price = float(ticker['bidPx'])

        # 2. Calculate Size in Contracts
        sz = self.calculate_position_size(instId, amount_usd, last_price)
        
        # Smart Handling for Close Actions: If amount is 0, fetch current full position size
        if "close" in action and (sz <= 0 or amount_usd <= 0):
             if self.shadow_mode:
                 state = self._load_shadow_state()
                 for p in state["positions"]:
                     if p["symbol"] == symbol and (target_pos_side == "net" or p["type"] == target_pos_side):
                          sz = p["size"]
                          target_pos_side = p["type"]
                          print(f"🔍 [SHADOW] Auto-detected position size for closing: {sz} contracts")
                          break
             else:
                  # Real Mode: Fetch actual position from OKX to ensure full closure
                 raw_res = self._request("GET", f"/api/v5/account/positions?instId={instId}")
                 if raw_res.get("code") == "0" and raw_res.get("data"):
                      for p in raw_res["data"]:
                           # Match by position side (long/short/net) AND ensure it has a size > 0
                           if p.get("posSide") == target_pos_side or target_pos_side == "net":
                               if float(p.get("pos", 0)) != 0:
                                   sz = abs(float(p["pos"]))
                                   target_pos_side = p.get("posSide")
                                   print(f"🔍 [REAL] Auto-detected position size for closing: {sz} contracts ({target_pos_side})")
                                   break

        if sz <= 0:
            print(f"⚠️ Calculated size is 0 for ${amount_usd}. Minimum not met?")
            return

        print(f"🤖 Execution Request: {action} {symbol} | Last: {last_price} | Val: ${amount_usd} | Size: {sz} contracts")

        # 3. Determine Side & Limit Price
        if "close" in action:
            side = "sell" if ("long" in action or target_pos_side == "long") else "buy"
        else:
            side = "buy" if ("long" in action or target_pos_side == "long") else "sell"
            
        limit_px = ask_price if side == "buy" else bid_price # Simplified for shadow

        if self.shadow_mode:
            print(f"🌑 [SHADOW] Order: {side} {sz} contracts of {instId} @ ${limit_px}")
            
            # --- UPDATE SHADOW STATE ---
            state = self._load_shadow_state()
            
            # Fee simulation (0.05%)
            fee = amount_usd * 0.0005
            state["cash"] -= fee
            state["total_equity"] -= fee
            
            if "open" in action:
                # Deduct Cash (Margin)
                # Margin = Position Value / Leverage
                margin_required = amount_usd / leverage
                if state["cash"] < margin_required:
                     print(f"❌ [SHADOW] Insufficient Cash: ${state['cash']:.2f} < ${margin_required:.2f}")
                     return None
                     
                state["cash"] -= margin_required
                
                # Add Position
                new_pos = {
                    "symbol": symbol,
                    "instId": instId,
                    "type": "long" if "long" in action else "short",
                    "leverage": leverage,
                    "size": sz, # Contracts
                    "entry_price": limit_px,
                    "margin": margin_required,
                    "size_usd": amount_usd,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "timestamp": datetime.datetime.now().isoformat()
                }
                state["positions"].append(new_pos)
                print(f"✅ [SHADOW] Position Opened: {symbol} {action}")
                
            elif "close" in action:
                # Find Position
                pos_idx = -1
                for i, p in enumerate(state["positions"]):
                    if p["symbol"] == symbol:
                        pos_idx = i
                        break
                
                if pos_idx >= 0:
                    pos = state["positions"].pop(pos_idx)
                    # PnL Calc
                    # Long: (Exit - Entry) * Size * ContractVal
                    # Short: (Entry - Exit) * Size * ContractVal
                    # Need ContractVal... 
                    info = self.get_instrument_info(instId)
                    ctVal = info["ctVal"] if info else 0.01 # Fallback
                    
                    if pos["type"] == "long":
                        pnl = (limit_px - pos["entry_price"]) * pos["size"] * ctVal
                    else:
                        pnl = (pos["entry_price"] - limit_px) * pos["size"] * ctVal
                        
                    # Return Margin + PnL to Cash
                    return_amount = pos["margin"] + pnl
                    state["cash"] += return_amount
                    state["total_equity"] += pnl
                    print(f"✅ [SHADOW] Position Closed: {symbol}. PnL: ${pnl:.2f}")

                    # --- LOG TRADE HISTORY (Shadow Mode) ---
                    # Now we must record this closed trade to trade_history so frontend can see it
                    try:
                        from db_client import db
                        history = db.get_data("trade_history", [])

                        trade_record = {
                            "id": f"{symbol}_{int(time.time())}",
                            "symbol": symbol,
                            "type": pos["type"],
                            "entryPrice": pos["entry_price"],
                            "exitPrice": limit_px,
                            "amount": pos["size"], # contracts
                            "leverage": pos["leverage"],
                            "pnl": float(f"{pnl:.2f}"),
                            "pnlPercent": float(f"{((limit_px - pos['entry_price'])/pos['entry_price'] * 100 * pos['leverage'] if pos['type']=='long' else (pos['entry_price'] - limit_px)/pos['entry_price'] * 100 * pos['leverage']):.2f}"),
                            "entryTime": pos.get("timestamp", datetime.datetime.now().isoformat()), # Fallback
                            "exitTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "reason": "AI Decision (Shadow)" 
                        }
                        
                        history.append(trade_record)
                        
                        db.save_data("trade_history", history)
                        print(f"📝 [SHADOW] Appended trade to history: {trade_record['id']}")

                    except Exception as e:
                        print(f"⚠️ Failed to log shadow trade history: {e}")

                else:
                    print(f"⚠️ [SHADOW] No position found to close for {symbol}")

            self._save_shadow_state(state)
            return "SHADOW_ORDER_ID"

        # REAL MODE EXECUTION
        info = self.get_instrument_info(instId)
        tick_sz = info["tickSz"] if info else 0.01

        # 0. Set Leverage
        if "open" in action:
             self.set_leverage(instId, leverage, posSide=target_pos_side)

        if symbol in ["BTC", "ETH"]: SLIPPAGE_TOLERANCE = 0.002
        else: SLIPPAGE_TOLERANCE = 0.005

        if side == "buy": limit_px = ask_price * (1 + SLIPPAGE_TOLERANCE)
        else: limit_px = bid_price * (1 - SLIPPAGE_TOLERANCE)
        
        # Round to precision
        limit_px = self.round_step_size(limit_px, tick_sz)
        
        if "close" in action:
            # Force market order for closing to prevent hang-ups and add reduceOnly for safety
            payload = {
                "instId": instId, "tdMode": "isolated", "side": side,
                "ordType": "market", "sz": str(sz), "posSide": target_pos_side,
                "reduceOnly": "true"
            }
        else:
            # Limit order for opening
            payload = {
                "instId": instId, "tdMode": "isolated", "side": side,
                "ordType": "limit", "px": str(limit_px), "sz": str(sz), "posSide": target_pos_side
            }
        
        if (stop_loss and str(stop_loss) != "None") or (take_profit and str(take_profit) != "None"):
            # Calculate and round TP/SL
            algo_order = { "attachAlgoId": f"tpsl_{int(time.time())}", "tpOrdPx": "-1", "slOrdPx": "-1" }
            if take_profit and str(take_profit) != "None":
                try:
                    tp_val = self.round_step_size(float(take_profit), tick_sz)
                    algo_order["tpTriggerPx"] = str(tp_val)
                    algo_order["tpTriggerPxType"] = "last"
                except ValueError:
                    print(f"⚠️ Invalid take_profit format: {take_profit}. Skipping TP.")
            
            if stop_loss and str(stop_loss) != "None":
                sl_str = str(stop_loss).lower()
                try:
                    if "dynamic" in sl_str or "%" in sl_str:
                        # Auto-calculate the 5% dynamic stop loss
                        sl_float = limit_px * 0.95 if "long" in action else limit_px * 1.05
                    else:
                        sl_float = float(stop_loss)
                    sl_val = self.round_step_size(sl_float, tick_sz)
                    algo_order["slTriggerPx"] = str(sl_val)
                    algo_order["slTriggerPxType"] = "last"
                except Exception as e:
                    print(f"⚠️ Failed to parse stop_loss: {stop_loss}. Error: {e}")
                    
            if "slTriggerPx" in algo_order or "tpTriggerPx" in algo_order:
                payload["attachAlgoOrds"] = [algo_order]
        
        print(f"📡 Sending POST /api/v5/trade/order...")
        res = self._request("POST", "/api/v5/trade/order", payload)
        
        if res["code"] == "0":
            order_id = res["data"][0]["ordId"]
            print(f"✅ Order Placed: ID={order_id}")
            return order_id
            
        print(f"❌ Order Failed: {res.get('msg')}")
        return None

    def get_open_position_count(self):
        if self.shadow_mode:
            state = self._load_shadow_state()
            return len(state["positions"])
        
        res = self._request("GET", "/api/v5/account/positions?instType=SWAP")
        if res["code"] == "0": return len(res["data"])
        return 0

    def get_total_exposure(self):
        exposure = {'long': 0.0, 'short': 0.0}
        if self.shadow_mode:
            state = self._load_shadow_state()
            for p in state["positions"]:
                # Approx exposure = Size (contracts) * EntryPrice * CtVal ?? 
                # Or just stored size_usd? Stored `size_usd` is margin * leverage roughly.
                # Let's use stored size_usd for simplicity
                if p["type"] == "long": exposure['long'] += p.get("size_usd", 0)
                else: exposure['short'] += p.get("size_usd", 0)
            return exposure

        res = self._request("GET", "/api/v5/account/positions?instType=SWAP")
        if res["code"] == "0":
            for pos in res["data"]:
                notional = float(pos.get("notionalUsd", 0))
                side = pos.get("posSide")
                if side == "long": exposure['long'] += abs(notional)
                elif side == "short": exposure['short'] += abs(notional)
        return exposure

    def get_all_positions(self):
        """
        Get detailed list of all open positions.
        Returns standard format list for frontend.
        """
        if self.shadow_mode:
            state = self._load_shadow_state()
            # Map shadow positions to standard format
            mapped = []
            for p in state["positions"]:
                # Fetch current price for PnL calculation if possible, else use Entry
                # For shadow list, we might not have live price here unless we fetch ticker
                # Let's try to fetch ticker for PnL accuracy
                instId = p.get("instId", f"{p['symbol']}-USDT-SWAP")
                ticker = self.get_market_ticker(instId)
                current_price = float(ticker['last']) if ticker else p['entry_price']
                
                # Calc PnL
                entry_price = p['entry_price']
                size = p['size'] # Contracts
                # We need instrument info for contract value (ctVal)
                # If cached/fetching fails, assume 0.01 for ETH/BTC etc or usage logic
                # For simplicity in shadow view:
                # Value = Size * ContractVal * Price
                # But we stored 'size_usd' in execute_trade for shadow positions as approx
                
                # Let's simple calc:
                # PnL % = (Current - Entry) / Entry * Leverage (Long)
                if p['type'] == 'long':
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100 * p['leverage']
                    pnl_amt = (pnl_pct / 100) * p['margin']
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100 * p['leverage']
                    pnl_amt = (pnl_pct / 100) * p['margin']
                
                mapped.append({
                    "symbol": p["symbol"],
                    "instId": instId,
                    "leverage": p["leverage"],
                    "type": p["type"],
                    "entryPrice": entry_price,
                    "currentPrice": current_price,
                    "pnl": float(f"{pnl_amt:.2f}"),
                    "pnlPercent": float(f"{pnl_pct:.2f}"),
                    "amount": size, # contracts
                    "margin": p["margin"],
                    "stopLoss": p.get("stop_loss"),    # Return None if missing, Frontend handles '---'
                    "takeProfit": p.get("take_profit"), # Return None if missing
                    "name": p["symbol"] # Simple fallback
                })
            return mapped

        # REAL / DEMO MODE
        res = self._request("GET", "/api/v5/account/positions?instType=SWAP")
        
        # Also fetch pending Algo orders (SL/TP) to populate those fields
        # Note: API might not support comma-separated ordType, so we fetch sequentially.
        algo_map = {}
        for o_type in ["oco", "conditional", "trigger"]:
            try:
                res_algo = self._request("GET", f"/api/v5/trade/orders-algo-pending?instType=SWAP&ordType={o_type}")
                if res_algo["code"] == "0":
                    for algo in res_algo["data"]:
                        # algo structure: slTriggerPx, tpTriggerPx, instId
                        i_id = algo["instId"]
                        if i_id not in algo_map: algo_map[i_id] = {}
                        
                        # SL
                        if algo.get("slTriggerPx") and float(algo["slTriggerPx"]) > 0:
                            algo_map[i_id]["sl"] = float(algo["slTriggerPx"])
                        # TP
                        if algo.get("tpTriggerPx") and float(algo["tpTriggerPx"]) > 0:
                            algo_map[i_id]["tp"] = float(algo["tpTriggerPx"])
            except Exception as e:
                print(f"⚠️ Failed to fetch algo orders ({o_type}): {e}")

        mapped_real = []
        if res["code"] == "0":
            for pos in res["data"]:
                # OKX API Fields:
                # instId, avgPx (Entry), last (Mark), upl (Unrealized PnL), uplRatio (PnL%), lever
                
                sym = pos["instId"].split("-")[0]
                entry_px = float(pos.get("avgPx", 0))
                mark_px = float(pos.get("markPx", 0) or pos.get("last", 0))
                upl = float(pos.get("upl", 0))
                upl_ratio = float(pos.get("uplRatio", 0)) * 100 # OKX gives decimal usually? No, check docs. 
                # Docs: uplRatio is ratio. e.g. 0.1 for 10%. So * 100.
                
                side = pos.get("posSide") # long, short, net
                if side == "net":
                    # If net, determine by pos sign
                    sz = float(pos.get("pos", 0))
                    side = "long" if sz > 0 else "short"
                
                # Get instrument info for ctVal conversion (Contracts -> Tokens)
                info = self.get_instrument_info(pos["instId"])
                ct_val = info.get("ctVal", 1.0) if info else 1.0
                actual_amount = abs(float(pos.get("pos", 0))) * ct_val

                # Retrieve SL/TP from Algo Map
                sl = algo_map.get(pos["instId"], {}).get("sl")
                tp = algo_map.get(pos["instId"], {}).get("tp")

                mapped_real.append({
                    "symbol": sym,
                    "instId": pos["instId"],
                    "leverage": int(float(pos.get("lever", 1))),
                    "type": side,
                    "entryPrice": entry_px,
                    "currentPrice": mark_px,
                    "pnl": upl,
                    "pnlPercent": float(f"{upl_ratio:.2f}"),
                    "amount": str(actual_amount), # Actual tokens/size
                    "margin": float(pos.get("margin", 0) or pos.get("notionalUsd", 0)) / float(pos.get("lever", 1)), # Approx
                    "stopLoss": sl,
                    "takeProfit": tp,
                    "name": sym # Simple Name
                })
        return mapped_real

    def get_account_equity(self):
        """
        Get total account equity in USDT.
        """
        if self.shadow_mode:
            state = self._load_shadow_state()
            return state.get("total_equity", 0.0)
            
        # Get total balance
        res = self._request("GET", "/api/v5/account/balance")
        if res.get("code") == "0" and res.get("data"):
            data = res["data"][0]
            # totalEq is the most reliable metric for Unified Accounts
            eq = float(data.get("totalEq", 0))
            if eq == 0:
                # Fallback: check details for USDT specifically if totalEq is empty
                for details in data.get("details", []):
                    if details.get("ccy") == "USDT":
                        eq = float(details.get("eq", 0))
                        break
            return eq
        else:
            msg = res.get("msg", "Unknown Error")
            code = res.get("code", "Unknown")
            print(f"❌ [OKX API] Balance Fetch Failed: {msg} (Code: {code})")
        return 0.0

    def sync_trade_history(self):
        """
        [REAL MODE ONLY]
        Fetch past filled orders from OKX and update trade_history.json.
        This ensures the frontend shows actual trade history even if the bot restarts.
        """
        if self.shadow_mode:
            print("🌑 [SHADOW] Skip syncing history from OKX (using local simulation log).")
            return

        print("🔄 [REAL] Syncing trade history from OKX...")
        
        # 1. Fetch Orders History (Last 7 days for recent fills)
        # Using orders-history covers the most recent activity immediately.
        res = self._request("GET", "/api/v5/trade/orders-history?instType=SWAP&state=filled")
        
        if res["code"] != "0":
            print(f"❌ Failed to fetch OKX history: {res.get('msg')}")
            return

        okx_orders = res.get("data", [])
        if not okx_orders:
            print("ℹ️ No filled orders found in OKX history.")
            return

        # 2. Load existing local history to prevent duplicates
        from db_client import db
        local_history = db.get_data("trade_history", [])
        
        existing_ids = set(item['id'] for item in local_history)
        new_records = []

        # 3. Process OKX Orders -> Frontend Format
        for ord in okx_orders:
            # We only care about orders that REDUCED position (Closing trades)
            # Typically check 'reduceOnly' or side vs posSide.
            # Simplified: If raw side != posSide (e.g. buy short, sell long) -> Close?
            # Better: Check PnL. Only closing orders have realized PnL in fills?
            # OKX Orders History endpoint has 'pnl' field for the order.
            
            pnl = float(ord.get("pnl", 0))
            if pnl == 0 and ord.get("reduceOnly") != "true":
                # Probably an opening order, skip (we only show closed trades in history usually)
                continue

            # ID unique to this order
            trade_id = ord["ordId"]
            if trade_id in existing_ids:
                continue

            # Format
            symbol = ord["instId"].split("-")[0]
            # Map side: buy + long = Open? buy + short = Close?
            # OKX: side=buy, posSide=long -> Open Long
            # OKX: side=sell, posSide=long -> Close Long
            side = ord["side"]
            posSide = ord["posSide"]
            
            # Determine type
            if posSide == "long":
                trade_type = "long"
            elif posSide == "short":
                trade_type = "short"
            else:
                trade_type = side # Net mode fallback

            # Avg Price
            avg_px = float(ord.get("avgPx", 0))
            
            # For a closed order, avgPx is exitPrice.
            # Entry price is harder to get from just order history (need positions history).
            # We can approximate or just leave entryPrice same as exit if unknown, or 0.
            # Wait, user wants to see PnL.
            # OKX Order JSON has `pnl` (Realized PnL).
            
            # Calculate approx entry price using PnL formula if valid?
            # PnL = (Exit - Entry) * Size * ContractVal
            # We have PnL, Exit, Size. Can solve for Entry.
            # But we need ContractVal.
            
            sz = float(ord.get("sz", 0)) # Contracts
            
            # Attempt to get Entry Price
            # If PnL is available, perfect.
            entry_px = 0.0
            
            # Fetch instrument info for calc
            instId = ord["instId"]
            info = self.get_instrument_info(instId)
            ctVal = info["ctVal"] if info else 0.01

            if sz > 0 and ctVal > 0:
                # PnL = (Exit - Entry) * sz * ctVal (Long)
                # Entry = Exit - (PnL / (sz * ctVal))
                if trade_type == "long": # Sell to close
                    # Order is 'sell'
                    entry_px = avg_px - (pnl / (sz * ctVal))
                else: # Buy to close short
                    # PnL = (Entry - Exit) * sz * ctVal
                    # Entry = (PnL / (sz * ctVal)) + Exit
                    entry_px = (pnl / (sz * ctVal)) + avg_px
            
            # Calculate %
            pnl_percent = 0.0
            if entry_px > 0:
                try:
                    lever = int(float(ord.get("lever", 1)))
                    if trade_type == "long":
                        pnl_percent = ((avg_px - entry_px) / entry_px) * 100 * lever
                    else:
                        pnl_percent = ((entry_px - avg_px) / entry_px) * 100 * lever
                except ZeroDivisionError:
                    pnl_percent = 0.0

            # Time
            # uTime is unix ms
            ts_ms = int(ord.get("uTime", 0))
            exit_time_str = datetime.datetime.fromtimestamp(ts_ms/1000).strftime("%Y-%m-%d %H:%M:%S")

            record = {
                "id": trade_id,
                "symbol": symbol,
                "type": trade_type,
                "entryPrice": float(f"{entry_px:.4f}"),
                "exitPrice": avg_px,
                "amount": sz,
                "leverage": int(float(ord.get("lever", 1))),
                "pnl": float(f"{pnl:.2f}"),
                "pnlPercent": float(f"{pnl_percent:.2f}"),
                "entryTime": "---", # Hard to know exact open time from close order
                "exitTime": exit_time_str,
                "reason": "OKX Real Trade"
            }
            
            new_records.append(record)
            existing_ids.add(trade_id)

        # 4. Save if any new found
        if new_records:
            # Append new ones
            local_history.extend(new_records)
            # Sort by time desc?
            try:
                from db_client import db
                db.save_data("trade_history", local_history)
                print(f"✅ [REAL] Synced {len(new_records)} new trades from OKX.")
            except Exception as e:
                print(f"⚠️ Failed to save synced history: {e}")
        else:
            print("✅ [REAL] History is up to date.")
# Simple Test
if __name__ == "__main__":
    # Test in Shadow Mode
    executor = OKXExecutor(shadow_mode=True)
    # executor.execute_trade("ETH", "open_long", 100, 5)
    print(f"Shadow Open Positions: {executor.get_open_position_count()}")
    print(f"Shadow Exposure: {executor.get_total_exposure()}")
    print(f"Shadow Equity: ${executor.get_account_equity()}")
