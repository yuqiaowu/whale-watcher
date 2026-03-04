# Issue: 修复前端“代币流量 (Token Flow)”归零及情绪分数偏差的 Bug

## 📝 问题描述 (Bug Report)
监控面板前端经常出现“代币流量（Token Flow）”长期为 `0` 的异常情况。
经排查底层数据处理模块 (`backend/crypto_brain.py`)，发现在 `analyze_transfers_v1` 函数中存在一段过度严格的隔离过滤代码：
```python
if symbol not in STABLECOINS and symbol != target_symbol:
    continue
```
由于该逻辑，任何非稳定币（USDT/USDC）且非目标原生代币（如 ETH 或 SOL）的巨鲸转账事件（例如系统原本应该监听的 SHIB、PEPE、LINK、WETH 等重要风向标代币的千万级别大单抛售或吸筹）会被系统直接丢弃。
这不仅导致了面板上以太坊等链的代币总流量统计残缺，更导致 AI 进行全局**情绪评分 (Sentiment Score)** 和**操作信心分 (Confidence Score)** 的计算时“以偏概全”，失去了对周边山寨市场大资金动向的感知。

## ✨ 修复目标 (Resolution)
- [x] **移除过度过滤:** 删除由 `crypto_brain.py` 错误引入的 `target_symbol` 隔离墙，让系统重新放行所有配置文件 `TOKENS` 白名单内的链上大额转账事件。
- [x] **恢复流量统计:** 确保巨鲸对重要山寨币/Meme 币的操作金额能重新被正确累加至 `token_net_flow` 和 `token` 累加器中。
- [x] **数据反馈闭环:** 经过平方根（`math.sqrt`）权重的计算，这部分流失的庞大金额将被修正回 AI 每天的 `w_score` 总分池子中，使其预判大盘变盘的指标更加敏感。

## 🛠 修改明细 (Changelog)
**文件**: `backend/crypto_brain.py` -> `analyze_transfers_v1` 方法。
- **删除了以下代码行**：
  ```python
  if symbol not in STABLECOINS and symbol != target_symbol:
      continue
  ```
- **保留了基础业务流**：代币属性分离判定依然完整（稳定币进入 `stable`，其他所有非稳定币通证准确流入 `token` 作为行情燃料参考）。

## 🧪 验证结果 (Verification)
- 后端脚本重新拉取区块解析时，不会再将非 ETH 的链上白名单资产丢弃。
- 经过下一轮定时同步 (`trigger_sync.py` 或由系统 Cronjob 触发的大脑刷新)，前端 Web 面板的“代币流量”图表将长出真实的直方图数据。AI 得分引擎重回完全体。
