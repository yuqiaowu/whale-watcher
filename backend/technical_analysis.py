
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
    
    df['p_di'] = 100 * (df['pdm_ema'] / df['tr_ema'])
    df['n_di'] = 100 * (df['ndm_ema'] / df['tr_ema'])
    
    df['dx'] = 100 * abs(df['p_di'] - df['n_di']) / (df['p_di'] + df['n_di'])
    df['adx_14'] = df['dx'].ewm(alpha=1/14, adjust=False).mean()

    # --- Extract Latest Values ---
    latest = df.iloc[-1]
    
    results = {
        # Trend
        "price_close": float(latest['close']),
        "sma_50": float(latest['sma_50']) if not pd.isna(latest['sma_50']) else 0,
        "sma_200": float(latest['sma_200']) if not pd.isna(latest['sma_200']) else 0,
        "macd_line": float(latest['macd_line']),
        "signal_line": float(latest['signal_line']),
        "macd_hist": float(latest['macd_hist']),
        "adx_14": float(latest['adx_14']),
        "p_di": float(latest['p_di']), # Positive Directional Index
        "n_di": float(latest['n_di']), # Negative Directional Index
        
        # Momentum / Osc
        "rsi_14": float(latest['rsi_14']),
        
        # Volatility / Bands
        "bb_pct_b": float(latest['bb_pct_b']),
        "bb_width": float(latest['bb_width']),
        "atr_14": float(latest['atr_14']),
        "natr_percent": float(latest['natr'])
    }
    
    return results
