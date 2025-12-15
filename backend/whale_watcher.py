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
MIN_VALUE_USD_SOL = 5000 # SOL Threshold (Increased to filter noise)
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
                response = requests.get(etherscan_url, params=params)
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
        response = requests.get(url, headers=headers)
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
            
            # Fetch 2 pages (~200 txs) to save API credits (Free Tier limit 40k CU/day)
            for _ in range(2):
                # Retry loop for SOL requests
                max_retries = len(API_KEYS) + 1
                response = None
                for attempt in range(max_retries):
                    # Update header with potentially new key
                    headers["X-API-Key"] = get_current_key()
                    response = requests.get(url, headers=headers, params=params)
                    
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
    """Calculate sentiment score, aggregate metrics, and top whale."""
    if not transfers:
        return {
            "sentiment_score": 0,
            "stablecoin_net_flow": 0,
            "token_net_flow": 0,
            "whale_count": 0,
            "avg_tx_size": 0,
            "total_volume": 0,
            "top_whale": {"address": "N/A", "volume": 0, "label": "N/A"}
        }

    total_score_weight = 0
    weighted_score_sum = 0
    
    stablecoin_net_flow = 0
    token_net_flow = 0
    
    unique_whales = set()
    whale_volumes = {} # Map address -> total volume
    total_volume = 0
    
    score_map = {
        "BULLISH_INFLOW": 2,
        "BULLISH_OUTFLOW": 1,
        "BEARISH_INFLOW": -2,
        "BEARISH_OUTFLOW": -1,
        "NEUTRAL": 0,
        "INTERNAL_LOOP": 0
    }

    import math

    for tx in transfers:
        amount_usd = tx["amount_usd"]
        signal = tx["signal"]
        symbol = tx["symbol"]
        address = tx["from"]
        
        total_volume += amount_usd
        unique_whales.add(address)
        
        # Track Whale Volume
        whale_volumes[address] = whale_volumes.get(address, 0) + amount_usd
        
        # 1. Sentiment Score
        weight = math.log10(amount_usd) if amount_usd > 1 else 0
        score = score_map.get(signal, 0)
        
        weighted_score_sum += score * weight
        total_score_weight += weight
        
        # 2. Net Flows (Chain Level)
        if symbol in ["USDT", "USDC", "DAI"]:
            if signal == "BULLISH_INFLOW":
                stablecoin_net_flow += amount_usd
            elif signal == "BEARISH_OUTFLOW":
                stablecoin_net_flow -= amount_usd
        else:
            if signal == "BEARISH_INFLOW":
                token_net_flow += amount_usd
            elif signal == "BULLISH_OUTFLOW":
                token_net_flow -= amount_usd

    sentiment_score = weighted_score_sum / total_score_weight if total_score_weight > 0 else 0
    
    # Identify Top Whale
    top_whale_addr = "N/A"
    top_whale_vol = 0
    if whale_volumes:
        top_whale_addr = max(whale_volumes, key=whale_volumes.get)
        top_whale_vol = whale_volumes[top_whale_addr]
        
    # Mask Address
    top_whale_label = top_whale_addr[:6] + "..." + top_whale_addr[-4:] if len(top_whale_addr) > 10 else top_whale_addr
    
    return {
        "sentiment_score": round(sentiment_score, 2),
        "stablecoin_net_flow": stablecoin_net_flow,
        "token_net_flow": token_net_flow,
        "whale_count": len(unique_whales),
        "avg_tx_size": total_volume / len(transfers) if transfers else 0,
        "total_volume": total_volume,
        "top_whale": {
            "address": top_whale_addr,
            "volume": top_whale_vol,
            "label": top_whale_label
        }
    }

def generate_comparative_summary(eth_data, sol_data, fear_greed):
    """Generate a bilingual market story comparing ETH and SOL, including Fear & Greed."""
    
    # Prepare data for prompt
    prompt_data = {
        "Macro_Sentiment": {
            "BTC_Fear_Greed_Index": f"{fear_greed['value']} ({fear_greed['value_classification']})"
        },
        "ETH_Chain (Institutional/Market)": {
            "sentiment_score": eth_data["stats"]["sentiment_score"],
            "total_volume_usd": eth_data["stats"]["total_volume"],
            "stablecoin_net_flow": eth_data["stats"]["stablecoin_net_flow"],
            "top_transfers": [
                f"{tx['amount_usd']:.0f} {tx['symbol']} ({tx['signal']})" 
                for tx in eth_data["top_txs"][:5]
            ]
        },
        "SOL_Chain (Retail/Speculative)": {
            "sentiment_score": sol_data["stats"]["sentiment_score"],
            "total_volume_usd": sol_data["stats"]["total_volume"],
            "stablecoin_net_flow": sol_data["stats"]["stablecoin_net_flow"],
            "top_transfers": [
                f"{tx['amount_usd']:.0f} {tx['symbol']} ({tx['signal']})" 
                for tx in sol_data["top_txs"][:5]
            ]
        }
    }
    
    prompt = f"""
    You are a crypto market analyst. Compare the whale sentiment on ETH vs SOL chains, considering the macro BTC Fear & Greed Index.
    
    Data:
    {json.dumps(prompt_data, indent=2)}
    
    Context:
    - BTC Fear & Greed: Macro market sentiment.
    - ETH: Institutional/Smart Money sentiment.
    - SOL: Retail/Speculative/Hot Money sentiment.
    - Sentiment Score: -2 (Strong Bearish) to +2 (Strong Bullish).
    
    Task:
    Write a short market story (max 4 sentences) comparing the two.
    1. Start with the macro mood (Fear & Greed).
    2. Contrast ETH vs SOL behavior.
    3. Give a short-term outlook.
    
    Output Format:
    JSON object:
    {{
        "en": "English story...",
        "zh": "中文市场故事..."
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean up json markdown
        if text.startswith("```json"):
            text = text[7:-3]
        return json.loads(text)
    except Exception as e:
        print(f"AI Error: {e}")
        return {
            "en": "AI analysis unavailable.",
            "zh": "AI 分析暂时不可用。"
        }

def merge_and_filter_txs(new_txs, old_txs):
    """
    Merge new and old transactions, remove duplicates, and keep only those from the last 24 hours.
    """
    # 1. Deduplicate using hash as key
    merged_map = {}
    
    # Add old first
    for tx in old_txs:
        merged_map[tx['hash']] = tx
        
    # Add new (overwrite if exists, though should be same)
    for tx in new_txs:
        merged_map[tx['hash']] = tx
        
    all_txs = list(merged_map.values())
    
    # 2. Filter last 24h
    # Use UTC to match API timestamps
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    filtered_txs = []
    
    for i, tx in enumerate(all_txs):
        try:
            # Handle timestamp format (Moralis returns ISO string usually)
            # If it's already a string, parse it.
            ts_str = tx['timestamp']
            
            # Simple ISO parser if needed, or dateutil
            # Assuming standard ISO format like "2023-10-27T10:00:00.000Z"
            # Python 3.7+ has fromisoformat but might struggle with 'Z'.
            # Let's use a robust way or just string comparison if format is consistent?
            # String comparison works for ISO format!
            
            # But we need to compare with cutoff_time which is a datetime object.
            # Let's convert cutoff_time to string for comparison? No, that's risky with timezones.
            # Let's try to parse.
            if ts_str.endswith('Z'):
                ts_str = ts_str[:-1] # Remove Z for fromisoformat
            
            tx_time = datetime.fromisoformat(ts_str)
            
            if tx_time > cutoff_time:
                filtered_txs.append(tx)
        except Exception as e:
            # If parsing fails, keep it to be safe? Or drop? 
            # Let's print error and keep if it looks recent (fallback)
            # print(f"Time parse error: {e}")
            filtered_txs.append(tx) 

    # 3. Sort by timestamp descending
    filtered_txs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    
    return filtered_txs

def recalculate_signals(transfers):
    """Re-evaluate signals for all transfers using updated EXCHANGES."""
    # EXCHANGES is global and should be normalized by now
    count_updated = 0
    for tx in transfers:
        symbol = tx["symbol"]
        
        # Addresses might be mixed case in history
        from_addr = tx["from"].lower()
        to_addr = tx["to"].lower()
        
        # Normalize in tx object too for consistency
        tx["from"] = from_addr
        tx["to"] = to_addr
        
        is_exchange_in = to_addr in EXCHANGES
        is_exchange_out = from_addr in EXCHANGES
        
        # Update labels (in case new exchanges added or fixed)
        tx["from_label"] = EXCHANGES.get(from_addr, from_addr[:6] + "...")
        tx["to_label"] = EXCHANGES.get(to_addr, to_addr[:6] + "...")
        
        signal = "NEUTRAL"
        if symbol in STABLECOINS:
            if is_exchange_in: signal = "BULLISH_INFLOW"
            if is_exchange_out: signal = "BEARISH_OUTFLOW"
        else:
            if is_exchange_in: signal = "BEARISH_INFLOW"
            if is_exchange_out: signal = "BULLISH_OUTFLOW"
            
        # Preserve Loop Logic
        if tx.get("pattern") == "INTERNAL_LOOP":
            signal = "NEUTRAL"
            
        if tx["signal"] != signal:
            tx["signal"] = signal
            count_updated += 1
            
    if count_updated > 0:
        print(f"Recalculated signals for {count_updated} transfers.")
    return transfers

def main():
    print("DEBUG: Entering whale_watcher.main()...")
    load_dotenv()
    # 1. Load History (for EMA Smoothing)
    # Use absolute path relative to this script to ensure it works in Docker
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(base_dir, "../frontend/data/whale_analysis.json")
    
    history_data = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, "r") as f:
                history_data = json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")

    # 2. Fetch Data
    output_dir = os.path.join(base_dir, "../frontend/data")
    os.makedirs(output_dir, exist_ok=True)

    print("Fetching data from Moralis (ETH)...")
    new_eth_transfers = fetch_large_transfers()
    
    print("Fetching data from Moralis (SOL)...")
    new_sol_transfers = fetch_solana_swaps()
    
    print("Fetching Fear & Greed Index...")
    fear_greed = fetch_fear_greed_index()
    print(f"Fear & Greed: {fear_greed['value']} ({fear_greed['value_classification']})")
    
    # 3. Merge with History (Keep last 24h)
    old_eth_txs = []
    if "eth" in history_data and "top_txs" in history_data["eth"]:
        old_eth_txs = history_data["eth"]["top_txs"]
        
    old_sol_txs = []
    if "sol" in history_data and "top_txs" in history_data["sol"]:
        old_sol_txs = history_data["sol"]["top_txs"]
        
    eth_transfers = merge_and_filter_txs(new_eth_transfers, old_eth_txs)
    # Recalculate signals to fix historical data with new/corrected logic
    eth_transfers = recalculate_signals(eth_transfers)
    
    sol_transfers = merge_and_filter_txs(new_sol_transfers, old_sol_txs)
    
    print(f"Merged ETH Txs: {len(new_eth_transfers)} new + {len(old_eth_txs)} old -> {len(eth_transfers)} total (24h)")
    print(f"Merged SOL Txs: {len(new_sol_transfers)} new + {len(old_sol_txs)} old -> {len(sol_transfers)} total (24h)")
    
    # 4. Analyze Data (Raw Scores)
    print("Analyzing sentiment...")
    eth_stats = analyze_transfers(eth_transfers)
    sol_stats = analyze_transfers(sol_transfers)
    
    # 5. Apply EMA Smoothing (Sentiment Stabilization)
    # Formula: New = (Current * 0.3) + (Old * 0.7)
    ALPHA = 0.3
    
    # ETH Smoothing
    old_eth_score = 0
    if "eth" in history_data and "stats" in history_data["eth"]:
        old_eth_score = history_data["eth"]["stats"].get("sentiment_score", 0)
    
    # If history exists, smooth it. If not (first run), use current raw score.
    if history_data:
        eth_stats["sentiment_score"] = round((eth_stats["sentiment_score"] * ALPHA) + (old_eth_score * (1 - ALPHA)), 2)
        print(f"ETH Sentiment Smoothed: {old_eth_score} -> {eth_stats['sentiment_score']} (Raw: {analyze_transfers(eth_transfers)['sentiment_score']})")

    # SOL Smoothing
    old_sol_score = 0
    if "sol" in history_data and "stats" in history_data["sol"]:
        old_sol_score = history_data["sol"]["stats"].get("sentiment_score", 0)
        
    if history_data:
        sol_stats["sentiment_score"] = round((sol_stats["sentiment_score"] * ALPHA) + (old_sol_score * (1 - ALPHA)), 2)
        print(f"SOL Sentiment Smoothed: {old_sol_score} -> {sol_stats['sentiment_score']} (Raw: {analyze_transfers(sol_transfers)['sentiment_score']})")

    # 6. Prepare Data Structure
    analysis_data = {
        "eth": {
            "stats": eth_stats,
            "top_txs": eth_transfers # Keep all valid 24h txs
        },
        "sol": {
            "stats": sol_stats,
            "top_txs": sol_transfers
        },
        "fear_greed": fear_greed,
        "updated_at": datetime.now().isoformat()
    }
    
    # 6. Generate AI Summary (Using Smoothed Scores + Fear Greed)
    analysis_data["ai_summary"] = generate_comparative_summary(analysis_data["eth"], analysis_data["sol"], fear_greed)

    # 7. Save Single JSON File
    with open(output_file, "w") as f:
        json.dump(analysis_data, f, indent=2)
        
    print("Done! Saved analysis to whale_analysis.json")

if __name__ == "__main__":
    main()
