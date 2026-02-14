
import os
import requests
import json
import time
import base64
import hmac
import hashlib
import datetime
import statistics
from dotenv import load_dotenv
import numpy as np
import pandas as pd
from technical_analysis import add_all_indicators, get_signal_history

# Load env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.env")
load_dotenv(dotenv_path=env_path)

API_KEY = os.getenv("OKX_API_KEY")
SECRET_KEY = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
BASE_URL = "https://www.okx.com"

class OKXDataClient:
    def __init__(self):
        self.api_key = API_KEY
        self.secret_key = SECRET_KEY
        self.passphrase = PASSPHRASE
        self.base_url = BASE_URL
        
    def _get_timestamp(self):
        # Format: ISO 8601 with milliseconds, e.g. 2020-12-08T09:08:57.715Z
        return datetime.datetime.utcnow().isoformat(timespec='milliseconds') + "Z"

    def _sign_request(self, timestamp, method, request_path, body=""):
        message = timestamp + method + request_path + str(body)
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    def _request(self, method, endpoint, params={}):
        if not self.api_key:
            raise ValueError("Missing OKX_API_KEY")

        # Sort params if needed, but requests handles query string
        # OKX requires the queryString to be exactly what is sent
        query = '&'.join([f"{k}={v}" for k, v in params.items()])
        request_path = endpoint + ("?" + query if query else "")
        
        timestamp = self._get_timestamp()
        signature = self._sign_request(timestamp, method, request_path)
        
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }
        
        try:
            url = self.base_url + request_path
            # print(f"DEBUG: Requesting {url}")
            r = requests.request(method, url, headers=headers, timeout=10)
            
            if r.status_code != 200:
                print(f"Error {r.status_code}: {r.text}")
                return None
                
            json_resp = r.json()
            if json_resp["code"] != "0":
                print(f"API Error {json_resp['code']}: {json_resp['msg']}")
                return None
                
            return json_resp["data"]
            
        except Exception as e:
            print(f"Exception during request: {e}")
            return None

    def calculate_rsi(self, prices, period=14):
        """Calculate RSI from a list of prices."""
        prices = np.array(prices)
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum()/period
        down = -seed[seed < 0].sum()/period
        
        if down == 0: return 100.0
        rs = up/down
        rsi = np.zeros_like(prices)
        rsi[:period] = 100. - 100./(1. + rs)

        for i in range(period, len(prices)):
            delta = deltas[i-1]
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta

            up = (up * (period - 1) + upval) / period
            down = (down * (period - 1) + downval) / period
            
            if down == 0: rs = 100.0
            else: rs = up/down
            
            rsi[i] = 100. - 100./(1. + rs)
            
        return float(rsi[-1])

    def get_market_metrics(self, symbol):
        """
        Fetches all necessary market metrics for the new strategy.
        Symbol: "ETH" or "SOL"
        """
        inst_id = f"{symbol}-USDT-SWAP"
        metrics = {
            "symbol": symbol,
            "price": 0,
            "rsi_4h": 50.0, # Default Neutral
            "volume_24h": 0,
            "volume_avg_30d": 0,
            "volume_ratio": 0,
            "oi_now": 0,
            "oi_avg_30d": 0, 
            "delta_oi_24h_percent": 0,
            "funding_rate": 0,
            "funding_rate_status": "NEUTRAL"
        }

        # 1. Ticker (Price & Current Volume)
        data = self._request("GET", "/api/v5/market/ticker", {"instId": inst_id})
        if data:
            ticker = data[0]
            metrics["price"] = float(ticker["last"])
            metrics["volume_24h"] = float(ticker["volCcy24h"]) # Volume in USDT
            try:
                open_price = float(ticker.get("sodUtc0", ticker.get("open24h", metrics["price"])))
                if open_price > 0:
                    metrics["change_24h"] = ((metrics["price"] - open_price) / open_price) * 100
                else:
                    metrics["change_24h"] = 0.0
            except:
                metrics["change_24h"] = 0.0
        
        # 2. Advanced Technicals (4H Candles)
        # Fetch 500 candles (approx 83 days) to cover >60 days context + SMA200
        # OKX limits usually 100-300. We fetch twice.
        limit_per_req = 300
        all_candles = []
        
        # First Batch (Latest)
        data1 = self._request("GET", "/api/v5/market/candles", {"instId": inst_id, "bar": "4H", "limit": str(limit_per_req)})
        if data1:
            all_candles.extend(data1)
            # Last candle timestamp
            last_ts = data1[-1][0]
            
            # Rate Limit Safety: Sleep briefly strictly to handle OKX limits (20 req/2s)
            time.sleep(0.1)
            
            # Second Batch (Older)
            data2 = self._request("GET", "/api/v5/market/candles", {"instId": inst_id, "bar": "4H", "after": last_ts, "limit": "200"})
            if data2:
                all_candles.extend(data2)
        else:
            # If data1 failed, we have nothing.
            print(f"⚠️ Warning: First batch of candles for {inst_id} was empty/failed.")
                
        data = all_candles
        # Ensure we have enough data for technicals (at least 50 for SMA50/EMAs to warmup)
        if data and len(data) > 50:
            try:
                # OKX returns [ts, o, h, l, c, vol, volCcy, valCcyQuote, confirm]
                # Convert to DataFrame
                df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'volCcy', 'volCcyQuote', 'confirm'])
                
                # Sort ascending (oldest first) for calc
                df = df.iloc[::-1].reset_index(drop=True)
                
                # Prepare input DF
                df_input = pd.DataFrame()
                df_input['ts'] = df['ts']
                df_input['open'] = df['open']
                df_input['high'] = df['high']
                df_input['low'] = df['low']
                df_input['close'] = df['close']
                df_input['volume'] = df['volCcyQuote'] # Volume in USDT (Quote)
                
                # Calculate All Indicators (modifies df_input in place)
                tech_values = add_all_indicators(df_input)
                
                # Merge into metrics dict
                metrics.update(tech_values)
                
                # Backward compatibility
                metrics["rsi_4h"] = tech_values.get("rsi_14", 50)
                
                # GET HISTORY (60 periods)
                metrics["history_60d"] = get_signal_history(df_input, limit=60)
                
            except Exception as e:
                import traceback
                print(f"⚠️ Tech Calc Failed for {symbol}: {e}")
                print(f"DEBUG: DF Shape: {df_input.shape if 'df_input' in locals() else 'No DF'}")
                traceback.print_exc()

        # 3. Funding Rate
        data = self._request("GET", "/api/v5/public/funding-rate", {"instId": inst_id})
        if data:
            val = float(data[0]["fundingRate"])
            metrics["funding_rate"] = val
            # Determine status
            if val > 0.0003: metrics["funding_rate_status"] = "EXTREME_BULLISH_CROWDED" # > 0.03% (High)
            elif val < -0.0003: metrics["funding_rate_status"] = "EXTREME_BEARISH_CROWDED"
            else: metrics["funding_rate_status"] = "NORMAL"

        # 4. Open Interest (Current)
        # 5. Open Interest History (30 Days) -> Calculate Delta & Avg
        data = self._request("GET", "/api/v5/rubik/stat/contracts/open-interest-history", {"instId": inst_id, "period": "1D", "limit": "30"})
        if data:
            # Data is [ts, oi, oiCcy]. Sorted latest first.
            latest = float(data[0][2]) # OI in Currency (e.g. ETH) 
            try:
                # Convert OI(Coin) to OI(USD) using current price
                # Or use data[0][1] (contracts) ? 
                # Contracts is safer for raw comparison, but user wants Value
                # Let's use Contracts for Ratio to avoid Price noise? 
                # No, Strategy usually uses USD value.
                metrics["oi_now"] = latest * metrics["price"]
                
                # Historical
                if len(data) >= 2:
                    yesterday = float(data[1][2]) # OI 24h ago record
                    # Or should we look at the 'open' of the candle?
                    # The API returns one record per Day. 
                    # Assuming data[0] is 'today so far' or 'yesterday closed'?
                    # Docs: "Sorted in descending order". data[0] is latest.
                    
                    # Calculate Delta 24h
                    # Simple approach: (Latest - Data[1])/Data[1]
                    metrics["delta_oi_24h_percent"] = ((latest - yesterday) / yesterday) * 100
                
                # Avg 30d
                all_oi = [float(x[2]) for x in data]
                metrics["oi_avg_30d"] = (sum(all_oi) / len(all_oi)) * metrics["price"]
                
            except Exception as e:
                print(f"Error calcing OI: {e}")

        # 6. Volume History (30 Days) -> Calculate Volume Ratio
        data = self._request("GET", "/api/v5/market/history-candles", {"instId": inst_id, "bar": "1D", "limit": "30"})
        if data:
            # [ts, o, h, l, c, vol, volCcy, ...]
            # volCcy is index 6. 
            all_vols = []
            for k in data:
                # k[6] is volCcy (USDT volume)
                all_vols.append(float(k[6]))
                
            if all_vols:
                avg_vol = sum(all_vols) / len(all_vols)
                metrics["volume_avg_30d"] = avg_vol
                if avg_vol > 0:
                    metrics["volume_ratio"] = metrics["volume_24h"] / avg_vol
                    
        return metrics

    def fetch_liquidation_data(self, uly="ETH-USDT", inst_type="SWAP"):
        """
        Fetch recent liquidation orders to gauge market pain.
        Returns: {'long_vol_usd': float, 'short_vol_usd': float} (Last 24h approx)
        """
        try:
            # OKX Public Liquidation Orders
            # We fetch last 100 orders and sum them up to get a snapshot of "Recent Pain"
            params = {
                "instType": inst_type,
                "uly": uly,
                "state": "filled",
                "limit": "100"
            }
            data = self._request("GET", "/api/v5/public/liquidation-orders", params)
            if not data:
                return {"long_vol_usd": 0, "short_vol_usd": 0}
            
            # Data structure: data is list of objects with 'details'
            long_liq = 0.0
            short_liq = 0.0
            
            for entry in data:
                # 'details' is a list of orders in that second
                if "details" in entry:
                    for order in entry["details"]:
                        side = order.get("side") or order.get("posSide") # 'buy' or 'sell' usually, or look at docs
                        # Docs: side 'buy' means liquidated shorts? No.
                        # Actually 'posSide' -> 'long' or 'short' is clearer in V5 API if available.
                        # Re-checking API docs: V5 returns 'posSide' ('long', 'short').
                        # Also 'sz' (size) and 'bkPx' (bankruptcy price)
                        
                        pos_side = order.get("posSide")
                        sz = float(order.get("sz", 0))
                        price = float(order.get("bkPx", 0))
                        vol_usd = sz * price # Approx value
                        
                        if pos_side == "long":
                            long_liq += vol_usd
                        elif pos_side == "short":
                            short_liq += vol_usd
                            
            return {
                "long_vol_usd": long_liq,
                "short_vol_usd": short_liq,
                "status": "High Pain" if (long_liq + short_liq) > 1000000 else "Normal"
            }
            
        except Exception as e:
            print(f"Error fetching liquidations: {e}")
            return {"long_vol_usd": 0, "short_vol_usd": 0}

# Singleton instance
client = OKXDataClient()

def get_strategy_metrics(symbol):
    """
    Public wrapper to get metrics for a symbol.
    """
    try:
        return client.get_market_metrics(symbol)
    except Exception as e:
        print(f"Failed to get market metrics for {symbol}: {e}")
        return None

if __name__ == "__main__":
    # Self Test
    print("Testing Market Data Module...")
    res = get_strategy_metrics("ETH")
    print(json.dumps(res, indent=2))
