# 项目状态

最后核对：2026-09-30（UTC+8）。核对方式：对两个生产域名做只读 `curl -I`，用 `gh run list` / `gh run view` 查看 GitHub Actions 记录，并对照 `main` 上的代码。本文件是带日期的快照，引用前请重新核对。操作规则见 [`AGENTS.md`](../AGENTS.md)。

## 结论

生产环境自 2026-09-27 起被 Vercel 停用，前后端都返回 `HTTP 402`。代码自 2026-09-08（`3f09f0e`，PR #41）起没有变化。数据库在停用之后仍能连接，问题在 Vercel 一侧。恢复需要所有者先在 Vercel 查看用量与账单，代码改动无法解除停用。

## 线上状态

| 项 | 状态 | 依据 |
|---|---|---|
| 前端 `alpha.bobbyzhong.com` | `HTTP 402`，`x-vercel-error: DEPLOYMENT_DISABLED` | 2026-09-30 只读请求 |
| 后端 `alpha-api.bobbyzhong.com` | 同上，`/api/_health` 也返回 402 | 2026-09-30 只读请求 |
| 停用开始时间 | 2026-09-27 01:09Z 之后，最迟 07:55Z | 01:09Z `propose-job-runner` 成功；07:55Z `cron-shards` 运行 `36304615154` 的响应体为 `DEPLOYMENT_DISABLED` |
| Neon 数据库 | 2026-09-28 16:34Z 仍可连接 | 当时 `brain-mining-loop` 成功，该流程直连数据库并执行迁移 |
| 最近一次生产部署 | `main` 的 `3f09f0e`（2026-09-08） | PR #41 的发布记录，未在 Vercel 控制台复核 |
| 停用原因 | **待验证** | 假设是 Hobby 套餐的函数用量超限，需要在 Vercel 的 Usage 与 Billing 页面确认 |

两个域名的响应头都是 `server: Vercel`，没有 Cloudflare 的 `cf-ray`，说明请求不经过 Cloudflare 代理，`worker/` 里的 Worker 不在当前链路上。

## 定时任务

| 来源 | 名称 | 调度（UTC） | 链路 | 2026-09-30 状态 |
|---|---|---|---|---|
| GitHub Actions | `cron-shards` | 工作日多个时段 | 调用 Vercel 后端 | 2026-09-27 起全部失败（402） |
| GitHub Actions | `propose-job-runner` | 每小时 | 调用 Vercel 后端 | 2026-09-27 07:44Z 起失败 |
| GitHub Actions | `daily-factor-loop` | 每天 07:00 | 调用 Vercel 后端 | 2026-09-27 起失败 |
| GitHub Actions | `brain-mining-loop` | 每天 08:00 | 直连 Neon，先执行迁移 | 正常 |
| GitHub Actions | `brain-backfill-selfcorr` | 每天 09:00 | 直连 Neon，先执行迁移 | 正常 |
| GitHub Actions | `earnings-finnhub` | 工作日 11:30 | 直连 Neon | 正常 |
| GitHub Actions | `insider-form4` | 工作日 12:00 | 直连 Neon | 正常 |
| GitHub Actions | `test` | PR 与推送 `main` | CI，只跑后端 | 最近一次在 2026-09-08 推送 `main`（PR #41）时通过 |
| Vercel Cron | `/api/cron/slow_daily` | 每天 13:30（含周末） | 后端函数 | 随部署停用 |
| Vercel Cron | `/api/cron/paper_fill` | 每天 01:00 | 后端函数 | 随部署停用 |

另有 7 个只能手动触发的工作流：`apply-migrations`、`brain-catalog`、`brain-diag`、`brain-dump-alphas`、`brain-dump-fields`、`brain-show-errors`、`_seccomp_audit`。

数据保留清理（`minute_bars`、`news_items`、`daily_signals_fast`）挂在 `/api/cron/minute_bars` 的 `offset=0` 分片上，由 `cron-shards` 在工作日 18:15 调用，停用期间没有运行。这三张表都由后端任务写入，停用期间也没有新数据进来，所以积压有限；恢复后第一次 `minute_bars` 运行会补做清理。

## 已知问题

### P0

1. **生产停用。** 见上文。需要所有者操作。
2. **依赖后端的定时任务持续失败。** 根因是问题 1，恢复部署后应自愈。失败期间 CI 页面持续报红，容易掩盖真正的回归。

### P1

3. **`vercel.json` 里的 `slow_daily` Cron 不分片。** Vercel Cron 调用时不带 `limit` / `offset`，处理函数会对全部 558 只股票单次计算。按 `cron-shards.yml` 注释里的实测速度（80 只约 120 秒），全量约需 14 分钟，远超 300 秒上限；`api/cron/slow_daily.py` 的注释也写明全量只适用于 Pro 套餐的 800 秒上限。它和 GitHub Actions 的分片 `slow_daily` 在工作日同一时刻（13:30）重复运行，周末也照跑。这很可能每天产生一次跑满 300 秒的超时调用，**尚未用 Vercel 日志证实**。
4. **Cloudflare 缓存文件被提交。** `.wrangler/cache/wrangler-account.json`（2026-04-13 提交）包含 Cloudflare 账户 ID 与账户显示名，`.gitignore` 只覆盖了 `worker/.wrangler/`。从当前树移除后，历史里仍然存在。
5. **仓库根目录有与代码无关的文件。** 蓝图 docx/pdf（8 个，所有者决定暂时保留）、`_tmp_*` 解包目录（4 个）、`.skill` 包（2 个）、面向旧 AutoDL 服务器的一次性脚本 `patch_backend.py`、两个静态 HTML，以及 `frontend/.env.local.bak`。`frontend/.env.production` 只含公开的后端地址，`next build` 会读取它，应保留。
6. **没有 LICENSE 文件。** `README.md` 写的是 MIT，但仓库里没有许可证文件，GitHub 也识别不到许可证。

### P2

7. **双入口路由靠人工同步，另有两段死代码。** `create_app()` 与 `api/index.py` 当前加载的业务路由集合一致（`websocket` 只在本地入口加载，这是有意的），但没有测试保证两边同步。`factors_db` 路由（`/api/v1/factors` 的列表、详情、删除、衰减告警）只在 `create_app()` 里注册，而且在那里也加载失败：`alpha_agent/storage/factor_db.py` 依赖 `sqlalchemy`，依赖清单里没有这个包（2026-09-30 本地复现 `ModuleNotFoundError`），CI 也跳过了 `tests/test_factor_db_autoinit.py`。所以这组接口在哪个入口都不可用，`openapi.snapshot.json` 里也没有它们，前端目前没有调用。`alpha_agent/api/routes/dashboard.py` 两个入口都没有挂载，它引用的根目录 `qcore_dashboard.html` 因此也不会被访问到。
8. **文档过期。** `README.md` 和 `README_zh.md` 仍描述早期的 A 股因子研究代理；`docs/ROADMAP.md` 停在 2026-06-20，其中多项已完成但状态没有更新。
9. **陈旧分支与 PR。** 除 `main` 外有 28 个远端分支。其中 25 个的末端提交就是对应 PR 合并时的最终提交，合并后没有新工作，删除不会丢失内容；`codex/alpha-paper-recommendation-loop` 没有 PR，内容已全部在 `main`；`codex/alpha-desktop-redesign-proposal` 没有 PR，含 1 个未合并的提交（2026-08-03 的桌面工作台改版提案，文档加约 20 MB 截图）；`feat/brain-whitelist` 对应仍开着的草稿 PR #5，与 `main` 冲突。删除和关闭都需要所有者逐项同意。

## 恢复检查单

1. 所有者在 Vercel 查看两个项目的 Usage 与 Billing，确认停用原因，决定升级、等计费周期重置，还是先降负载（例如处理问题 3）。
2. 恢复后只读核验：后端 `/api/_health` 的 `db` 为 `ok`、`db_error` 为 `null`；`/api/_health/routers` 全部加载；前端首页和 `/api/auth/session` 正常。
3. 用 `docs/runbooks/2026-08-01-neon-quota-recovery.md` 第 2 步的查询看一次库大小，再让定时任务照常运行。
4. 观察下一轮调度的 `cron-shards`、`propose-job-runner`、`daily-factor-loop` 是否转绿。不为此手动触发生产任务，除非所有者同意。

## 待所有者决定

- Vercel 的恢复路径。
- 是否删掉 `vercel.json` 里未分片的 `slow_daily` Cron（问题 3）。这会改变生产调度，需要同意后才动。
- 是否改写 Git 历史来彻底清除 wrangler 缓存文件（需要强推 `main`）。
- 陈旧分支、未合并的改版提案分支与 PR #5 的处理。
- `.skill` 包、`engineering-blueprint-builder/` 目录和两个静态 HTML 的去留。
- `factors_db` 死代码：补上 `sqlalchemy` 依赖并接入生产入口，还是删除。

已决定：根目录的 8 个蓝图 docx/pdf 暂时保留（2026-09-30）；LICENSE 采用 MIT，版权人 `zzzhhn`。

## 本地验证基线（2026-09-30）

- 后端：`ruff check alpha_agent tests` 通过。`pytest`（CI 同款参数）在没有本机 Postgres 的环境下：883 通过、0 失败、251 个错误，错误全部是 `pytest-postgresql` 找不到 `pg_ctl`。本地使用 Python 3.13，CI 使用 3.12。
- 前端（Node 22，`npm ci` 按锁文件安装）：`npm run lint` 无告警；`npm test` 18 个文件、74 个用例全部通过；`npx tsc --noEmit` 通过；`npm run build` 的设计系统审计部分通过。`next build` 本身没有在本地跑通，原因是本地代理工具的文件系统层拦截了 `.next/` 下的 `mkdir`，不是代码问题，需要在 CI 或 Vercel 上确认。

## 更新方式

每次核对后更新顶部日期和对应条目，未核对的内容标注“待验证”。问题修复后移到下方“近期变更”，注明 PR 编号。

## 近期变更

- 2026-09-30：新增 `AGENTS.md` 与本文件。
