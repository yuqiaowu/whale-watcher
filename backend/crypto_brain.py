import os
import json
import time
import requests
from datetime import datetime, timedelta
import news_fetcher
from macro_history import MacroHistory
from dotenv import load_dotenv
from moralis import evm_api


# Load environment variables
# Load environment variables
# Use absolute path relative to this script to ensure proper loading regardless of CWD
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.env")
load_dotenv(dotenv_path=env_path)

MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
MORALIS_API_KEY_2 = os.getenv("MORALIS_API_KEY_2") 
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# Key Rotation Logic
API_KEYS = [k for k in [MORALIS_API_KEY_2, MORALIS_API_KEY] if k]
CURRENT_KEY_IDX = 0

def get_current_key():
    if not API_KEYS: return None
    return API_KEYS[CURRENT_KEY_IDX % len(API_KEYS)]

def rotate_key():
    global CURRENT_KEY_IDX
    print(f"DEBUG: Switching API Key from index {CURRENT_KEY_IDX}...")
    CURRENT_KEY_IDX = (CURRENT_KEY_IDX + 1) % len(API_KEYS)
    print(f"DEBUG: New API Key index: {CURRENT_KEY_IDX}")


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
                # Dynamic Offset: Reverted to 300 as we use DefiLlama for main flow data now.
                "offset": 300 if symbol in STABLECOINS else 100,
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

def fetch_defillama_global_flows():
    """Fetch global stablecoin market cap change (24h) from DefiLlama."""
    try:
        url = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        total_change = 0
        count = 0
        
        # We focus on the Top 2: USDT, USDC which represent majority of flow
        for coin in data.get("peggedAssets", []):
             if coin.get("symbol") in ["USDT", "USDC"]:
                 try:
                     curr = coin.get("circulating", {}).get("peggedUSD", 0)
                     prev = coin.get("circulatingPrevDay", {}).get("peggedUSD", 0)
                     
                     if curr and prev:
                         change = curr - prev
                         total_change += change
                         count += 1
                 except: pass
        
        if count > 0:
            print(f"✅ DefiLlama Global Stablecoin Flow (24h): ${total_change:,.0f}")
            return total_change
            
        print("⚠️ DefiLlama: No valid stablecoin data found.")
        return 0
    except Exception as e:
        print(f"❌ DefiLlama Error: {e}")
        return 0

def fetch_fear_greed_index():
    """Fetch Bitcoin Fear & Greed Index from alternative.me (Today + Yesterday for change)."""
    try:
        url = "https://api.alternative.me/fng/?limit=2"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if "data" in data and len(data["data"]) > 0:
            today_item = data["data"][0]
            today_val = int(today_item["value"])
            
            if len(data["data"]) > 1:
                yesterday_val = int(data["data"][1]["value"])
                if yesterday_val != 0:
                    change = ((today_val - yesterday_val) / yesterday_val) * 100
                else:
                    change = 0
                
            return {
                "value": today_val,
                "value_classification": today_item["value_classification"],
                "change": change
            }
    except Exception as e:
        print(f"Error fetching Fear & Greed Index: {e}")
    
    return {"value": 50, "value_classification": "Neutral", "change": 0} # Fallback

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
    # Use timezone-aware UTC for everything
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    cutoff_time = now_utc - timedelta(hours=168)
    
    filtered_txs = []
    
    for tx in all_txs:
        try:
            # Handle timestamp parsing
            ts_str = tx['timestamp']
            
            # Robust ISO parsing
            if ts_str.endswith('Z'):
                ts_str = ts_str[:-1]
                # If Z was present, it's UTC.
                if "." in ts_str:
                     tx_time = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
                else:
                     tx_time = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                # Make it aware
                tx_time = tx_time.replace(tzinfo=timezone.utc)
            else:
                 # Assume it's UTC if missing Z (common in our script), but let's be safe
                 # If using .fromisoformat() in py3.7+, better, but manual is safer here
                 if "." in ts_str:
                     tx_time = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
                 else:
                     tx_time = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                 
                 # Force UTC if naive
                 if tx_time.tzinfo is None:
                     tx_time = tx_time.replace(tzinfo=timezone.utc)

            if tx_time > cutoff_time:
                filtered_txs.append(tx)
        except Exception as e:
            # print(f"Date error: {e}")
            # Ensure we don't drop data on parser error, default to keep or check manually?
            # Safer to keep if unsure? Or drop? 
            # If we drop, we lose history. If we keep, we might have effective duplicates if parser fails.
            # Let's try to keep recent-ish looking strings or just fail safe.
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
        
        # 2. OI Alignment (25%) - REFINED LOGIC (Trend vs Volatility)
        # Old Logic was either blunt or contradictory.
        # New Logic: Distinction between "Trend Strength" and "Volatility Risk".
        
        oi_conf = 50 # Default Neutral
        
        # A. Base Score from OI Change (Capital Flow)
        if oi_delta > 5.0:    oi_conf = 80  # Big Interest (High Confidence something is happening)
        elif oi_delta > 2.0:  oi_conf = 70  # Healthy Growing Interest
        elif oi_delta < -5.0: oi_conf = 10  # Panic Capital Flight (Low Confidence)
        elif oi_delta < -2.0: oi_conf = 30  # Funds Leaving (Weak)
        
        # B. Context Modifier (Sentiment Alignment) - The "Contradiction Resolver"
        is_strong_sentiment = abs(sentiment_score) > 0.3
        
        if is_strong_sentiment:
            # Trend Confirmation: If sentiment has direction, High OI is good.
            if oi_delta > 1.0: 
                oi_conf = 100 # Perfect: Direction + Fuel -> High Confidence
            elif oi_delta < -1.0: 
                oi_conf = 40  # Divergence: Trend exists but fuel is leaving -> Weak Confidence
        else:
            # Neutral Sentiment Logic: High OI without direction = DANGER (Volatility)
            if oi_delta > 5.0:
                oi_conf = 20  # PENALTY: Huge OI but no direction? That's a coin flip/gambling.
            elif oi_delta > 2.0:
                oi_conf = 60  # Slight Penalty: Interest growing but direction unclear.

            
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

def generate_comparative_summary(eth_data, sol_data, eth_market, sol_market, fear_greed, news_data, macro_data, btc_market=None, btc_analysis=None):
    # Default dicts if None
    if btc_market is None: btc_market = {}
    if btc_analysis is None: btc_analysis = {"stats_24h": {}}
    if fear_greed is None: fear_greed = {"value": "50", "value_classification": "Neutral"}
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
                "Whale_Flow": {
                    "Sentiment_Score": eth_data["stats_7d"]["sentiment_score"],
                    "Confidence": eth_data["stats_7d"]["confidence_score"],
                    "Net_Flow_Tokens": f"{eth_data['stats_7d']['token_net_flow']:,.0f}",
                    "Net_Flow_Stablecoin": f"${eth_data['stats_7d']['stablecoin_net_flow']:,.0f}",
                },
                "Market_Technicals": {
                    "Price": eth_market.get('price_close'),
                    "Price_Rank": f"{eth_market.get('price_rank_20', 50):.1f}/100",
                    "Vol_Ratio": f"{eth_market.get('vol_ratio_20', 1):.2f}x",
                    "Buy_Stars": f"{eth_market.get('buy_stars', 0)}/3",
                    "Sell_Stars": f"{eth_market.get('sell_stars', 0)}/3",
                    "Signal_Bottom_Vol": eth_market.get('signal_low_high_vol', False),
                    "Signal_Top_Vol": eth_market.get('signal_high_high_vol', False),
                    "RSI_14": f"{eth_market.get('rsi_14', 50):.1f}",
                    "MACD_Hist": f"{eth_market.get('macd_hist', 0):.4f}",
                    "ADX": f"{eth_market.get('adx_14', 0):.1f}",
                    "Bollinger_Width": f"{eth_market.get('bb_width', 0):.3f}",
                    "ATR_Percent": f"{eth_market.get('natr_percent', 0):.2f}%",
                    "Funding": f"{eth_market.get('funding_rate',0):.6f}",
                    "OI_Delta": f"{eth_market.get('delta_oi_24h_percent',0):.2f}%"
                },
                "Liquidation": eth_market.get("liquidation_context", "N/A")
            },
            "SOL_Chain": {
                 "Whale_Flow": {
                    "Sentiment_Score": sol_data["stats_7d"]["sentiment_score"],
                    "Confidence": sol_data["stats_7d"]["confidence_score"],
                    "Net_Flow_Tokens": f"{sol_data['stats_7d']['token_net_flow']:,.0f}",
                    "Net_Flow_Stablecoin": f"${sol_data['stats_7d']['stablecoin_net_flow']:,.0f}",
                },
                "Market_Technicals": {
                    "Price": sol_market.get('price_close'),
                    "Price_Rank": f"{sol_market.get('price_rank_20', 50):.1f}/100",
                    "Vol_Ratio": f"{sol_market.get('vol_ratio_20', 1):.2f}x",
                    "Buy_Stars": f"{sol_market.get('buy_stars', 0)}/3",
                    "Sell_Stars": f"{sol_market.get('sell_stars', 0)}/3",
                    "Signal_Bottom_Vol": sol_market.get('signal_low_high_vol', False),
                    "Signal_Top_Vol": sol_market.get('signal_high_high_vol', False),
                    "RSI_14": f"{sol_market.get('rsi_14', 50):.1f}",
                    "MACD_Hist": f"{sol_market.get('macd_hist', 0):.4f}",
                    "ADX": f"{sol_market.get('adx_14', 0):.1f}",
                    "Bollinger_Width": f"{sol_market.get('bb_width', 0):.3f}",
                    "ATR_Percent": f"{sol_market.get('natr_percent', 0):.2f}%",
                    "Funding": f"{sol_market.get('funding_rate',0):.6f}",
                    "OI_Delta": f"{sol_market.get('delta_oi_24h_percent',0):.2f}%"
                },
                "Liquidation": sol_market.get("liquidation_context", "N/A")
            },
            "BTC_Context": {
                "RSI": f"{btc_market.get('rsi_14', 50):.1f}",
                "MACD": f"{btc_market.get('macd_hist', 0):.4f}",
                "ADX": f"{btc_market.get('adx_14', 0):.1f}",
                "Liquidation": btc_market.get("liquidation_context", "N/A")
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
       - **Technical Confirmation**:
         - **Trend (ADX)**: If ADX > 25, the trend is STRONG (Don't fade it). If ADX < 20, market is CHOPPING (Mean Reversion).
         - **Momentum (MACD)**: Check for Divergences. Price Lower Low + MACD Higher Low = Bullish Divergence.
         - **Volatility (BB/ATR)**: If Bollinger Width is compressing (Low), expect a BREAKOUT. Use ATR % to gauge stop-loss width.
         - **Volume Anomaly (CRITICAL)**:
             - **Signal_Bottom_Vol**: Low Price + High Volume = PANIC SELLING / WHALE ACCUMULATION -> BULLISH.
             - **Signal_Top_Vol**: High Price + High Volume = CLIMAX BUYING / WHALE DISTRIBUTION -> BEARISH.
             - **Star Rating**: 3/3 Stars means strong technical confluence.
       - **Bullish Verification**: News says "Buy" AND Whales are Buying (Positive Flow) + ADX Rising + Signal_Bottom_Vol.
       - **Bearish Verification**: News says "Sell" AND Whales are Selling + MACD Death Cross + Signal_Top_Vol.
       - **TRAP WARNING**: News is Bullish BUT Whales are Selling (Exit Liquidity) -> Call this out!
       - **TRAP WARNING**: News is Bearish BUT Whales are Buying (Accumulation) -> Call this out!
       - **Retail Pain (Liquidations)**: Are retail traders bleeding? If Long Liqs are high, is the bottom near? If Short Liqs are high, is the top near?
       - **For BTC**: Since we lack Whale Flow, focus purely on **Pain/Squeeze** logic (Negative Funding + High Short Liqs = Squeeze).

    OUTPUT INSTRUCTIONS:

    - Return a JSON object with "en" and "zh" keys.
    - Content must be Markdown.
    - **Synthesize** the layers. Don't just list data.
    - **Verdict**: For ETH, SOL, and BTC, give a final signal (EXECUTE / PROBE / OBSERVE / WAIT) based on the *confluence* of layers.
    
    Structure:
    **🌍 Global Macro & Liquidity**: [Summary of Layer 1 & 2 combined]
    
    **🟠 BTC Strategy (Contract Only)**:
    * **Signal**: [Action Signal based on Squeeze/RSI]
    * **Reality Check**: [Analyze Funding Rates & Liquidation Pain. Are shorts trapped? Is it oversold?]
    
    **🔷 ETH Strategy**:
    * **Signal**: [Action Signal]
    * **Reality Check**: [Compare News Sentiment vs Whale Flow. **CRITICAL: Compare 7-Day Trend (Structural) vs 24H (Immediate). Are they aligning or diverging? Check Liquidation Pain**: Are retail traders bleeding? If Long Liqs are high, is the bottom near?]
    * **Key Metric**: [Mention the most critical metric]
    
    **🟣 SOL Strategy**:
    * **Signal**: [Action Signal]
    * **Reality Check**: [Compare News Sentiment vs Whale Flow. **CRITICAL: Compare 7-Day Trend (Structural) vs 24H (Immediate). Check Liquidation Pain**: Are retail traders bleeding? If Long Liqs are high, is the bottom near?]
    * **Key Metric**: [Mention crucial metric]
    """
    
    # Add prompt reinforcement
    prompt += "\n\nCRITICAL: You MUST include BOTH 'en' (English) and 'zh' (Chinese) analysis in the JSON."
    
    res = _call_ai_with_fallback(prompt)
    
    if res and isinstance(res, dict):
        if "en" in res and ("zh" not in res or not res["zh"]):
            print("⚠️ AI omitted 'zh'. Copying 'en' as fallback.")
            res["zh"] = "[AI 暂未提供中文，显示原逻辑]\n\n" + res["en"]
            
    return res

def _call_ai_with_fallback(prompt, system_prompt="You are a professional crypto AI. Return ONLY valid JSON.", is_translation=False):
    """
    Primary: DeepSeek V3
    Fallback: Gemini 1.5 Pro
    """
    # 1. Try DeepSeek (Primary)
    ds_key = os.getenv("DEEPSEEK_API_KEY")
    if ds_key:
        try:
            print(f"🔄 Requesting DeepSeek V3 ({'Translation' if is_translation else 'Analysis'})...")
            url = "https://api.deepseek.com/chat/completions"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ds_key}"}
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "response_format": {"type": "json_object"}
            }
            res = requests.post(url, headers=headers, json=payload, timeout=90)
            if res.status_code == 200:
                text = res.json()["choices"][0]["message"]["content"].strip()
                import re
                match = re.search(r'\{.*\}', text, re.DOTALL)
                return json.loads(match.group(0)) if match else json.loads(text)
            else:
                print(f"⚠️ DeepSeek Status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            print(f"⚠️ DeepSeek failed: {e}")

    # 2. Fallback to Gemini (Secondary)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            print(f"🔄 DeepSeek failing... Falling back to Gemini Pro...")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={gemini_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": f"SYSTEM: {system_prompt}\n\nUSER: {prompt}"}]
                }],
                "generationConfig": {
                    "response_mime_type": "application/json"
                }
            }
            res = requests.post(url, headers=headers, json=payload, timeout=90)
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                import re
                match = re.search(r'\{.*\}', text, re.DOTALL)
                return json.loads(match.group(0)) if match else json.loads(text)
            else:
                print(f"⚠️ Gemini Status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            print(f"⚠️ Gemini fallback failed: {e}")

    # 3. Last Resort
    return None

def generate_market_narrative(prompt):
    """Refactored to use fallback logic"""
    result = _call_ai_with_fallback(prompt)
    if result:
        return result
    return {"en": "AI analysis currently unavailable.", "zh": "AI 分析暂时不可用。"}

def translate_news_data(news_data):
    """
    Batch translate news titles and summaries using AI Fallback.
    """
    if not news_data:
        return news_data
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("⚠️ No DeepSeek API Key for translation.")
        return news_data

    # 1. Extract titles and summaries to translate
    to_translate = []
    refs = []  # To map back: (category, index)
    
    import re
    def clean_html(raw_html):
        cleanr = re.compile('<.*?>')
        cleantext = re.sub(cleanr, '', raw_html)
        return cleantext.strip()

    # Priority categories
    for category in ["bitcoin", "ethereum", "general"]:
        if category in news_data and isinstance(news_data[category], dict) and "items" in news_data[category]:
            # Only translate the top 8 items per category to save tokens/time
            for i, item in enumerate(news_data[category]["items"][:8]):
                raw_summary = item.get("summary", "")
                clean_summary = clean_html(raw_summary)
                
                to_translate.append({
                    "title": item.get("title", ""),
                    "summary": clean_summary[:300] # Extend truncate limit now that tags are gone
                })
                refs.append((category, i))
    
    if not to_translate:
        return news_data

    prompt = (
        "You are a professional crypto translator. Identify the core message and translate the following news items (titles and summaries) into professional Chinese (Simplified). "
        "Strictly maintain the order. "
        "Return ONLY a JSON object with a 'translations' key containing a list of objects in the EXACT same order. "
        "Example format: {'translations': [{'title': '...', 'summary': '...'}, ...]}.\n\n"
        f"ITEMS: {json.dumps(to_translate)}"
    )
    
    print(f"DEBUG: Sending translation request for {len(to_translate)} items.")
    result = _call_ai_with_fallback(prompt, system_prompt="Return ONLY a JSON object with a 'translations' key. No preamble.", is_translation=True)
    
    if result and "translations" in result:
        translated_list = result["translations"]
        print(f"DEBUG: AI returned {len(translated_list)} translations.")
        
        # 3. Apply back to news_data
        count = 0
        for j, (cat, idx) in enumerate(refs):
            if j < len(translated_list):
                item = news_data[cat]["items"][idx]
                t_title = translated_list[j].get("title", "")
                t_summary = translated_list[j].get("summary", "")
                
                # Check for validity
                if t_title and t_summary:
                    item["title"] = t_title
                    item["summary"] = t_summary
                    count += 1
                    
        print(f"✅ News translated successfully via AI ({count} items updated).")
    else:
        print(f"❌ News translation failed (Result was None or missing key): {result}")
        # Fallback: Mark as [Untranslated] so we know
        # for j, (cat, idx) in enumerate(refs):
        #    item = news_data[cat]["items"][idx]
        #    item["title"] = "[EN] " + item["title"]
        
    return news_data

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
        
        # --- Macro History Persistence ---
        try:
             data_dir_path = os.path.join(base_dir, "../frontend/data")
             mh = MacroHistory(data_dir_path)
             mh.add_snapshot(
                 macro_data.get("fed_futures", {}), 
                 macro_data.get("japan_macro", {}), 
                 macro_data.get("liquidity_monitor", {})
             )
             
             # Calculate 5-day changes from LOCAL history (Overwrite API-based if available)
             # Fed Change (bps)
             fed_rate = macro_data.get("fed_futures", {}).get("implied_rate")
             change_bps = mh.get_change_absolute("fed_rate", fed_rate, days=5)
             if change_bps is not None:
                 macro_data["fed_futures"]["change_5d_bps"] = round(change_bps, 1)

             # Japan Change (%)
             japan_price = macro_data.get("japan_macro", {}).get("price")
             change_pct = mh.get_change_percentage("japan", japan_price, days=5)
             if change_pct is not None:
                 macro_data["japan_macro"]["change_5d_pct"] = round(change_pct, 2)
                 
             print("✅ Macro History updated locally.")
        except Exception as e:
             print(f"⚠️ Macro History update failed: {e}")
        # --------------------------------
        print("Fetching Global News...")
        news_data = news_fetcher.gather_news()
        news_data = translate_news_data(news_data)
        print("✅ Macro & News fetched and translated successfully.")
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
    btc_market = market_data.get_strategy_metrics("BTC")
    bnb_market = market_data.get_strategy_metrics("BNB")   # NEW
    doge_market = market_data.get_strategy_metrics("DOGE") # NEW
    
    # NEW: Fetch Liquidation Data (The "Pain" Index)
    print("Fetching Liquidation Data (Market Pain)...")
    eth_liquidation = market_data.client.fetch_liquidation_data("ETH-USDT")
    sol_liquidation = market_data.client.fetch_liquidation_data("SOL-USDT")
    btc_liquidation = market_data.client.fetch_liquidation_data("BTC-USDT")
    bnb_liquidation = market_data.client.fetch_liquidation_data("BNB-USDT")   # NEW
    doge_liquidation = market_data.client.fetch_liquidation_data("DOGE-USDT") # NEW
    
    print(f"ETH Liq: Long ${eth_liquidation.get('long_vol_usd',0):.0f} / Short ${eth_liquidation.get('short_vol_usd',0):.0f}")
    print(f"SOL Liq: Long ${sol_liquidation.get('long_vol_usd',0):.0f} / Short ${sol_liquidation.get('short_vol_usd',0):.0f}")
    print(f"BTC Liq: Long ${btc_liquidation.get('long_vol_usd',0):.0f} / Short ${btc_liquidation.get('short_vol_usd',0):.0f}")

    print("Calculating Strategy V1 Metrics...")
    eth_analysis = analyze_transfers_v1(eth_transfers, eth_market)
    sol_analysis = analyze_transfers_v1(sol_transfers, sol_market)
    
    # Helper to create dummy analysis for chains without whale data
    def create_dummy_analysis(liq_data):
        return {
            "timeframe": "4h",
            "action_signal": "NEUTRAL",
            "stats_24h": {
                "sentiment_score": 0,
                "token_net_flow": 0,
                "stablecoin_net_flow": 0,
                "liquidation_long_usd": liq_data.get("long_vol_usd", 0),
                "liquidation_short_usd": liq_data.get("short_vol_usd", 0),
                "leverage_ratio": 0
            }
        }

    btc_analysis = create_dummy_analysis(btc_liquidation)
    bnb_analysis = create_dummy_analysis(bnb_liquidation)   # NEW
    doge_analysis = create_dummy_analysis(doge_liquidation) # NEW
    
    # Inject Liquidation Data into Stats (for JSON Output)
    eth_analysis["stats_24h"]["liquidation_long_usd"] = eth_liquidation.get("long_vol_usd", 0)
    eth_analysis["stats_24h"]["liquidation_short_usd"] = eth_liquidation.get("short_vol_usd", 0)
    eth_analysis["stats_24h"]["leverage_ratio"] = eth_market.get("oi_now", 0)
    
    sol_analysis["stats_24h"]["liquidation_long_usd"] = sol_liquidation.get("long_vol_usd", 0)
    sol_analysis["stats_24h"]["liquidation_short_usd"] = sol_liquidation.get("short_vol_usd", 0)
    sol_analysis["stats_24h"]["leverage_ratio"] = sol_market.get("oi_now", 0)
    
    # Inject Liquidation Data into Market Dicts (for AI Prompt)
    def fmt_liq(d):
        return f"Long Liquidation: ${d.get('long_vol_usd',0):,.0f}, Short Liquidation: ${d.get('short_vol_usd',0):,.0f}"
        
    eth_market["liquidation_context"] = fmt_liq(eth_liquidation)
    sol_market["liquidation_context"] = fmt_liq(sol_liquidation)
    btc_market["liquidation_context"] = fmt_liq(btc_liquidation)
    bnb_market["liquidation_context"] = fmt_liq(bnb_liquidation)   # NEW
    doge_market["liquidation_context"] = fmt_liq(doge_liquidation) # NEW
    
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

    # [NEW] Inject DefiLlama Macro Flow Data (Global Liquidity)
    print("Fetching DefiLlama Global Flows...")
    global_stable_flow = fetch_defillama_global_flows()
    if global_stable_flow != 0:
        macro_data["global_stable_flow"] = global_stable_flow

    # 5. Generate AI Narrative (V2 Tri-Layer)
    ai_summary = {"en": "AI disabled or failed.", "zh": "AI 分析暂时不可用。"}
    try:
        print("\n=== GENERATING AI TRI-LAYER ANALYSIS ===")
        # Note: Updated function signature. We pass btc_market but others are just implicit in the data struct if we wanted
        # Ideally we should pass all, but let's stick to core 3 for "Narrative" to avoid token overflow
        # AI Trader (Dolores) will read the FULL JSON anyway, so we don't strictly need them here in the summary generator.
        raw_ai_summary = generate_comparative_summary(
            eth_analysis, sol_analysis, 
            eth_market, sol_market, 
            fear_greed, 
            news_data, macro_data,
            btc_market=btc_market,
            btc_analysis=btc_analysis
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
        with open("error_log.txt", "w") as ef:
            traceback.print_exc(file=ef)
        traceback.print_exc()

    # 6. Save Final JSON
    # [SYNC FIX] Update Global Snapshot for Frontend Consistency
    SNAPSHOT_PATHS = [
        os.path.join(os.path.dirname(__file__), "../frontend/data/global_onchain_news_snapshot.json")
    ]
    
    for path in SNAPSHOT_PATHS:
        try:
            snapshot_data = {}
            if os.path.exists(path):
                with open(path, "r") as f:
                    snapshot_data = json.load(f)
            
            # 1. Sync News
            snapshot_data["news"] = {
                "items": news_data,
                "source": "Crypto_Brain_Realtime",
                "updated_at": datetime.now().isoformat()
            }

            # 2. Sync Fear & Greed
            if fear_greed:
                 old_fg = snapshot_data.get("fear_greed", {})
                 old_series = old_fg.get("series", [])
                 snapshot_data["fear_greed"] = {
                     "latest": fear_greed,
                     "series": old_series,
                     "paragraph": f"Fear & Greed: {fear_greed.get('value')} ({fear_greed.get('value_classification')})"
                 }

            # 3. Add Whale Data
            snapshot_data["whale_scan_data"] = {
                "eth_transfers": eth_transfers,
                "sol_swaps": sol_transfers,
                "updated_at": datetime.now().isoformat()
            }

            with open(path, "w") as f:
                json.dump(snapshot_data, f, indent=2)
            print(f"✅ Synced fresh data to {path}")

        except Exception as e:
            print(f"⚠️ Failed to sync snapshot to {path}: {e}")

    # --- History Tracking (New Feature) ---
    def update_history(chain_key, current_stats):
        hist = []
        try:
            if chain_key in history_data:
                hist = history_data[chain_key].get("stats_history", [])
        except: pass
        
        # New Entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "display_time": datetime.now().strftime("%H:%M"),
            "whale_count": current_stats.get("whale_count", 0),
            "total_volume": current_stats.get("total_volume", 0),
            "stablecoin_net_flow": current_stats.get("stablecoin_net_flow", 0),
            "token_net_flow": current_stats.get("token_net_flow", 0),
            "avg_tx_size": current_stats.get("avg_tx_size", 0),
            "liquidation_long_usd": current_stats.get("liquidation_long_usd", 0),
            "liquidation_short_usd": current_stats.get("liquidation_short_usd", 0),
            "leverage_ratio": current_stats.get("leverage_ratio", 0)
        }
        
        hist.append(entry)
        # Keep last 24 entries
        return hist[-24:]

    eth_history = update_history("eth", eth_analysis["stats_24h"])
    sol_history = update_history("sol", sol_analysis["stats_24h"])

    final_output = {
        "updated_at": datetime.now().isoformat(),
        "fear_greed": fear_greed,
        "macro": macro_data, 
        "news": news_data,
        "eth": {
            "stats": eth_analysis["stats_7d"], 
            "stats_24h": eth_analysis["stats_24h"],
            "stats_history": eth_history,
            "market": eth_market,
            "top_txs": eth_transfers[:1000]
        },
        "sol": {
            "stats": sol_analysis["stats_7d"],
            "stats_24h": sol_analysis["stats_24h"],
            "stats_history": sol_history,
            "market": sol_market,
            "top_txs": sol_transfers[:1000]
        },
        "btc": {
            "stats": btc_analysis["stats_24h"],
            "stats_24h": btc_analysis["stats_24h"],
            "market": btc_market
        },
        "bnb": { "stats_24h": bnb_analysis["stats_24h"], "market": bnb_market },     # NEW
        "doge": { "stats_24h": doge_analysis["stats_24h"], "market": doge_market }, # NEW
        "ai_summary": ai_summary
    }

    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(final_output, f, indent=2)
        print(f"✅ Analysis saved to {output_file}")
        
        # Sync to DB
        from db_client import db
        db.save_data("whale_analysis", final_output)
        print("✅ Analysis synced to MongoDB")
    except Exception as e:
        print(f"❌ Error saving/syncing output: {e}")
    
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
