# Whale Watcher V3

后端当前可以直接部署到 Railway，数据库使用 MongoDB。

## 当前部署口径

- GitHub 仓库：`origin = https://github.com/yuqiaowu/whale-watcher.git`
- Railway 运行入口：`python backend/run_loop.py`
- 数据库：`MongoDB`，环境变量为 `MONGODB_URI`
- 调度周期：默认每 `2` 小时运行一次
- 决策时间框架：`4H`
- 为避免同一根 `4H` K 线重复立案，默认会跳过重复 `cycle`

## Railway 配置

仓库根目录已经包含：

- `Dockerfile`
- `Procfile`
- `railway.json`

推荐在 Railway 中使用 Dockerfile 部署。

## 建议环境变量

至少需要：

- `MONGODB_URI`
- `OPENAI_API_KEY`
- `PORT`

调度相关：

- `RUN_INTERVAL_HOURS=2`
- `DECISION_TIMEFRAME_HOURS=4`
- `SKIP_DUPLICATE_DECISION_CYCLE=1`
- `ENABLE_V2_PIPELINE=1`

如果启用实盘/影子执行，还需要补全你当前本地 `.env` 里已有的 OKX 和其他数据源配置。

## 后台可观测接口

部署后，至少可以从这些接口看运行情况：

- `GET /api/health`
  - Railway 健康检查
  - 会返回 Mongo 连接状态、最新运行状态、最新 cycle id

- `GET /api/admin/latest-run`
  - 最近一次后台运行摘要

- `GET /api/admin/runs`
  - 最近 50 次后台运行历史

- `GET /api/v2/latest-cycle`
  - 最近一次完整决策 cycle

- `GET /api/v2/trade-records`
  - 最近的 trade decision records

- `GET /api/v2/latest-trade-record`
  - 最近一条决策记录

## 当前运行记录会保存什么

每次后台运行会落一条 `system_run_history` 记录，至少包括：

- `runId`
- `started_at / completed_at`
- `started_at_local / completed_at_local`
- `status`
- `interval_hours`
- `decision_timeframe_hours`
- `target_cycle_id`
- `cycle_id`
- `data_update_ok`
- `qlib_ok`
- `v2_cycle_status`
- `record_count`
- `approved_symbols`

所以即使没有 candidate，你也能从后台看到：

- 这次有没有真正跑完
- 有没有因为没有新 `4H` bar 而跳过
- 有没有 candidate
- 有没有批准订单

## 关于 2 小时调度

当前系统策略主周期仍然是 `4H`。  
因此把后台设成每 `2` 小时跑一次，目的是：

- 更快刷新数据
- 更快跑后台同步和复盘
- 保持 Railway 服务存活

但决策层默认不会在同一根 `4H` bar 上重复生成新 cycle。

## 本地启动

```bash
python3 backend/run_loop.py
```

## 单次主链验证

```bash
python3 backend/run_v2_pipeline.py
```
