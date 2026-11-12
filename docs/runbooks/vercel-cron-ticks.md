# Vercel Cron 定时触发（2026-11-12 起）

## 为什么迁走 GitHub 定时

- **已确认**：GitHub `schedule:` 经常延迟数小时。11-11 的 23:00 UTC 任务实际 03:33 UTC 才启动，22:00 的价格拉取晚了约 4.5 小时。
- 研究链路要求在同一个 UTC 日内完成（见下文），延迟就意味着当天不发布推荐。11-12 侧栏因此显示“落后 2 日”。
- 现在所有定时都由 Vercel Cron 触发（生产部署、`GET`、`Authorization: Bearer $CRON_SECRET`）。GitHub workflows 只保留手动 `workflow_dispatch`，用于管理员刷新和故障恢复。
- `daily-factor-loop` 保持停用，不在本次迁移范围内。

## 时刻表（UTC）

| 入口 `/api/cron/…` | 时间 | 工作 |
| --- | --- | --- |
| `tick/daily_close` | 工作日 20:10–23:55，每 5 分钟 | 价格 → IC → 6 个 full shard → 发布尝试 → L2 |
| `tick/slow_daily` | 工作日 13:30–14:25，每 5 分钟 | offset 0–480，每片 80，然后 30 天 IC 标注 |
| `tick/fast_tech` | 工作日 15:30、19:30 | tech，limit 40 |
| `tick/news_per_ticker` | 工作日 15:00、19:00 | offset 0/75，limit 75 |
| `tick/news_macro` | 工作日 12/16/20:00，另每天 02:00 | 宏观新闻 |
| `tick/minute_bars` | 工作日 18:15 | limit 75 |
| `tick/ic_backtest_monthly` | 每月 1 日 04:00 | 月度 IC 回测 |
| `paper_bot/drive` | 工作日 14–15 时第 1–25 分、16/17/19/20 时第 31–55 分，每分钟 | 机器人一步（入队、带租约的 step；无事可做时结算订单） |
| `dispatch/brain-mining-loop` | 每天 08:00 | 派遣 GitHub 长任务 |
| `dispatch/brain-backfill-selfcorr` | 每天 09:00 | 同上，`limit=30` 与原定时一致 |
| `dispatch/earnings-finnhub` | 工作日 11:30 | 同上 |
| `dispatch/insider-form4` | 工作日 12:00 | 同上 |
| `run_propose_jobs` | 每小时整点 | 因子提案队列的兜底消费 |

原有的 `paper_bot/valuation`、`paper_bot/wake`、`paper_fill` 不变。

- `wake` 只入队。仅当 `PAPER_BOT_GH_FALLBACK=1` 时才额外派遣 GitHub runner；派遣失败不再返回 503。
- 用户手动唤起机器人仍走原来的 GitHub runner。
- 运行 30–150 分钟的 Python 脚本任务（BRAIN、Finnhub、Form 4）超出函数时长，仍在 GitHub 上运行，只是由 Vercel 准时派遣。`workflow_dispatch` 事件即时启动，不受 schedule 延迟影响。

## daily_close 的顺序与门槛

1. **等待收盘价稳定**：XNYS 当天官方收盘后 60 分钟才开始拉价格（与原 22:00 UTC 拉取的冬令时间隔一致）。夏令时 20:00 收盘对应 21:00 开始，冬令时 21:00 收盘对应 22:00 开始。
2. **价格**：第一轮总是完整拉取整个价格股票池（每片 75，period 5d），因为 IC、L2 和机器人估值用到的标的比研究集合多。之后如果 `research_price_readiness` 仍未就绪，再补拉，最多 3 轮，每轮间隔至少 20 分钟。
3. **IC 回测**，每个研究日一次。
4. **6 个 full shard**：offset 0/40/80/120/160/200，`run_key=tick-{research_day}-{offset}`，已成功的 offset 不重跑。
5. **发布尝试**：每次 tick 都重新检查真实覆盖率；缺任何一个成功 shard 都不发布。原有的健康门槛和 `no_op_same_market_date` 幂等规则不变。
6. **L2**：发布尝试之后运行一次（无论发布是否通过）。如果价格 3 轮后仍未就绪，或当日失败预算耗尽，跳过研究，但仍运行一次 L2 估值。L2 不会为已收盘的交易日补建目标。

**研究日仍按 UTC 日期计算。** 原因是：fast 信号行按 UTC 日期存储，优先股票池用 `before_date=UTC 日期` 排名。每个单元执行前都检查仍在同一 UTC 日、距午夜至少 300 秒，避免跨日股票池与信号混用。

- 第二天不补跑前一天的 fast 信号或发布。
- 价格覆盖门槛和 SPY 门槛不放宽。

## 进度、锁与失败预算

- **锁**：每个 job 在一条专用连接上持有事务级 advisory lock（`pg_try_advisory_xact_lock(hashtext('tick:<job>'))`）。重叠的调用返回 `skipped=overlap`。
  - Neon 连接池是事务模式的 pgbouncer，会话级锁可能残留在服务端连接上，所以不用会话锁。
  - 事务锁在提交、回滚或函数被终止时都会释放。
- **进度**：每个执行单元在 `cron_runs` 写一行 `tick_<job>`，字段包括 research_day、market_date、slot、unit、offset、price_pass、ok、error_type、handler_errors、tick_id、observed_at，以及可选的 run_id。
  - 单元开始前先写入 `UnitInterrupted`，完成后更新同一行。函数被杀掉的单元在下次 tick 计为失败，不会无限重试。
  - 不记录密钥或原始供应商响应。原有 handler 仍写各自的 cron_name，健康 DAG 照常可用。
- **单元判定**：与原 workflow 一致。只有异常、显式拒绝（`ok=false`）或重叠跳过才算失败；逐票的供应商错误只计数（`handler_errors`），覆盖率由就绪门槛和发布门槛判断。
- **时间预算**：只有在“已耗时 + 片间等待 + 单元估算 < 240 秒”时才启动下一个单元，给 300 秒的函数上限留出收尾时间。
- **失败预算**：tick 内不重试。同一 job、同一研究日累计 3 个失败单元后停止当天的工作。
  - 被健康门槛拒绝的发布不计入失败预算。
  - daily_close 预算耗尽时仍跑一次 L2。
  - 第二天重新计数。不要删除历史行来冒充成功。

## 手动触发与核对

下面的命令执行真实工作，沿用相同的锁、容量、时段、覆盖率和失败门槛：

```sh
curl --fail-with-body --max-time 290 \
  -H "Authorization: Bearer $CRON_SECRET" \
  https://alpha-api.bobbyzhong.com/api/cron/tick/daily_close
```

- 核对时，只读查看 `cron_runs` 中 `cron_name LIKE 'tick_%' OR cron_name LIKE 'dispatch_%'` 的行，再结合 `/api/_health/dag`。
- HTTP 200 不代表已发布，也不代表机器人已完成决策。
- 需要整条链路一次跑完时（例如补跑当天），仍可在 GitHub 手动运行 `cron-shards`，选择 `job=fast_intraday`。
