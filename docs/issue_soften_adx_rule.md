# Issue: 放宽 ADX 趋势过滤条件，启用震荡市全天候交易能力

## 📝 问题描述
在过去的系统防守策略中，为了防止由于市场**无趋势震荡（ADX < 20）**带来的假突破与来回插针插爆静态止损点，我们在 `ai_trader.py` 的执行校验层以及提示词中，加入了名为 `ADX No-Trade Zone` 的硬性阻断规则。
这套“宁可踏空绝不挨刀”的古老防区，虽然在单边市保护了胜率，但在近期造成了**系统过早地下轿，甚至因为底层严格的拦截而错过了至少两波巨轮级别的前置吸筹右侧启动行情（处于启动前夕时，指标的 ADX 往往都还没越过 20 的门槛）**。

随着近期我们完成了【追踪止损保本与动态上移止盈】的高级战术系统 (`adjust_sl`)，机器人在弱势震荡环境中的近战护具已经全面升级，这使得 ADX < 20 时的“盈亏护城河脆弱”短板被彻底抵消。原有的刚性策略显得过于死板。

## ✨ 实现目标
- [x] **解放系统指令:** 更新系统大脑（`ai_trader.py` 的 `SYSTEM_PROMPT`），将 ADX < 20 的禁止状态改为“允许进入但须保持谨慎”的 `ADX Choppy Zone` 状态。
- [x] **战术策略配套:** 让 AI 知晓在此时可以进场，但命令其在此环境下一旦产生利润，必须**极其频繁而敏锐地利用我们刚写的动态调整命令（Dynamic SL/TP）来贴身保护订单或锁利**。
- [x] **撤除底层阻断器:** 在底层执行引擎过滤链条中，删去 `action == "REJECTED"` 的一刀切逻辑，使其转化为仅仅是记录风险日志（`⚠️ ADX Warning`），而不会再去物理截断原本极具潜力的鲸鱼跟随开单。

## 🛠 修改明细
**文件**: `backend/ai_trader.py`
1. 将 Prompt `4. ADX No-Trade Zone (HARD RULE — NEVER VIOLATE)` 模块改写为了 `4. ADX Choppy Zone (Proceed with Caution)`。
2. 明确指示该阶段开仓时的配套要求：“You ARE ALLOWED to open directional bets here, but you MUST rely heavily on your dynamic Stop-Loss and Take-Profit adjustments to survive the noise.”
3. 移除了底部执行验证代码 `valid_and_enforce_decision` 中当 `adx_val < 20` 时的拒绝接单行为，代之以警告放行通过。

## 🧪 建议的验收测试
- 观察当整体大盘进入横盘/回调低谷位开始反弹、且 ADX 仍然小于 20 的关键前夜时，机器人是否开始正常执行鲸鱼跟单（过去此处将被死死拦截）。
- 查看日志打印，确认遇到低 ADX 时控制台会打出提示 `⚠️ ADX Warning: ... Relying on Dynamic SL/TP` 而不是直接踢除这笔委托单。
