import os
import pandas as pd
import numpy as np
import datetime
import time
import json
from pathlib import Path
from market_data import OKXDataClient
from technical_analysis import add_all_indicators

# Configuration
BASE_DIR = Path(__file__).resolve().parent
QLIB_DATA_DIR = BASE_DIR / "qlib_data"
CSV_PATH = QLIB_DATA_DIR / "multi_coin_features.csv"
BIN_DIR = QLIB_DATA_DIR / "bin_multi_coin"
SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "DOGE"]
SCHEMA_COLUMNS = [
    'datetime', 'instrument', 'open', 'high', 'low', 'close', 'volume',
    'ret', 'log_return', 'ma_5', 'ma_20', 'ma_60', 'ma_cross', 'momentum_12',
    'macd', 'macd_signal', 'macd_hist', 'atr_14', 'bb_width_20', 'bb_pos_20',
    'volatility_20', 'rsi_14', 'volume_ma_20', 'rel_volume_20', 'price_position_20',
    'funding_rate', 'funding_rate_zscore', 'open_interest', 'oi_change', 'oi_rsi',
    'btc_corr_24h', 'natr_14', 'buy_stars', 'sell_stars',
    'volume_usd_4h', 'liquidation_long_usd', 'liquidation_short_usd',
    'liquidation_long_to_volume_4h', 'liquidation_short_to_volume_4h',
    'token_net_flow_4h', 'stablecoin_net_flow_4h',
    'token_net_flow_24h', 'stablecoin_net_flow_24h',
    'future_4h_ret', 'future_24h_ret'
]


def ensure_csv_schema():
    if not CSV_PATH.exists():
        return

    df = pd.read_csv(CSV_PATH)
    changed = False

    if 'volume_usd_4h' not in df.columns:
        # Existing `volume` already uses OKX volCcyQuote, which is the quote-currency notional.
        df['volume_usd_4h'] = df['volume']
        changed = True

    for col in [
        'liquidation_long_usd',
        'liquidation_short_usd',
        'liquidation_long_to_volume_4h',
        'liquidation_short_to_volume_4h',
        'token_net_flow_4h',
        'stablecoin_net_flow_4h',
        'token_net_flow_24h',
        'stablecoin_net_flow_24h',
    ]:
        if col not in df.columns:
            df[col] = np.nan
            changed = True

    missing_cols = [col for col in SCHEMA_COLUMNS if col not in df.columns]
    for col in missing_cols:
        df[col] = np.nan
        changed = True

    if changed or list(df.columns) != SCHEMA_COLUMNS:
        df = df[SCHEMA_COLUMNS]
        df.to_csv(CSV_PATH, index=False)
        print("✅ Qlib CSV schema updated with volume/liquidation columns.")

def get_last_date_from_csv():
    if not CSV_PATH.exists():
        return None
    try:
        # Read only the last few lines to find the date efficiently
        df_last = pd.read_csv(CSV_PATH).tail(10)
        df_last['datetime'] = pd.to_datetime(df_last['datetime'])
        return df_last['datetime'].max()
    except Exception as e:
        print(f"⚠️ Error reading CSV last date: {e}")
        return None

def fetch_and_process_missing_data(start_date):
    client = OKXDataClient()
    all_new_rows = []
    
    now = datetime.datetime.now()
    print(f"🚀 Updating Qlib Data from {start_date} to {now}...")

    for symbol in SYMBOLS:
        print(f"  Fetching {symbol}...")
        inst_id = f"{symbol}-USDT-SWAP"
        
        # 1. Fetch OHLCV (4H)
        # We need to fetch enough history for indicators (SMA200 needs 200 bars)
        # To be safe, we fetch 500 bars including the missing ones.
        # But for appending, we only keep the ones AFTER start_date.
        
        limit = 300
        data = client._request("GET", "/api/v5/market/candles", {"instId": inst_id, "bar": "4H", "limit": str(limit)})
        if not data:
            print(f"  ⚠️ No data returned for {symbol}!")
            continue
        
        print(f"  Fetched {len(data)} candles for {symbol}.")
            
        df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'volCcy', 'volCcyQuote', 'confirm'])
        df = df.iloc[::-1].reset_index(drop=True)
        df['datetime'] = pd.to_datetime(df['ts'].astype(int), unit='ms')
        
        # Prepare for Technical Indicators
        df_input = df[['datetime', 'open', 'high', 'low', 'close', 'volCcyQuote']].copy()
        df_input.columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        
        # 2. Calculate Indicators (Matching multi_coin_features.csv schema)
        # Using technical_analysis.py's add_all_indicators
        # We need to ensure we have all required columns: ma_5, ma_20, ma_60, momentum_12, etc.
        
        # Note: multi_coin_features.csv has some specific column names: ma_5, ma_20, ma_60
        # technical_analysis calculates sma_50, sma_200 etc. Let's adapt.
        
        df_feats = df_input.copy()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df_feats[col] = df_feats[col].astype(float)
            
        # Ma
        df_feats['ma_5'] = df_feats['close'].rolling(5).mean()
        df_feats['ma_20'] = df_feats['close'].rolling(20).mean()
        df_feats['ma_60'] = df_feats['close'].rolling(60).mean()
        df_feats['ma_cross'] = np.where(df_feats['ma_5'] > df_feats['ma_20'], 1, -1)
        
        # Returns
        df_feats['ret'] = df_feats['close'].pct_change()
        df_feats['log_return'] = np.log(df_feats['close'] / df_feats['close'].shift(1))
        
        # Momentum
        df_feats['momentum_12'] = df_feats['close'].pct_change(12)
        
        # MACD
        exp1 = df_feats['close'].ewm(span=12, adjust=False).mean()
        exp2 = df_feats['close'].ewm(span=26, adjust=False).mean()
        df_feats['macd'] = exp1 - exp2
        df_feats['macd_signal'] = df_feats['macd'].ewm(span=9, adjust=False).mean()
        df_feats['macd_hist'] = df_feats['macd'] - df_feats['macd_signal']
        
        # ATR
        tr0 = abs(df_feats['high'] - df_feats['low'])
        tr1 = abs(df_feats['high'] - df_feats['close'].shift())
        tr2 = abs(df_feats['low'] - df_feats['close'].shift())
        tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)
        df_feats['atr_14'] = tr.rolling(14).mean()
        df_feats['natr_14'] = (df_feats['atr_14'] / df_feats['close']) * 100
        
        # Bollinger
        df_feats['ma_20_std'] = df_feats['close'].rolling(20).std()
        df_feats['bb_width_20'] = (df_feats['ma_20_std'] * 4) / df_feats['ma_20']
        df_feats['bb_pos_20'] = (df_feats['close'] - (df_feats['ma_20'] - 2*df_feats['ma_20_std'])) / (4*df_feats['ma_20_std'])
        df_feats['volatility_20'] = df_feats['ma_20_std'] / df_feats['ma_20']
        
        # RSI
        delta = df_feats['close'].diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ema_up = up.ewm(alpha=1/14, adjust=False).mean()
        ema_down = down.ewm(alpha=1/14, adjust=False).mean()
        rs = ema_up / ema_down
        df_feats['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Volume
        df_feats['volume_ma_20'] = df_feats['volume'].rolling(20).mean()
        df_feats['rel_volume_20'] = df_feats['volume'] / df_feats['volume_ma_20']
        # OKX `volCcyQuote` is quote-currency notional, so reuse it as 4H USD volume proxy.
        df_feats['volume_usd_4h'] = df_feats['volume']
        
        # Range Pos
        roll_min = df_feats['low'].rolling(20).min()
        roll_max = df_feats['high'].rolling(20).max()
        df_feats['price_position_20'] = (df_feats['close'] - roll_min) / (roll_max - roll_min + 1e-9)
        
        # Stars (mock or simplified)
        df_feats['buy_stars'] = 0
        df_feats['sell_stars'] = 0
        
        # Funding & OI with REAL DATA
        try:
            # 1. Real Funding Rate History
            fr_data = client._request("GET", "/api/v5/public/funding-rate-history", {"instId": inst_id, "limit": "100"})
            if fr_data:
                df_fr = pd.DataFrame(fr_data)[['fundingTime', 'fundingRate']]
                df_fr['datetime'] = pd.to_datetime(df_fr['fundingTime'].astype(int), unit='ms')
                df_fr['fundingRate'] = df_fr['fundingRate'].astype(float)
                df_fr = df_fr.sort_values('datetime')
                
                df_feats = df_feats.sort_values('datetime')
                df_feats = pd.merge_asof(df_feats, df_fr[['datetime', 'fundingRate']], on='datetime', direction='backward')
                df_feats['funding_rate'] = df_feats['fundingRate'].fillna(0.0)
                
                mean_fr = df_feats['funding_rate'].rolling(30, min_periods=1).mean()
                std_fr = df_feats['funding_rate'].rolling(30, min_periods=1).std() + 1e-9
                df_feats['funding_rate_zscore'] = (df_feats['funding_rate'] - mean_fr) / std_fr
            else:
                df_feats['funding_rate'] = 0.0
                df_feats['funding_rate_zscore'] = 0.0
                
            # 2. Real Open Interest History
            try:
                oi_data = client._request("GET", "/api/v5/rubik/stat/contracts/open-interest-history", {"instId": inst_id, "period": "4H", "limit": "100"})
                if oi_data and isinstance(oi_data, list):
                    df_oi = pd.DataFrame(oi_data, columns=['ts', 'oi', 'oiCcy', 'oiUsd'])
                    df_oi['datetime'] = pd.to_datetime(df_oi['ts'].astype(int), unit='ms')
                    df_oi['oi'] = df_oi['oi'].astype(float)
                    df_oi = df_oi.sort_values('datetime')
                    
                    df_feats = pd.merge_asof(df_feats, df_oi[['datetime', 'oi']], on='datetime', direction='backward')
                    df_feats['open_interest'] = df_feats['oi'].fillna(0.0)
                    df_feats['oi_change'] = df_feats['open_interest'].pct_change().fillna(0.0)
                    
                    delta = df_feats['open_interest'].diff()
                    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
                    down = -1 * delta.clip(upper=0).ewm(alpha=1/14, adjust=False).mean()
                    rs = up / down
                    df_feats['oi_rsi'] = 100 - (100 / (1 + rs))
                    df_feats['oi_rsi'] = df_feats['oi_rsi'].fillna(50.0)
                else:
                    df_feats['open_interest'] = 0.0
                    df_feats['oi_change'] = 0.0
                    df_feats['oi_rsi'] = 50.0
            except Exception:
                df_feats['open_interest'] = 0.0
                df_feats['oi_change'] = 0.0
                df_feats['oi_rsi'] = 50.0
                
        except Exception as e:
            print(f"⚠️ Error fetching sentiment history for {symbol}: {e}")
            df_feats['funding_rate'] = 0.0
            df_feats['funding_rate_zscore'] = 0.0
            df_feats['open_interest'] = 0.0
            df_feats['oi_change'] = 0.0
            df_feats['oi_rsi'] = 50.0

        # Liquidation snapshot is available for the latest market state, but not as full historical 4H series.
        # Keep historical rows empty unless we are appending the newest bar, where a point-in-time snapshot is acceptable.
        df_feats['liquidation_long_usd'] = np.nan
        df_feats['liquidation_short_usd'] = np.nan
        df_feats['liquidation_long_to_volume_4h'] = np.nan
        df_feats['liquidation_short_to_volume_4h'] = np.nan
        try:
            liq_data = client.fetch_liquidation_data(f"{symbol}-USDT")
            if liq_data and not df_feats.empty:
                latest_idx = df_feats.index[-1]
                long_liq = float(liq_data.get("long_vol_usd", 0.0) or 0.0)
                short_liq = float(liq_data.get("short_vol_usd", 0.0) or 0.0)
                latest_volume_usd = float(df_feats.loc[latest_idx, 'volume_usd_4h'] or 0.0)
                denom = latest_volume_usd if latest_volume_usd > 0 else np.nan
                df_feats.loc[latest_idx, 'liquidation_long_usd'] = long_liq
                df_feats.loc[latest_idx, 'liquidation_short_usd'] = short_liq
                df_feats.loc[latest_idx, 'liquidation_long_to_volume_4h'] = long_liq / denom if pd.notna(denom) else np.nan
                df_feats.loc[latest_idx, 'liquidation_short_to_volume_4h'] = short_liq / denom if pd.notna(denom) else np.nan
        except Exception as e:
            print(f"⚠️ Error fetching liquidation snapshot for {symbol}: {e}")

        # Historical chain flow is backfilled by a separate script.
        df_feats['token_net_flow_4h'] = np.nan
        df_feats['stablecoin_net_flow_4h'] = np.nan
        df_feats['token_net_flow_24h'] = np.nan
        df_feats['stablecoin_net_flow_24h'] = np.nan

        df_feats['btc_corr_24h'] = 1.0 # default
        
        # Targets (set to 0 for inference)
        df_feats['future_4h_ret'] = 0.0
        df_feats['future_24h_ret'] = 0.0
        
        # Prepare for merging
        df_feats['instrument'] = symbol
        
        # Filter only NEW data
        new_df = df_feats[df_feats['datetime'] > start_date].copy()
        if not new_df.empty:
            all_new_rows.append(new_df[SCHEMA_COLUMNS])
            
    if all_new_rows:
        combined_new = pd.concat(all_new_rows)
        # Format datetime back to string
        combined_new['datetime'] = combined_new['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
        return combined_new
    return None

def update_qlib_binary():
    """Convert CSV to binary format for Qlib."""
    print("📥 Dumping data to Qlib format via run_dump.py...")
    import subprocess
    import sys
    try:
        # Avoid circular dependencies, just call the CLI
        cmd = [sys.executable, "run_dump.py"]
        # Run inside backend directory
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(cmd, cwd=backend_dir, check=True)
    except Exception as e:
        print(f"❌ Failed to update binaries: {e}")

def main():
    ensure_csv_schema()
    last_date = get_last_date_from_csv()
    if not last_date:
        print("❌ Could not find starting date in CSV.")
        return

    new_data = fetch_and_process_missing_data(last_date)
    
    if new_data is not None and not new_data.empty:
        print(f"📝 Appending {len(new_data)} new records to CSV...")
        new_data.to_csv(CSV_PATH, mode='a', header=False, index=False)
        print("✅ CSV updated.")
        
        # Now update BIN
        update_qlib_binary()
    else:
        print("✅ Data is already up to date.")

if __name__ == "__main__":
    main()
