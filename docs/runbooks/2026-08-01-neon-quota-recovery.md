# Neon 配额恢复操作手册（2026-08-01）

## 背景

2026-07-25，Neon 免费层的**数据传输配额**耗尽（`usage 5,505,661,466 / limit 5,500,000,000`，仅超约 5.6 MB），
compute 被硬锁（`POST /endpoints/{id}/start` 返回 **HTTP 423**），所有碰 DB 的 workflow 连续失败约两天。

为止血，已停用 6 个定时 workflow。配额按自然月重置，即 **2026-08-01**。

## 顺序不可颠倒

恢复当天真正的风险**不是流量，是磁盘**：出事时存储已达 **460 / 500 MB（92%）**，
而 `daily_signals_fast` 与 `news_items` 在 2026-07-26 之前从未有过任何 retention。
若先恢复 cron 再清理，等于把一次流量故障原地换成 DiskFull 故障，几天内必定复发
（2026-06-26、2026-07-08 已各发生一次）。

## 步骤

### 1. 确认配额已重置

```bash
cd ~/Desktop/Side-projects/Artifacts/alpha-agent
.venv/bin/python -c "
import asyncio
from pathlib import Path
dsn=[l.split('=',1)[1].strip().strip('\"') for l in Path('.env').read_text().splitlines()
     if l.startswith('DATABASE_URL=')][0]
async def m():
    import asyncpg; c=await asyncpg.connect(dsn,timeout=30)
    print('库大小:', await c.fetchval('SELECT pg_size_pretty(pg_database_size(current_database()))'))
    await c.close()
asyncio.run(m())"
```

连得上即已重置。仍报 `exceeded the data transfer quota` 就继续等，**不要**在此时 enable 任何 workflow。

### 2. 先看清哪张表占地方

```sql
SELECT relname, pg_size_pretty(pg_total_relation_size(c.oid)) AS sz
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 10;
```

### 3. 确保一致性历史已物化（清理的前提）

`consistency_outcomes` 存的是**判定**而非信号，是允许清理 `daily_signals_*` 的唯一依据。
清理前必须先跑物化，否则会永久丢失一致性历史。

```bash
.venv/bin/python -c "
import asyncio
from pathlib import Path
from alpha_agent.backtest.consistency import materialize_outcomes
dsn=[l.split('=',1)[1].strip().strip('\"') for l in Path('.env').read_text().splitlines()
     if l.startswith('DATABASE_URL=')][0]
async def m():
    import asyncpg; p=await asyncpg.create_pool(dsn,min_size=1,max_size=2)
    print(await materialize_outcomes(p)); await p.close()
asyncio.run(m())"
```

代码里的 `prune_daily_signals` 有联锁：`consistency_outcomes` 为空时直接拒绝执行，
且永不删除超出物化进度的日期。**手工执行 SQL 时没有这层保护，务必先跑完这一步。**

### 4. 清理并回收空间

清理语句只标记死行、不缩文件；`VACUUM FULL` 才真正把空间还给文件系统，但需要约等于表大小的临时空间。
磁盘紧张时的顺序：先处理最大的表，边清边给后续操作腾出临时空间。

```sql
-- 按体积从大到小依次处理，每张表清完立刻 VACUUM FULL
DELETE FROM minute_bars WHERE ts < now() - interval '1 day';
VACUUM FULL minute_bars;

DELETE FROM news_items WHERE published_at < now() - interval '30 days';
VACUUM FULL news_items;

-- daily_signals_fast：手工版必须自己带上物化联锁
DELETE FROM daily_signals_fast
WHERE date < current_date - interval '30 days'
  AND date <= (SELECT max(date) FROM consistency_outcomes);
VACUUM FULL daily_signals_fast;
```

若 `VACUUM FULL` 因临时空间不足失败：先删掉该表最大的次级索引（立即释放物理空间且不需临时空间），
`VACUUM FULL` 之后再重建索引。2026-06-26 用此法把 490 MB 降到 213 MB。

### 5. 验证空间确实降下来了

重复步骤 2。**库大小明显下降**才算通过，不要只看命令没报错。

### 6. 最后才恢复定时任务

```bash
for wf in cron-shards propose-job-runner brain-mining-loop daily-factor-loop earnings-finnhub insider-form4; do
  gh workflow enable "$wf"
done
gh workflow list --all --json name,state --jq '.[] | "\(.state)\t\(.name)"'
```

### 7. 恢复后 24 小时复查

```bash
curl -s https://alpha.bobbyzhong.com/api/_health | python3 -m json.tool
```

`db` 应为 `ok`、`db_error` 应为 `null`。若 `db` 为 `down`，`db_error` 会直接写明原因
（这个字段是 2026-07-25 补的，此前该端点在 DB 挂掉时只会返回一句无信息量的 500）。

同时到 Neon 控制台确认 Network transfer 的日增速度。本次已把 cron 触发从 447 次/天砍到 96 次/天，
若用量仍逼近 5.5 GB/月，说明瓶颈在**单次查询的数据量**而非频率，需要去查具体是哪些查询在反复拉全量大表。

## 已上线的代码侧修复（2026-07-26）

| 改动 | 位置 |
|---|---|
| `minute_bars` 保留期 2 天 → 1 天 | `alpha_agent/data/minute_price.py` |
| 新增 `news_items` prune（30 天） | `alpha_agent/data/retention.py` |
| 新增 `daily_signals_fast` prune（30 天，带物化联锁） | `alpha_agent/data/retention.py` |
| 三个 prune 挂进 `minute_bars` cron 的 `offset==0` 分支 | `alpha_agent/api/routes/cron_routes.py` |
| `stock.py` 改为引用真实保留期常量，消除 30 天 vs 2 天的契约漂移 | `alpha_agent/api/routes/stock.py` |
| cron 触发 447/天 → 96/天 | `.github/workflows/cron-shards.yml`、`propose-job-runner.yml` |

即：**8-01 当天 cron 一恢复就会自动开始 prune**，手工步骤只是把历史积压一次性清掉并回收空间。
