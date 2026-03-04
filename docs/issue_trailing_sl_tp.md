# Issue: 为 AI 交易模型实现动态止盈止损（移动止损与追踪锁利）

## 📝 问题描述
当前的 AI 交易模型 (`ai_trader.py`) 仅在开仓的瞬间设置一次固定的止损 (SL) 和止盈 (TP)。一旦订单生效，AI 就失去了“修改”这些价位的能力与权限（比如无法在浮盈时把止损位上调来保护本金，也无法在趋势大好时上调止盈让利润奔跑）。为了优化胜率和拉高盈亏比，系统的两端（AI 大脑提示词 和 OKX 订单执行器）都需要进行大重构，使其支持对存量合约订单的动态算法调仓。

## ✨ 实现目标
- [x] **赋予 AI “持仓感知”能力:** 修改 `ai_trader.py` 的系统提示词 `SYSTEM_PROMPT`，强制 AI 在开仓前“检查所有存量订单的浮盈 (`pnlPercent`)”。当浮盈突破 5% 时，AI **必须**下发追踪止损的指令。
- [x] **新增调仓动作指令 (Agent):** 给 AI 动作库添加 `adjust_sl` 指令模块。允许 AI 生成更新存量订单方案 `exit_plan`（包含修改后的 `stop_loss` 和/或 `take_profit`）的标准动作输出。
- [x] **绕过风控层拦截:** 在风控函数 `validate_and_enforce_decision` 中加入特批通道，允许 `adjust_sl` 等保本动作丝滑通过，并且不占用开仓数量的安全阈值。
- [x] **执行层对接 (Executor):** 在 `okx_executor.py` (`execute_trade`) 接住模型下发下来的 `adjust_sl` 格式指令。
- [x] **沙盒/模拟模式 (Shadow Mode) 数据流对接:** 让本地存量的模拟盘 JSON（`portfolio_state.json`）能正确处理 `adjust_sl` 逻辑并刷新账本中的预估止盈止损点位。
- [x] **实盘 OKX API 对接:**  重构了完整的双重挂单更新逻辑：自动获取已有未触发挂单 -> POST `/api/v5/trade/cancel-algos` 一键撤销过时算法单 -> 遍历双向真实仓位推导演算买卖方向 -> POST `/api/v5/trade/order-algo` 重新上膛全新的 OCO 双向止盈止损单。

## 🛠 修复细节展示
1. **Prompt 调教 (`ai_trader.py`):** 添加了强制性纪律指令：`If floating profit is > 5%, you MUST output an adjust_sl action... Update stop_loss and/or take_profit parameters in exit_plan`。
2. **底层黑名单豁免 (`ai_trader.py`):** 修复了原 `is_trade` 常量只认 `open_` 和 `close` 的隐性报错流，目前完美抓取拦截了 `adjust_sl` 并调用 `executor.execute_trade`。
3. **安全而严谨的执行引擎 (`okx_executor.py`):** 包含以下实战防呆逻辑:
   - 动态获取属于该品种的全部算法委托。
   - 对废弃或不在水里的止损限价单予以清除。
   - **循环查询仓位方向（双重保险）：** 不死板地拿数组第1个元素（防止全仓/双向开单错乱），灵活提取当前 `posSide`（多或空）来逆向决定接盘网是不是 `buy` 还是 `sell`。
   - 组装成 OCO 条件单交回 OKX 完成利润护盾。

## 🧪 建议的验收测试
- **测试方法:** 通过人工发送给 AI 特定的带强浮盈（> 5%）的持仓 JSON 给模型推理，判断它是否立刻输出了 `{"action": "adjust_sl"}`，并检查控制台 OKX/Shadow 接口是否出现修改止损成功 (`SHADOW_ADJUSTED`) 或打向 OKX 的订单反馈。
