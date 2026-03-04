# Issue: AI Trading Autonomy & Fractional Risk Management Upgrade

## 📌 Background & Motivation
The AI trading system previously suffered from two major limitations that negatively impacted its execution efficiency and risk management:

1. **The "Right-Side Breakout" Trap (Over-Constrained Entry):** 
   The AI was frequently identifying excellent entry setups based on whale accumulation, extreme negative funding, and liquidation squeezes. However, a hardcoded Python verification layer forced a `WAIT` state if the exact 4-hour candle close hadn't mathematically broken the previous 5-candle high/low. Because LLMs lack "visual chart logic" and struggle with precise decimal comparisons, the AI often felt compelled to declare a "breakout" prematurely. The physical code block would then slap it down, resulting in a conflicting loop where the AI wanted to enter but was blocked, missing the exact left-side optimal entries it correctly identified.

2. **The "Rollercoaster Ride" (All-or-Nothing Exit Constraint):**
   Once in a profitable position, the AI's action menu only allowed it to `hold`, `adjust_sl` (trail stop loss), or `close_position` (100% exit). This binary approach meant the AI could not scale out of positions (e.g., locking in partial profits at resistance while letting the rest run). Furthermore, the naming of `adjust_sl` caused the AI to forget it could also adjust the Take Profit (`take_profit`) upwards, leading to unrealized floating profits turning back into break-even or minor losses during volatility.

## 🛠 Enhancements Deployed

### 1. Complete Removal of Constraints (Total Autonomy)
- **Prompt Overhaul (`ai_trader.py`):** Completely eradicated all mentions of "Right-side Breakout", "Left Signal, Right Entry", and rules forcing the AI to strictly wait for previous high/low clearance. The AI now has 100% tactical firing rights to execute `OPEN_LONG` or `OPEN_SHORT` based on holistic data confluence.
- **Verification Layer Removal (`ai_trader.py`):** Deleted the 40-line `Verify Right-Side Breakout` block that previously hijacked the AI's intent and forcibly overwrote `open` actions into `WAIT`. 

### 2. Fractional Position Reduction (Scale-Out Profit Taking)
- **Menu Expansion (`ai_trader.py`):** Introduced three new granular commands for existing positions:
  - `reduce_25`: Close 25% of the position when detecting emerging risks or declining momentum.
  - `reduce_50`: Close 50% of the position when hitting major resistance/support but the macro trend survives.
  - `reduce_75`: Close 75% of the position when the trend is severely weakening.
- **Execution Engine Support (`okx_executor.py`):** Rewrote the OKX payload logic and Shadow State calculator to intercept `reduce_` commands. It now accurately calculates the proportional contract size (e.g., 25% of 102 contracts) to close, cleanly adjusts remaining margins, and correctly logs partial PnL.

### 3. Renaming for Clarification (Take Profit Trailing)
- **Menu Renamed (`ai_trader.py`, `okx_executor.py`):** Changed the `adjust_sl` action keyword to `adjust_sl_tp` across the entire stack.
- **Explicit Instruction:** Added a direct command within the prompt explicitly telling the AI: *"Update `stop_loss` AND/OR `take_profit` parameters to trail profits or adapt to new resistance/support."* This ensures the AI actively protects floating profits instead of passively riding market waves.

## 🎯 Expected Outcomes
- **Faster Entries:** The AI will enter squeeze opportunities and whale accumulations immediately without waiting for lagging candle confirmation.
- **Smoother Equity Curve:** The AI will now secure partial profits (`reduce_50`) into strength instead of helplessly watching a 10% floating profit evaporate in a sudden crypto wick.
- **Reduced "Log Schizophrenia":** The logs will map directly to the AI's actions without the confusing paradox of "saying it's waiting while the executor attempts to buy."
