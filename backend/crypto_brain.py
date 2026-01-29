import os
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from moralis import evm_api
import google.generativeai as genai

# Load environment variables
# Load environment variables
# Use absolute path relative to this script to ensure proper loading regardless of CWD
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.env")
load_dotenv(dotenv_path=env_path)

MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
MORSLID_API_KEY_2 = os.getenv("MORSLID_API_KEY_2") # Handle user typo
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# Key Rotation Logic
API_KEYS = [k for k in [MORALIS_API_KEY, MORSLID_API_KEY_2] if k]
CURRENT_KEY_IDX = 0

def get_current_key():
    if not API_KEYS: return None
    return API_KEYS[CURRENT_KEY_IDX % len(API_KEYS)]

def rotate_key():
    global CURRENT_KEY_IDX
    print(f"DEBUG: Switching API Key from index {CURRENT_KEY_IDX}...")
    CURRENT_KEY_IDX = (CURRENT_KEY_IDX + 1) % len(API_KEYS)
    print(f"DEBUG: New API Key index: {CURRENT_KEY_IDX}")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Configuration
MIN_VALUE_USD = 50000  # ETH Threshold
MIN_VALUE_USD_SOL = 5000 # SOL Threshold (Reverted to filter noise)
CHAIN = "eth"

# Solana Configuration
SOLANA_TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112", # Wrapped SOL
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
}



# Known Exchange Addresses (Simplified for MVP)
EXCHANGES = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "Tether Treasury",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH Contract",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC Contract",
    "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK Contract",
    "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": "SHIB Contract",
    "0x6982508145454ce325ddbe47a25d4ec3d2311933": "PEPE Contract",
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503": "Binance 16",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 17",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX 3",
    "0x559432e18b281731c054cd703d4b49872be4ed53": "OKX 5",
    "0x5041ed759dd4afc3a72b8192c143f72f4724081a": "Kraken 4",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase 10",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase 2",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Bybit",
    "0xa7efae728d2936e78bda97dc267687568dd593f3": "KuCoin 6",
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe": "Gate.io",
    "0x61edcdf5bb737adffe5043706e7c5bb1f1a56eea": "Huobi 10",
    "0x876eabf441b2ee5b5b0554fd502a8e0600950cfa": "Bitfinex 3",
    "0x75e89d5979e4f6fba9f97c104c2f0afb3f1dcb88": "MEXC",
    "0x6262998ced04146fa42253a5c0af90ca02dfd2a3": "Crypto.com",
    "0x99c9fc46f92e8a1c0dqc1b9742442e525704533": "Optimism Gateway",
    "0x8315177ab297ba92a06054ce80a67ed4dbd7ed3a": "Arbitrum Bridge",
    "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7": "Hyperliquid Bridge"
}

# Token Contracts to Watch
TOKENS = {
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "WETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "WBTC": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    "SHIB": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce",
    "PEPE": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
    "LINK": "0x514910771af9ca656af840dff83e8264ecf986ca"
}

STABLECOINS = ["USDT", "USDC"]

# Token Decimals
TOKEN_DECIMALS = {
    "USDT": 6,
    "USDC": 6,
    "WBTC": 8,
    "WETH": 18,
    "SHIB": 18,
    "PEPE": 18,
    "LINK": 18
}

def get_token_price(address):
    """Fetch token price in USD from Moralis."""
    try:
        result = evm_api.token.get_token_price(
            api_key=MORALIS_API_KEY,
            params={"address": address, "chain": CHAIN}
            # Moralis SDK doesn't easily expose timeout param in this method wrapper?
            # It seems evm_api uses requests under the hood but might not pass kwargs.
            # Let's check generic requests usages first.
        )
        return result["usdPrice"]
    except Exception as e:
        print(f"Error fetching price for {address}: {e}")
        return 0

def fetch_large_transfers():
    """Fetch recent large transfers for tracked tokens (ETH)."""
    # Ensure global EXCHANGES keys are lowercase for matching
    global EXCHANGES
    EXCHANGES = {k.lower(): v for k, v in EXCHANGES.items()}
    
    all_transfers = []
    
    print("Fetching data from Etherscan (Transfer Events)...")
    
    # Use Etherscan V2 API
    etherscan_url = "https://api.etherscan.io/v2/api"
    
    for symbol, address in TOKENS.items():
        print(f"Scanning {symbol} via Etherscan...")
        try:
            # 1. Get Token Price (Still use Moralis for Price)
            price = get_token_price(address)
            if price == 0: 
                print(f"Skipping {symbol} due to missing price.")
                continue
            
            # 2. Get Transfers via Etherscan
            # Use 'tokentx' endpoint: https://docs.etherscan.io/api-endpoints/accounts#get-a-list-of-erc20-token-transfer-events-by-address-on-ethereum
            # Although docs say it filters by 'address', testing showed it works for contractaddress only if address is omitted or same.
            # Actually, standard way for Contract Events is getLogs, but tokentx is parsed.
            # My test 'debug_etherscan.py' confirmed tokentx works for the contract.

            params = {
                "chainid": "1",
                "module": "account",
                "action": "tokentx",
                "contractaddress": address,
                "page": 1,
                "offset": 100, # Fetch last 100 txs (should cover > 10 mins usually)
                "sort": "desc",
                "apikey": ETHERSCAN_API_KEY
            }

            try:
                response = requests.get(etherscan_url, params=params, timeout=30)
                data = response.json()
                
                if data["status"] == "1" and isinstance(data["result"], list):
                    for tx in data["result"]:
                        # Etherscan result fields: 
                        # timeStamp, hash, from, to, value, tokenDecimal
                        
                        try:
                            decimals = int(tx.get("tokenDecimal", TOKEN_DECIMALS.get(symbol, 18)))
                            amount = float(tx["value"]) / (10 ** decimals)
                            amount_usd = amount * price
                            
                            # Filter Whales
                            if amount_usd >= MIN_VALUE_USD:
                                from_addr = tx["from"].lower()
                                to_addr = tx["to"].lower()
                                
                                # Use lower() for lookup just in case, though keys should be lower
                                from_label = EXCHANGES.get(from_addr, from_addr[:6] + "...")
                                to_label = EXCHANGES.get(to_addr, to_addr[:6] + "...")
                                
                                is_exchange_in = to_addr in EXCHANGES
                                is_exchange_out = from_addr in EXCHANGES
                                
                                signal = "NEUTRAL"
                                if symbol in STABLECOINS:
                                    if is_exchange_in: signal = "BULLISH_INFLOW"
                                    if is_exchange_out: signal = "BEARISH_OUTFLOW"
                                else:
                                    if is_exchange_in: signal = "BEARISH_INFLOW"
                                    if is_exchange_out: signal = "BULLISH_OUTFLOW"

                                # Convert Etherscan timestamp (epoch str) to ISO
                                ts_epoch = int(tx["timeStamp"])
                                ts_iso = datetime.utcfromtimestamp(ts_epoch).strftime("%Y-%m-%dT%H:%M:%S.000Z")

                                all_transfers.append({
                                    "hash": tx["hash"],
                                    "timestamp": ts_iso,
                                    "symbol": symbol,
                                    "amount": amount,
                                    "amount_usd": amount_usd,
                                    "from": from_addr,
                                    "to": to_addr,
                                    "from_label": from_label,
                                    "to_label": to_label,
                                    "signal": signal,
                                    "chain": "ETH"
                                })
                        except Exception as e:
                            print(f"Error parsing tx {tx.get('hash')}: {e}")
                            continue
                            
                else:
                    print(f"Etherscan error/empty for {symbol}: {data.get('message')}")
                    
            except Exception as e:
                print(f"Error fetching Etherscan for {symbol}: {e}")

        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            
        # Rate limiting: Etherscan free tier is 5 calls/sec, so strict sleep not needed but good for safety
        time.sleep(0.2)
    # Deduplication and Loop Detection
    cleaned_transfers = []
    seen_txs = {} # Map (hash, symbol, amount) -> index in cleaned_transfers

    for tx in all_transfers:
        key = (tx['hash'], tx['symbol'], tx['amount'])
        
        if key in seen_txs:
            idx = seen_txs[key]
            existing = cleaned_transfers[idx]
            
            # Check for Loop: A->B and B->A
            if existing['from'] == tx['to'] and existing['to'] == tx['from']:
                existing['pattern'] = 'INTERNAL_LOOP'
                existing['signal'] = 'NEUTRAL' # Force neutral
                # Merge: Do not append the new one
                continue
            
            # Check for Exact Duplicate
            if existing['from'] == tx['from'] and existing['to'] == tx['to']:
                continue
                
            # Otherwise, append
            cleaned_transfers.append(tx)
        else:
            seen_txs[key] = len(cleaned_transfers)
            cleaned_transfers.append(tx)
            
    all_transfers = cleaned_transfers

    # Sort by time desc
    all_transfers.sort(key=lambda x: x["timestamp"], reverse=True)
    return all_transfers

def get_solana_price(address):
    """Fetch Solana token price in USD."""
    try:
        # Use Moralis Token API for price
        # Use Moralis Token API for price
        url = f"https://solana-gateway.moralis.io/token/mainnet/{address}/price"
        headers = {"X-API-Key": get_current_key()}
        response = requests.get(url, headers=headers, timeout=30)
        data = response.json()
        return data.get("usdPrice", 0)
    except Exception as e:
        print(f"Error fetching price for {address}: {e}")
        return 0

def fetch_solana_swaps():
    """Fetch large swaps for Solana tokens."""
    all_swaps = []
    
    headers = {
        "X-API-Key": get_current_key()
    }
    
    # Pre-fetch prices
    prices = {}
    for symbol, address in SOLANA_TOKENS.items():
        prices[symbol] = get_solana_price(address)
        print(f"Price of {symbol}: ${prices[symbol]:.4f}")
    
    for symbol, address in SOLANA_TOKENS.items():
        print(f"Scanning Solana {symbol}...")
        try:
            url = f"https://solana-gateway.moralis.io/token/mainnet/{address}/swaps"
            params = {
                "limit": 100, 
            }
            
            # Fetch 10 pages (~1000 txs) to capture more history given Solana's high throughput
            # This is a trade-off: more API calls vs better data coverage
            for _ in range(10):
                # Retry loop for SOL requests
                max_retries = len(API_KEYS) + 1
                response = None
                for attempt in range(max_retries):
                    # Update header with potentially new key
                    headers["X-API-Key"] = get_current_key()
                    response = requests.get(url, headers=headers, params=params, timeout=30)
                    
                    if response.status_code in [401, 429]:
                         print(f"SOL API Quota hit. Rotating...")
                         rotate_key()
                         continue
                    else:
                        break
                
                if not response: break
                
                data = response.json()
                
                if "result" in data:
                    for swap in data["result"]:
                        # Determine which side is our token
                        bought_addr = swap["bought"]["address"]
                        sold_addr = swap["sold"]["address"]
                        
                        if bought_addr == address:
                            # User BOUGHT our token (Inflow to Wallet = Outflow from Pool)
                            # Logic: Buy = Bullish = Outflow (from exchange/pool perspective)
                            raw_amount = float(swap["bought"]["amount"])
                            signal = "BULLISH_OUTFLOW" 
                            if symbol in ["USDC", "USDT"]:
                                # Buying USDC = Selling Token = Bearish? No, this is just receiving USDC.
                                # If we are tracking USDC, and user BOUGHT USDC (swapped token for USDC), that is selling the token.
                                # So USDC Inflow to Wallet = Cash Out = Bearish Outflow?
                                # Wait, for Stablecoins:
                                # In to Exchange = Buy Power (Bullish Inflow)
                                # Out from Exchange = Cash Out (Bearish Outflow)
                                # Here: User Wallet receives USDC. This is "Out from Pool". 
                                # So it's "Cash Out" -> BEARISH_OUTFLOW.
                                signal = "BEARISH_OUTFLOW" 
                                
                        elif sold_addr == address:
                            # User SOLD our token (Outflow from Wallet = Inflow to Pool)
                            # Logic: Sell = Bearish = Inflow (to exchange/pool perspective)
                            raw_amount = float(swap["sold"]["amount"])
                            signal = "BEARISH_INFLOW"
                            if symbol in ["USDC", "USDT"]:
                                # Selling USDC = Buying Token = Bullish.
                                # User sends USDC to Pool.
                                # In to Pool = Buy Power -> BULLISH_INFLOW.
                                signal = "BULLISH_INFLOW" 
                        else:
                            continue

                        # Calculate USD Value Manually
                        price = prices.get(symbol, 0)
                        amount_usd = raw_amount * price
                        
                        # Fallback to API value if manual calc is 0
                        if amount_usd == 0:
                            amount_usd = float(swap.get("totalValueUsd", 0))

                        if amount_usd < MIN_VALUE_USD_SOL:
                            continue
                            
                        # Format for frontend
                        all_swaps.append({
                            "hash": swap["transactionHash"],
                            "timestamp": swap["blockTimestamp"],
                            "symbol": symbol,
                            "amount": raw_amount,
                            "amount_usd": amount_usd,
                            "from": swap["walletAddress"],
                            "to": swap["pairAddress"], 
                            "from_label": swap["walletAddress"][:6] + "...",
                            "to_label": swap.get("exchangeName", "DEX"),
                            "signal": signal,
                            "chain": "SOL"
                        })
                
                # Pagination
                if "cursor" in data and data["cursor"]:
                    params["cursor"] = data["cursor"]
                else:
                    break
                    
        except Exception as e:
            print(f"Error fetching Solana {symbol}: {e}")
        
        # Rate limiting: Sleep 1s between tokens 
        time.sleep(1)
            
    # Sort by time desc
    all_swaps.sort(key=lambda x: x["timestamp"], reverse=True)
    return all_swaps

def fetch_fear_greed_index():
    """Fetch Bitcoin Fear & Greed Index from alternative.me."""
    try:
        url = "https://api.alternative.me/fng/"
        response = requests.get(url, timeout=10)
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            item = data["data"][0]
            return {
                "value": int(item["value"]),
                "value_classification": item["value_classification"]
            }
    except Exception as e:
        print(f"Error fetching Fear & Greed Index: {e}")
    
    return {"value": 50, "value_classification": "Neutral"} # Fallback

def analyze_transfers(transfers):
    """Calculate sentiment score, aggregate metrics, and top whale for both 7d and 24h."""
    
    # Initialize helpers for empty stats
    def init_stats():
        return {
            "sentiment_score": 0,
            "stablecoin_net_flow": 0,
            "token_net_flow": 0,
            "whale_count": 0,
            "avg_tx_size": 0,
            "total_volume": 0,
            "top_whale": {"address": "N/A", "volume": 0, "label": "N/A"}
        }

    stats_7d = init_stats()
    stats_24h = init_stats()

    if not transfers:
        return {"stats_7d": stats_7d, "stats_24h": stats_24h}

    # Helpers for 24h calculation
    import datetime
    cutoff_24h = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

    # Accumulators
    acc_7d = {
        "total_score_weight": 0, "weighted_score_sum": 0,
        "stable_flow": 0, "token_flow": 0,
        "whales": set(), "volumes": {}, "total_vol": 0, "count": 0
    }
    
    acc_24h = {
        "total_score_weight": 0, "weighted_score_sum": 0,
        "stable_flow": 0, "token_flow": 0,
        "whales": set(), "volumes": {}, "total_vol": 0, "count": 0
    }

    score_map = {
        "BULLISH_INFLOW": 2, "BULLISH_OUTFLOW": 1,
        "BEARISH_INFLOW": -2, "BEARISH_OUTFLOW": -1,
        "NEUTRAL": 0, "INTERNAL_LOOP": 0
    }
    
    import math

    for tx in transfers:
        amount_usd = tx["amount_usd"]
        signal = tx["signal"]
        symbol = tx["symbol"]
        address = tx["from"]
        
        # Determine if this tx is within 24h
        # Assuming tx['timestamp'] is ISO string, specific to Moralis/Script
        # But here tx is from our internal list which might already have logic
        # We did parsing in merge_and_filter_txs but just kept string.
        # Let's re-parse or rely on string compare if format is consistent ISO
        is_24h = False
        # Specific format expected: YYYY-MM-DDTHH:MM:SS.000Z
        try:
            # Remove Z and parse naive
            ts_str = tx["timestamp"].replace("Z", "")
            # Handle potential millisecond differences
            if "." in ts_str:
                 tx_time = datetime.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
            else:
                 tx_time = datetime.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                 
            if tx_time > cutoff_24h:
                is_24h = True
        except Exception as e:
            # print(f"Time parse error: {e}") 
            pass

        # --- Process Logic (Apply to both if 24h, else only 7d) ---
        weight = math.log10(amount_usd) if amount_usd > 1 else 0
        score = score_map.get(signal, 0)

        # Update Accumulator Function
        def update_acc(acc):
            acc["count"] += 1
            acc["total_vol"] += amount_usd
            acc["whales"].add(address)
            acc["volumes"][address] = acc["volumes"].get(address, 0) + amount_usd
            
            acc["weighted_score_sum"] += score * weight
            acc["total_score_weight"] += weight
            
            if symbol in STABLECOINS:
                if signal == "BULLISH_INFLOW": acc["stable_flow"] += amount_usd
                elif signal == "BEARISH_OUTFLOW": acc["stable_flow"] -= amount_usd
            else:
                if signal == "BEARISH_INFLOW": acc["token_flow"] += amount_usd
                elif signal == "BULLISH_OUTFLOW": acc["token_flow"] -= amount_usd

        # Always update 7d
        update_acc(acc_7d)
        
        # Conditionally update 24h
        if is_24h:
            update_acc(acc_24h)

    # Finalize Stats Function
    def finalize(acc, stats):
        stats["sentiment_score"] = acc["weighted_score_sum"] / acc["total_score_weight"] if acc["total_score_weight"] > 0 else 0
        stats["stablecoin_net_flow"] = acc["stable_flow"]
        stats["token_net_flow"] = acc["token_flow"]
        stats["whale_count"] = len(acc["whales"])
        stats["total_volume"] = acc["total_vol"]
        stats["avg_tx_size"] = acc["total_vol"] / acc["count"] if acc["count"] > 0 else 0
        
        # Top Whale
        if acc["volumes"]:
            top = max(acc["volumes"], key=acc["volumes"].get)
            label = top[:6] + "..." + top[-4:] # Simple truncate
            # Try to find label in txs? 
            # We don't have label map handy here easily, but we can reuse the logic
            # Or just store it. For now simple truncate is safe fallback
            stats["top_whale"] = {"address": top, "volume": acc["volumes"][top], "label": label}

    finalize(acc_7d, stats_7d)
    finalize(acc_24h, stats_24h)
    
    return {"stats_7d": stats_7d, "stats_24h": stats_24h}

import market_data

def merge_and_filter_txs(new_txs, old_txs):
    """
    Merge new and old transactions, remove duplicates, and keep only those from the last 7 days.
    """
    # 1. Deduplicate using hash as key
    merged_map = {}
    
    # Add old first
    for tx in old_txs:
        merged_map[tx['hash']] = tx
        
    # Add new (overwrite if exists)
    for tx in new_txs:
        merged_map[tx['hash']] = tx
        
    all_txs = list(merged_map.values())
    
    # 2. Filter last 7 days (168 hours)
    # Use UTC to match API timestamps
    cutoff_time = datetime.utcnow() - timedelta(hours=168) 
    filtered_txs = []
    
    for tx in all_txs:
        try:
            # Handle timestamp parsing
            ts_str = tx['timestamp']
            if ts_str.endswith('Z'):
                ts_str = ts_str[:-1]
            
            # Use simple parsing
            if "." in ts_str:
                 tx_time = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
            else:
                 tx_time = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")

            if tx_time > cutoff_time:
                filtered_txs.append(tx)
        except Exception as e:
            # Fallback for errors
            filtered_txs.append(tx) 

    # 3. Sort by timestamp descending
    filtered_txs.sort(key=lambda x: x['timestamp'], reverse=True)
    return filtered_txs


def analyze_transfers_v1(transfers, market_metrics):
    """
    Strategy V1 Analysis:
    Combines Chain Transfers (Intent) + Market Data (Confirmation).
    Calculates Sentiment Score and Confidence Score.
    """
    
    # Initialize Stats Structure
    def init_stats():
        return {
            "sentiment_score": 0,
            "confidence_score": 0, # New V1 Metric
            "action_signal": "WAIT", # New V1 Metric
            "stablecoin_net_flow": 0,
            "token_net_flow": 0,
            "whale_count": 0,
            "avg_tx_size": 0,
            "total_volume": 0,
            "top_whale": {"address": "N/A", "volume": 0, "label": "N/A"}
        }

    stats_7d = init_stats()
    stats_24h = init_stats()

    if not transfers:
        return {"stats_7d": stats_7d, "stats_24h": stats_24h}

    cutoff_24h = datetime.utcnow() - timedelta(hours=24)

    # Accumulators
    acc_7d = {"w_score": 0, "total_w": 0, "stable": 0, "token": 0, "whales": set(), "vols": {}, "sum_vol": 0, "cnt": 0}
    acc_24h = {"w_score": 0, "total_w": 0, "stable": 0, "token": 0, "whales": set(), "vols": {}, "sum_vol": 0, "cnt": 0}

    import math
    
    # Market Context for Scoring Adjustments (Patch 1 & Confirmation)
    # We use market_metrics from OKX
    # If market data is missing, we use neutral defaults
    if not market_metrics:
        market_metrics = {"volume_ratio": 1.0, "delta_oi_24h_percent": 0, "funding_rate": 0, "oi_trend": "FLAT"}

    vol_ratio = market_metrics.get("volume_ratio", 1.0)
    oi_delta = market_metrics.get("delta_oi_24h_percent", 0)
    funding = market_metrics.get("funding_rate", 0)

    # --- Transfer Scoring Logic ---
    for tx in transfers:
        amount_usd = tx["amount_usd"]
        signal = tx["signal"]
        symbol = tx["symbol"]
        
        # 1. Base Score
        score = 0
        if signal == "BULLISH_INFLOW": score = 2
        elif signal == "BULLISH_OUTFLOW": score = 1
        elif signal == "BEARISH_OUTFLOW": score = -1
        elif signal == "BEARISH_INFLOW":
            # Patch 1: BEARISH_INFLOW Separation
            # If Volume is high or OI is up, it's real selling (-2)
            # Otherwise it might be hedging (-1)
            is_real_dump = (vol_ratio >= 1.5) or (oi_delta > 2.0)
            score = -2 if is_real_dump else -1
            
        weight = math.log10(amount_usd) if amount_usd > 1 else 0

        # Update Helper
        def update(acc):
            acc["cnt"] += 1
            acc["sum_vol"] += amount_usd
            acc["whales"].add(tx["from"])
            acc["vols"][tx["from"]] = acc["vols"].get(tx["from"], 0) + amount_usd
            
            acc["w_score"] += score * weight
            acc["total_w"] += weight
            
            if symbol in STABLECOINS:
                if signal == "BULLISH_INFLOW": acc["stable"] += amount_usd
                elif signal == "BEARISH_OUTFLOW": acc["stable"] -= amount_usd
            else:
                if signal == "BEARISH_INFLOW": acc["token"] += amount_usd
                elif signal == "BULLISH_OUTFLOW": acc["token"] -= amount_usd

        # 7d Update
        update(acc_7d)
        
        # 24h Update
        # Parse text time
        try:
            ts_str = tx["timestamp"].replace("Z", "")
            if "." in ts_str: t = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
            else: t = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
            if t > cutoff_24h:
                update(acc_24h)
        except: pass

    # --- Confidence Score Logic (Fusion) ---
    def calc_confidence(sentiment_score):
        # 1. Transfer Sentiment Contribution (30%)
        # Normalize score (-2 to 2) to 0-100
        # 0 -> 50, +2 -> 100, -2 -> 0
        sent_conf = ((sentiment_score + 2) / 4) * 100
        
        # 2. OI Alignment (25%)
        # Bullish & OI Up = Good
        # Bearish & OI Up = Good (Shorting)
        # Divergence = Bad
        oi_conf = 50
        if sentiment_score > 0.3: # Bullish
            if oi_delta > 1.0: oi_conf = 100 # New Longs
            elif oi_delta < -1.0: oi_conf = 20 # Deleveraging (Weak base)
        elif sentiment_score < -0.3: # Bearish
            if oi_delta > 1.0: oi_conf = 100 # New Shorts
            elif oi_delta < -1.0: oi_conf = 20 # Short Covering (Weak base)
            
        # 3. Volume Confirmation (20%)
        vol_conf = min(100, (vol_ratio / 1.5) * 75) # 1.5 ratio -> 75 score, 2.0 -> 100
        if vol_ratio < 1.0: vol_conf = 20 # Low interest
        
        # 4. Funding Safety (15%)
        fund_conf = 100
        if sentiment_score > 0 and funding > 0.0005: fund_conf = 10 # Don't long crowded top
        if sentiment_score < 0 and funding < -0.0005: fund_conf = 10 # Don't short crowded bottom
        
        # 5. Price Reaction (10%) - Simplified placeholder as we don't have detailed price candles here yet
        price_conf = 50 
        
        # Final Weighted Sum
        final_conf = (
            0.30 * sent_conf + 
            0.25 * oi_conf + 
            0.20 * vol_conf + 
            0.15 * fund_conf + 
            0.10 * price_conf
        )
        return round(final_conf, 1)

    # Finalize
    def finalize(acc, stats):
        if acc["total_w"] > 0:
            stats["sentiment_score"] = acc["w_score"] / acc["total_w"]
        
        stats["confidence_score"] = calc_confidence(stats["sentiment_score"])
        
        # Action Signal
        if stats["confidence_score"] >= 75: stats["action_signal"] = "EXECUTE"
        elif stats["confidence_score"] >= 60: stats["action_signal"] = "PROBE"
        elif stats["confidence_score"] >= 40: stats["action_signal"] = "OBSERVE"
        else: stats["action_signal"] = "NO_TRADE"
        
        stats["stablecoin_net_flow"] = acc["stable"]
        stats["token_net_flow"] = acc["token"]
        stats["whale_count"] = len(acc["whales"])
        stats["total_volume"] = acc["sum_vol"]
        if acc["cnt"] > 0: stats["avg_tx_size"] = acc["sum_vol"] / acc["cnt"]
        
        if acc["vols"]:
            top = max(acc["vols"], key=acc["vols"].get)
            stats["top_whale"] = {"address": top, "volume": acc["vols"][top], "label": top[:6]+"..."}

    finalize(acc_7d, stats_7d)
    finalize(acc_24h, stats_24h)
    
    return {"stats_7d": stats_7d, "stats_24h": stats_24h}


import news_fetcher

# ... (keep existing imports)

def generate_comparative_summary(eth_data, sol_data, eth_market, sol_market, fear_greed, news_data, macro_data):
    """
    Generate the V2 Strategy Narrative (Tri-Layer Analysis).
    Combines:
    1. Macro Liquidity (Fed/DXY/VIX)
    2. News Narrative (Headlines)
    3. Whale/Market Reality (On-Chain + OI/Funding)
    """
    
    # helper to format news
    def fmt_news(items):
        return "\n".join([f"- {i.get('title')}" for i in items[:3]])

    prompt_data = {
        "Layer1_Macro_Liquidity": {
            "BTC_Fear_Greed": f"{fear_greed['value']} ({fear_greed['value_classification']})",
            "Fed_Futures": macro_data.get('fed_futures'),
            "Japan_Carrier_Trade": macro_data.get('japan_macro'),
            "Global_Liquidity": macro_data.get('liquidity_monitor')
        },
        "Layer2_News_Narrative": {
            "Top_Macro_News": fmt_news(news_data.get('macro', {}).get('items', [])),
            "Top_Crypto_News": fmt_news(news_data.get('general', {}).get('items', [])),
            "ETH_News": fmt_news(news_data.get('ethereum', {}).get('items', [])),
            "SOL_News": fmt_news(news_data.get('general', {}).get('items', [])) # Fallback if no SOL specific
        },
        "Layer3_Whale_Reality": {
            "ETH_Chain": {
                "Sentiment_7d": eth_data["stats_7d"]["sentiment_score"],
                "Sentiment_24h": eth_data["stats_24h"]["sentiment_score"],
                "Confidence_Score": eth_data["stats_7d"]["confidence_score"],
                "Net_Flow_Stablecoin": f"${eth_data['stats_7d']['stablecoin_net_flow']:,.0f}",
                "Net_Flow_Token": f"{eth_data['stats_7d']['token_net_flow']:,.0f}",
                "Market_OI_Delta": f"{eth_market.get('delta_oi_24h_percent',0):.2f}%",
                "Funding": f"{eth_market.get('funding_rate',0):.6f}",
                "RSI_4H": f"{eth_market.get('rsi_4h', 50):.1f}"
            },
            "SOL_Chain": {
                "Sentiment_7d": sol_data["stats_7d"]["sentiment_score"],
                "Sentiment_24h": sol_data["stats_24h"]["sentiment_score"],
                "Confidence_Score": sol_data["stats_7d"]["confidence_score"],
                "Net_Flow_Stablecoin": f"${sol_data['stats_7d']['stablecoin_net_flow']:,.0f}",
                "Net_Flow_Token": f"{sol_data['stats_7d']['token_net_flow']:,.0f}",
                "Market_OI_Delta": f"{sol_market.get('delta_oi_24h_percent',0):.2f}%",
                "Funding": f"{sol_market.get('funding_rate',0):.6f}",
                "RSI_4H": f"{sol_market.get('rsi_4h', 50):.1f}"
            }
        }
    }
    
    prompt = f"""
    Act as a simplified "Crypto Hedge Fund AI". Perform a **Tri-Layer Market Analysis** to validate signals.
    
    DATA JSON:
    {json.dumps(prompt_data, indent=2)}
    
    ANALYSIS FRAMEWORK:
    1. **Layer 1 (Macro Liquidity)**: Is the global tap opening (Risk On) or closing (Risk Off)? 
       - Check DXY (Dollar), US10Y (Yields), VIX (Fear).
       - Check Fed Expectations (Dovish/Hawkish).
    2. **Layer 2 (Narrative)**: What is the media saying? Are headlines bullish or bearish?
    3. **Layer 3 (Reality Check)**: Do Whales & Money Flow agree with the Narrative?
       - **Technical Check**: RSI > 70 (Overbought), RSI < 30 (Oversold).
       - **Bullish Verification**: News says "Buy" AND Whales are Buying (Positive Flow) + OI Rising.
       - **Bearish Verification**: News says "Sell" AND Whales are Selling + OI Drop.
       - **TRAP WARNING**: News is Bullish BUT Whales are Selling (Exit Liquidity) -> Call this out!
       - **TRAP WARNING**: News is Bearish BUT Whales are Buying (Accumulation) -> Call this out!
    
    OUTPUT INSTRUCTIONS:

    - Return a JSON object with "en" and "zh" keys.
    - Content must be Markdown.
    - **Synthesize** the layers. Don't just list data.
    - **Verdict**: For ETH and SOL, give a final signal (EXECUTE / PROBE / OBSERVE / WAIT) based on the *confluence* of all 3 layers.
    
    Structure:
    **🌍 Global Macro & Liquidity**: [Summary of Layer 1 & 2 combined]
    
    **🔷 ETH Strategy**:
    * **Signal**: [Action Signal]
    * **Reality Check**: [Compare News Sentiment vs Whale Flow. Is it confirmed or divergent?]
    * **Key Metric**: [Mention the most critical confirming/contradicting metric, e.g. "Stablecoin Outflows"]
    
    **🟣 SOL Strategy**:
    * **Signal**: [Action Signal]
    * **Reality Check**: [Compare News Sentiment vs Whale Flow]
    * **Key Metric**: [Mention crucial metric]
    """

    # Attempt 1: Gemini
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        text = response.text.strip()
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match: text = match.group(0)
        return json.loads(text)
    except Exception as e_gemini:
        print(f"⚠️ Gemini AI Error: {e_gemini}")
        print("🔄 Switching to DeepSeek V3 (Fallback)...")
        
        # Attempt 2: DeepSeek
        try:
            deepseek_key = os.getenv("DEEPSEEK_API_KEY")
            if not deepseek_key:
                raise ValueError("No DEEPSEEK_API_KEY found in env")
                
            ds_url = "https://api.deepseek.com/chat/completions"
            ds_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_key}"
            }
            ds_payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a hedge fund AI. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            }
            
            ds_res = requests.post(ds_url, headers=ds_headers, json=ds_payload, timeout=60)
            
            if ds_res.status_code != 200:
                raise Exception(f"DeepSeek Status {ds_res.status_code}: {ds_res.text}")
                
            ds_data = ds_res.json()
            ds_text = ds_data["choices"][0]["message"]["content"].strip()
            
            import re
            match = re.search(r'\{.*\}', ds_text, re.DOTALL)
            if match: ds_text = match.group(0)
            
            return json.loads(ds_text)
            
        except Exception as e_ds:
            print(f"❌ DeepSeek AI Error: {e_ds}")
            return {"en": "AI analysis unavailable.", "zh": "AI 分析暂时不可用。"}

# ... (rest of file)

def main():
    print("DEBUG: Entering whale_watcher.main()...")
    
    # 1. Setup Directories
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(base_dir, "../frontend/data/whale_analysis.json")
    
    history_data = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, "r") as f:
                history_data = json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")

    # 2. Fetch News & Macro Data (Layer 1 & 2)
    print("\n=== LAYER 1 & 2: GLOBAL MACRO & NEWS ===")
    try:
        print("Fetching Macro Data (Fed, Liquidity)...")
        macro_data = {
            "fed_futures": news_fetcher.fetch_fed_futures(),
            "japan_macro": news_fetcher.fetch_japan_context(),
            "liquidity_monitor": news_fetcher.fetch_liquidity_monitor()
        }
        print("Fetching Global News...")
        news_data = news_fetcher.gather_news()
        print("✅ Macro & News fetched successfully.")
    except Exception as e:
        print(f"⚠️ News/Macro fetch failed: {e}")
        import traceback
        traceback.print_exc()
        macro_data = {}
        news_data = {}

    # 3. Fetch Whale Data (Layer 3)
    print("\n=== LAYER 3: WHALE & MARKET REALITY ===")
    
    print("Fetching data from Moralis (ETH)...")
    new_eth_transfers = fetch_large_transfers()
    
    print("Fetching data from Moralis (SOL)...")
    new_sol_transfers = fetch_solana_swaps()
    
    print("Fetching Fear & Greed Index...")
    fear_greed = fetch_fear_greed_index()
    print(f"Fear & Greed: {fear_greed['value']} ({fear_greed['value_classification']})")
    
    # Merge with History (Keep last 24h/7d deduplicated)
    old_eth_txs = []
    if "eth" in history_data and "top_txs" in history_data["eth"]:
        old_eth_txs = history_data["eth"]["top_txs"]
        
    old_sol_txs = []
    if "sol" in history_data and "top_txs" in history_data["sol"]:
        old_sol_txs = history_data["sol"]["top_txs"]
        
    # Deduplicate logic
    old_eth_hashes = {tx['hash'] for tx in old_eth_txs}
    unique_new_eth = [tx for tx in new_eth_transfers if tx['hash'] not in old_eth_hashes]
    
    old_sol_hashes = {tx['hash'] for tx in old_sol_txs}
    unique_new_sol = [tx for tx in new_sol_transfers if tx['hash'] not in old_sol_hashes]
    
    print(f"New Unique Tx Found: ETH={len(unique_new_eth)}, SOL={len(unique_new_sol)}")

    eth_transfers = merge_and_filter_txs(new_eth_transfers, old_eth_txs)
    sol_transfers = merge_and_filter_txs(new_sol_transfers, old_sol_txs)
    
    # 4. Fetch Market Data & Analyze
    print("Fetching Market Data (OKX)...")
    eth_market = market_data.get_strategy_metrics("ETH")
    sol_market = market_data.get_strategy_metrics("SOL")
    
    print("Calculating Strategy V1 Metrics...")
    eth_analysis = analyze_transfers_v1(eth_transfers, eth_market)
    sol_analysis = analyze_transfers_v1(sol_transfers, sol_market)
    
    # Apply EMA Smoothing
    ALPHA = 0.3
    def smooth_score(chain_key, timeframe_key, current_analysis, history):
        old_score = 0
        try:
            if chain_key in history and "stats" in history[chain_key]:
                old_score = history[chain_key]["stats"].get("sentiment_score", 0)
        except: pass
        raw_score = current_analysis[timeframe_key]["sentiment_score"]
        if history:
            return round((raw_score * ALPHA) + (old_score * (1 - ALPHA)), 2)
        else:
            return raw_score

    eth_analysis["stats_7d"]["sentiment_score"] = smooth_score("eth", "stats_7d", eth_analysis, history_data)
    sol_analysis["stats_7d"]["sentiment_score"] = smooth_score("sol", "stats_7d", sol_analysis, history_data)

    # 5. Generate AI Narrative (V2 Tri-Layer)
    ai_summary = {"en": "AI disabled or failed.", "zh": "AI 分析暂时不可用。"}
    try:
        print("\n=== GENERATING AI TRI-LAYER ANALYSIS ===")
        raw_ai_summary = generate_comparative_summary(
            eth_analysis, sol_analysis, 
            eth_market, sol_market, 
            fear_greed, 
            news_data, macro_data # Pass the new layers
        )
        
        # Sanitize AI Summary (Ensure values are strings, not dicts)
        ai_summary = {}
        for key, val in raw_ai_summary.items():
            if isinstance(val, dict):
                # If LLM returns a dict (e.g. nested JSON), try to extract text or dump it
                ai_summary[key] = val.get("content", val.get("text", str(val)))
            else:
                ai_summary[key] = str(val)
                
    except Exception as e:
        print(f"AI Generation Error: {e}")
        import traceback
        traceback.print_exc()

    # 6. Save Final JSON
    final_output = {
        "updated_at": datetime.now().isoformat(),
        "fear_greed": fear_greed,
        "macro": macro_data, 
        "news": { 
             "macro": [x['title'] for x in news_data.get('macro', {}).get('items', [])[:5]],
             "crypto": [x['title'] for x in news_data.get('general', {}).get('items', [])[:5]]
        },
        "eth": {
            "stats": eth_analysis["stats_7d"], 
            "stats_24h": eth_analysis["stats_24h"],
            "top_txs": eth_transfers[:1000]
        },
        "sol": {
            "stats": sol_analysis["stats_7d"],
            "stats_24h": sol_analysis["stats_24h"],
            "top_txs": sol_transfers[:1000]
        },
        "ai_summary": ai_summary
    }

    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(final_output, f, indent=2)
        print(f"✅ Analysis saved to {output_file}")
    except Exception as e:
        print(f"❌ Error saving output: {e}")
    
    # 7. Notifications
    new_tx_count = len(unique_new_eth) + len(unique_new_sol)
    if new_tx_count > 0:
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            try:
                from telegram_bot import send_daily_report
                print(f"Sending Telegram report...")
                send_daily_report(output_file)
            except Exception as e:
                print(f"Telegram fail: {e}")
            
        discord_url = os.getenv("DISCORD_WEBHOOK_URL")
        if discord_url:
            print("Sending Discord alert...")
            try:
                # Helper for formatting
                def fmt(val):
                    if abs(val) >= 1_000_000: return f"${val/1_000_000:.2f}M"
                    elif abs(val) >= 1_000: return f"${val/1_000:.1f}k"
                    else: return f"${val:.2f}"
                    
                eth_stats = eth_analysis["stats_7d"]
                sol_stats = sol_analysis["stats_7d"]
                ai_text = ai_summary.get("zh", ai_summary.get("en", "N/A"))
                
                # Brief Discord Msg
                msg = {
                    "content": f"🚨 **Whale Watcher V2** | {datetime.now().strftime('%H:%M')}\n\n"
                               f"**AI Verdict**:\n{ai_text[:1000]}\n\n"
                               f"**ETH**: Signal `{eth_stats['action_signal']}` | Conf `{eth_stats['confidence_score']}` | Flow `{fmt(eth_stats['stablecoin_net_flow'])}`\n"
                               f"**SOL**: Signal `{sol_stats['action_signal']}` | Conf `{sol_stats['confidence_score']}` | Flow `{fmt(sol_stats['stablecoin_net_flow'])}`"
                }
                requests.post(discord_url, json=msg)
            except Exception as e:
                print(f"Discord fail: {e}")
    else:
        print("No new transactions. Skipping alerts.")

if __name__ == "__main__":
    main()
