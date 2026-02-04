
import pandas as pd
import numpy as np

def compute_rsi(series: pd.Series, period: int = 14) -> float:
    """
    Compute Wilder's RSI.
    Returns the latest RSI value (float).
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).abs()
    loss = (delta.where(delta < 0, 0)).abs()

    avg_gain = gain.rolling(window=period, min_periods=PERIOD).mean() # SMMA would be accurate but EMA is close enough for short history
    # Standard Wilder's smoothing is slightly different, let's use the explicit logic if we want perfection.
    # But for efficiency, standard pandas ewm is preferred.
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def add_all_indicators(df: pd.DataFrame) -> dict:
    """
    Takes a DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    Returns a dictionary with the latest indicator values.
    """
    # Ensure numerical types
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)
    
    results = {}
    
    # 1. EMAs & SMAs
    df['sma_50'] = df['close'].rolling(window=50).mean()
    df['sma_200'] = df['close'].rolling(window=200).mean()
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    
    # 2. RSI (14)
    # Using Wilder's Smoothing
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rol_up = up.ewm(alpha=1/14, adjust=False).mean()
    rol_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = rol_up / rol_down
    df['rsi_14'] = 100.0 - (100.0 / (1.0 + rs))

    # 3. MACD (12, 26, 9)
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_line'] = exp1 - exp2
    df['signal_line'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['signal_line']

    # 4. Bollinger Bands (20, 2)
    df['bb_mid'] = df['close'].rolling(window=20).mean()
    df['bb_std'] = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * 2)
    df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2)
    # %B = (Price - Lower) / (Upper - Lower)
    df['bb_pct_b'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    # Bandwidth = (Upper - Lower) / Mid
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']

    # 5. ATR (14) - Average True Range
    # TR = Max(H-L, |H-Cp|, |L-Cp|)
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift())
    df['tr2'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr_14'] = df['tr'].ewm(alpha=1/14, adjust=False).mean()
    # Normalized ATR (Volatility %)
    df['natr'] = (df['atr_14'] / df['close']) * 100

    # 6. ADX (14) - Trend Strength
    # +DM = H - PrevH, -DM = PrevL - L
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']
    
    df['pdm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
    df['ndm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)
    
    df['pdm_ema'] = df['pdm'].ewm(alpha=1/14, adjust=False).mean()
    df['ndm_ema'] = df['ndm'].ewm(alpha=1/14, adjust=False).mean()
    df['tr_ema'] = df['tr'].ewm(alpha=1/14, adjust=False).mean()
    
    df['p_di'] = 100 * (df['pdm_ema'] / df['tr_ema'].replace(0, 1e-9))
    df['n_di'] = 100 * (df['ndm_ema'] / df['tr_ema'].replace(0, 1e-9))
    
    # Restore ADX Calculation
    di_sum = (df['p_di'] + df['n_di']).replace(0, 1e-9)
    df['dx'] = 100 * abs(df['p_di'] - df['n_di']) / di_sum
    df['adx_14'] = df['dx'].ewm(alpha=1/14, adjust=False).mean()
    
    # 7. Price Percentile (Window 20 - Matching Reference Repo)
    # 0 = Lowest Low in last 20 bars, 1 = Highest High
    lookback = 20
    # Rolling rank is tricky in pandas without apply, let's use min/max normalization which is close enough for High/Low detection
    # The reference repo uses rank(pct=True). Let's stick to min-max scalar which is faster and semantically similar for "Extreme" detection.
    roll_min = df['low'].rolling(window=lookback).min()
    roll_max = df['high'].rolling(window=lookback).max()
    # Avoid division by zero
    denom = (roll_max - roll_min).replace(0, 1)
    df['price_percentile_20'] = (df['close'] - roll_min) / denom
    
    # 8. Volume Anomalies (Window 20 - Matching Reference Repo)
    # Ratio of current volume to 20-period MA
    df['vol_ma_20'] = df['volume'].rolling(window=20).mean()
    df['vol_ratio_20'] = df['volume'] / df['vol_ma_20']

    # --- SIGNAL LOGIC (Replicating compute_signal_info) ---
    # Masks
    # Low Price (< 10%) AND High Vol (> 2.0x)
    low_high_mask = (df['price_percentile_20'] < 0.10) & (df['vol_ratio_20'] > 2.0)
    # High Price (> 90%) AND High Vol (> 2.0x)
    high_high_mask = (df['price_percentile_20'] > 0.90) & (df['vol_ratio_20'] > 2.0)
    
    # RSI Condition
    rsi_overbought = df['rsi_14'] > 70
    rsi_oversold = df['rsi_14'] < 30
    
    # ADX Condition (Trend Strength > 40 is considered "Extreme")
    adx_threshold = 40
    # +DI > -DI (Uptrend)
    adx_up_trend = (df['p_di'] > df['n_di']) & (df['adx_14'] > adx_threshold)
    # -DI > +DI (Downtrend)
    adx_down_trend = (df['n_di'] > df['p_di']) & (df['adx_14'] > adx_threshold)
    
    # Star Calculation
    # Buy Stars (Counter-trend / Exhaustion indicators)
    # 1. RSI Oversold
    # 2. Low Price + High Vol (Panic Selling / Accumulation)
    # 3. strong Down Trend (Possible Exhaustion? Reference repo adds this. We keep it.)
    df['buy_stars'] = (
        rsi_oversold.astype(int) + 
        low_high_mask.astype(int) + 
        adx_down_trend.astype(int)
    )
    
    # Sell Stars
    # 1. RSI Overbought
    # 2. High Price + High Vol (Climax / Distribution)
    # 3. Strong Up Trend
    df['sell_stars'] = (
        rsi_overbought.astype(int) + 
        high_high_mask.astype(int) + 
        adx_up_trend.astype(int)
    )

    # --- Extract Latest Values ---
    if df.empty:
        raise ValueError("Cannot extract technicals: DataFrame is empty.")
        
    latest = df.iloc[-1]
    
    # STRICT VALIDATION: Check for Critical Columns
    # We do NOT want to return fake 0.0 values.
    required_cols = ['rsi_14', 'adx_14', 'bb_width', 'price_percentile_20', 'vol_ratio_20']
    for col in required_cols:
        if col not in df.columns:
             # Try to debug why: maybe not enough data?
             raise KeyError(f"Missing critical indicator '{col}'. Input DF length: {len(df)}. "
                            "Likely insufficient history for calculation.")
    
    def get_strict(key):
        val = latest[key]
        if pd.isna(val):
             # If the latest value itself is NaN (e.g. calculation didn't propagate to the end), that's also bad.
             raise ValueError(f"Indicator '{key}' is NaN in the latest candle. Calculation incomplete.")
        return float(val)

    results = {
        # Trend
        "price_close": float(latest['close']),
        "sma_50": get_strict('sma_50'),
        "sma_200": get_strict('sma_200'),
        "macd_line": get_strict('macd_line'),
        "signal_line": get_strict('signal_line'),
        "macd_hist": get_strict('macd_hist'),
        "adx_14": get_strict('adx_14'),
        "p_di": get_strict('p_di'), 
        "n_di": get_strict('n_di'),
        
        # Momentum / Osc
        "rsi_14": get_strict('rsi_14'),
        
        # Volatility / Bands
        "bb_pct_b": get_strict('bb_pct_b'),
        "bb_width": get_strict('bb_width'),
        "atr_14": get_strict('atr_14'),
        "natr_percent": get_strict('natr'),
        
        # Context / Rank / Signals
        "price_rank_20": get_strict('price_percentile_20') * 100, 
        "vol_ratio_20": get_strict('vol_ratio_20'),
        
        # Star Signals
        "signal_low_high_vol": bool(latest['price_percentile_20'] < 0.10 and latest['vol_ratio_20'] > 2.0),
        "signal_high_high_vol": bool(latest['price_percentile_20'] > 0.90 and latest['vol_ratio_20'] > 2.0),
        "buy_stars": int(latest['buy_stars']),
        "sell_stars": int(latest['sell_stars'])
    }

    
    return results

def get_signal_history(df: pd.DataFrame, limit: int = 60) -> list:
    """
    Extracts the last `limit` rows of data with computed signals.
    Returns a list of dictionaries suitable for frontend plotting (JSON).
    """
    # Ensure all indicators are present (assuming add_all_indicators logic was run on this df, 
    # but the df passed here might be the one returned from that function? 
    # Actually add_all_indicators modifies df in place mostly. 
    # Better to assume df has columns.)
    
    # We need to re-run or rely on columns existing. 
    # In our flow, we calc everything in add_all_indicators but we didn't return the DF, we returned a dict.
    # So we need to modify add_all_indicators to return the DF or allow access to it.
    # WAIT: add_all_indicators took a df and modified it in place?
    # Yes, pandas operations like df['col'] = ... modify in place.
    
    subset = df.iloc[-limit:].copy()
    history = []
    
    for idx, row in subset.iterrows():
        # Handle NaN safely
        def safe_float(val, precision=2):
            try:
                if pd.isna(val): return None
                return round(float(val), precision)
            except: return None
            
        def safe_bool(val):
            try:
                if pd.isna(val): return False
                return bool(val)
            except: return False
            
        # Re-construct masks for this row if not in columns, or assume columns exist from previous step
        # Since we just added columns in add_all_indicators, they should be there.
        
        entry = {
            "ts": row.get('ts'), # String or int from OKX
            "date": pd.to_datetime(int(row.get('ts')), unit='ms').strftime('%Y-%m-%d %H:%M') if 'ts' in row else "",
            "close": safe_float(row.get('close')),
            "volume": safe_float(row.get('volume'), 0),
            "rsi_14": safe_float(row.get('rsi_14')),
            "adx_14": safe_float(row.get('adx_14')),
            "vol_ratio": safe_float(row.get('vol_ratio_20')),
            "price_rank": safe_float(row.get('price_percentile_20') * 100 if 'price_percentile_20' in row else 50, 1),
            "buy_stars": int(row.get('buy_stars', 0)),
            "sell_stars": int(row.get('sell_stars', 0)),
            "signals": {
                "low_vol": safe_bool((row.get('price_percentile_20', 0.5) < 0.10) and (row.get('vol_ratio_20', 1) > 2.0)),
                "high_vol": safe_bool((row.get('price_percentile_20', 0.5) > 0.90) and (row.get('vol_ratio_20', 1) > 2.0)),
                "rsi_low": safe_bool(row.get('rsi_14', 50) < 30),
                "rsi_high": safe_bool(row.get('rsi_14', 50) > 70)
            }
        }
        history.append(entry)
        
    return history
