# Railway 环境变量清单

这份清单对应当前 `deploy/v3-railway` 分支。

部署目标：
- 后端运行在 Railway
- 数据库使用 MongoDB
- 默认每 `2` 小时调度一次
- 决策主周期仍为 `4H`
- 交易模式先使用 `DEMO`

## 1. 必填变量

### `MONGODB_URI`
- 用途：后端 MongoDB 连接串
- 作用：保存
  - cycle 记录
  - trade records
  - latest records
  - system run history
- 示例：
```env
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
```

### `OPENAI_API_KEY`
- 用途：研究/复盘等 AI 调用
- 作用：
  - `Research`
  - `Post-Trade Review`
  - 其他 LLM 辅助层
- 示例：
```env
OPENAI_API_KEY=sk-...
```

### `TRADING_MODE`
- 用途：决定执行模式
- 可选值：
  - `SHADOW`：本地影子执行，不真正请求 OKX 下单
  - `DEMO`：OKX 模拟盘
  - `REAL`：OKX 实盘
- 当前建议：
```env
TRADING_MODE=DEMO
```

### `RUN_INTERVAL_HOURS`
- 用途：后台调度频率
- 当前建议：
```env
RUN_INTERVAL_HOURS=2
```

### `DECISION_TIMEFRAME_HOURS`
- 用途：正式决策周期
- 当前建议：
```env
DECISION_TIMEFRAME_HOURS=4
```

### `SKIP_DUPLICATE_DECISION_CYCLE`
- 用途：避免在同一根 `4H` bar 上重复生成决策
- 当前建议：
```env
SKIP_DUPLICATE_DECISION_CYCLE=1
```

### `LOCAL_TIMEZONE`
- 用途：本地时间展示
- 当前建议：
```env
LOCAL_TIMEZONE=Asia/Shanghai
```

## 2. OKX 交易相关

这些变量在 `TRADING_MODE=DEMO` 或 `TRADING_MODE=REAL` 时需要。

### `OKX_API_KEY`
- 用途：OKX API Key
- 来源：你在 OKX 创建的 API Key

### `OKX_SECRET_KEY`
- 用途：OKX API Secret
- 来源：对应 API Key 的 Secret

### `OKX_PASSPHRASE`
- 用途：OKX API Passphrase
- 来源：创建 API Key 时你自己设置的密码短语

示例：
```env
OKX_API_KEY=your_okx_api_key
OKX_SECRET_KEY=your_okx_secret_key
OKX_PASSPHRASE=your_okx_passphrase
```

说明：
- 如果你要跑 `DEMO`，这里也填这三个。
- 当前执行器默认就是读取这三个变量名。

## 3. 数据源相关

### `ETHERSCAN_API_KEY`
- 用途：ETH 链上历史 flow 回填、交易所地址相关查询
- 来源：Etherscan API

### `MORALIS_API_KEY`
- 用途：链上数据主 API 之一
- 来源：Moralis

### `MORALIS_API_KEY_2`
- 用途：Moralis 备用 key
- 来源：Moralis 第二个 key

### `HELIUS_API_KEY`
- 用途：Solana 历史增强交易数据
- 来源：Helius

### `ALCHEMY_SOLANA_API_KEY`
- 用途：Solana RPC / 历史辅助查询
- 来源：Alchemy

示例：
```env
ETHERSCAN_API_KEY=your_etherscan_key
MORALIS_API_KEY=your_moralis_key
MORALIS_API_KEY_2=your_second_moralis_key
HELIUS_API_KEY=your_helius_key
ALCHEMY_SOLANA_API_KEY=your_alchemy_key
```

## 4. Railway 上建议直接填写的完整模板

把下面这段作为模板，值替换成你自己的：

```env
MONGODB_URI=
OPENAI_API_KEY=

TRADING_MODE=DEMO
RUN_INTERVAL_HOURS=2
DECISION_TIMEFRAME_HOURS=4
SKIP_DUPLICATE_DECISION_CYCLE=1
LOCAL_TIMEZONE=Asia/Shanghai

OKX_API_KEY=
OKX_SECRET_KEY=
OKX_PASSPHRASE=

ETHERSCAN_API_KEY=
MORALIS_API_KEY=
MORALIS_API_KEY_2=
HELIUS_API_KEY=
ALCHEMY_SOLANA_API_KEY=
```

## 5. 部署后检查

部署完成后优先检查这些接口：

### `GET /api/health`
- 看服务是否活着
- 看 Mongo 是否连上
- 看最新 run 状态

### `GET /api/admin/latest-run`
- 看最近一次后台调度有没有跑完

### `GET /api/admin/runs`
- 看最近多次运行记录

## 6. 推荐上线顺序

### 第一步
```env
TRADING_MODE=DEMO
```

### 第二步
确认：
- 服务正常
- Mongo 正常
- 调度正常
- 有 run history

### 第三步
再决定要不要切：
```env
TRADING_MODE=REAL
```

## 7. 当前不建议的做法

不要一开始就：
```env
TRADING_MODE=REAL
```

因为你应该先确认：
- Railway 部署正常
- 后台调度正常
- API 正常
- 决策链路正常
- 运行记录和复盘记录能正常落库
