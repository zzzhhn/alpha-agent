# AGENTS.md

本文件是在本仓库工作的 AI 代理与协作者的操作规则。项目当前状态见 [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md)。

## 事实来源的优先级

1. 仓库所有者在当前任务里的指令。
2. 仓库当前文件、Git 状态和线上实测结果。
3. `docs/PROJECT_STATE.md`（带核对日期的快照）。
4. 其他文档、交接笔记、历史记忆。它们只是线索，引用前必须重新核对。

`README.md` 和 `README_zh.md` 描述的是项目早期（A 股因子研究代理）的形态，与当前产品不一致，不要据此推断架构。

## 项目是什么

单用户、免费数据、仅供研究的美股评级引擎。每天对 S&P 500 股票池计算多信号综合评分并发布推荐快照（`/picks`），配套个股详情、模拟交易（`/paper`）、因子回测与演化监控、WorldQuant BRAIN 因子挖掘，以及用户指南（`/guide`）。LLM 调用使用用户自带的密钥（BYOK），服务端加密保存。

## 仓库地图

| 路径 | 内容 |
|---|---|
| `alpha_agent/` | 后端 Python 包：FastAPI 路由、信号、融合、存储、BRAIN、回测 |
| `alpha_agent/api/app.py` | 本地与测试入口 `create_app()` |
| `api/index.py` | Vercel 生产入口，独立装配路由，不经过 `create_app()` |
| `api/cron/` | 定时任务处理函数，经 `alpha_agent/api/routes/cron_routes.py` 暴露为 `/api/cron/*` |
| `alpha_agent/storage/migrations/` | `V0NN__name.sql` 版本化迁移及其 runner |
| `alpha_agent/signals/registry.py` | 信号清单的唯一事实源 |
| `alpha_agent/data/retention.py` | 大表的数据保留与清理 |
| `frontend/` | Next.js 15 前端（NextAuth v5、Tailwind 3） |
| `.github/workflows/` | CI 与全部定时任务 |
| `docs/` | 路线图、运维手册、设计系统、指南源文件 |
| `worker/` | 早期的 Cloudflare Worker 回退层，不在当前线上链路上 |
| `scripts/` | 运维与数据脚本 |

## 本地命令

后端（Python 3.12 及以上，CI 使用 3.12）：

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,storage,test]"
ruff check alpha_agent tests
pytest tests/ --ignore=tests/test_factor_db_autoinit.py --ignore=tests/test_report.py -m "not slow"
```

- 约 250 个用例通过 `pytest-postgresql` 在本机拉起临时 Postgres，需要 `pg_ctl`。本机没有 Postgres 时这些用例报 `ExecutableMissingException`，其余用例照常运行；CI 用 `postgres:16` 服务覆盖它们。
- `ruff` 固定在 `0.16.0`，并在 `pyproject.toml` 里显式列出规则集。升级要单独提交，并在同一提交里修完新告警。
- `Makefile` 里的 `*-acceptance` 目标除了本地检查，还会请求生产域名做冒烟，只在所有者要求时运行。

前端（在 `frontend/` 下执行）：

```bash
npm ci
npm run lint
npm test            # vitest
npx tsc --noEmit
npm run build       # 先跑三个设计系统审计脚本，再执行 next build
```

`tsc` 和 `next build` 抓不到“服务端组件引用 `"use client"` 模块里的值”这类运行期崩溃。改动页面后，用 `npm run start` 起服务，再用 `curl` 访问受影响的路由做冒烟。

## 改动规则

- **双入口**：新增或删除后端路由模块时，`alpha_agent/api/app.py` 和 `api/index.py` 两处都要改，否则生产环境会缺路由（2026-05-15 的 watchlist 路由就是这样在生产缺失的，见 `api/index.py` 注释）。目前两边只差有意为之的 `websocket` 和本身就加载失败的 `factors_db`，见 `docs/PROJECT_STATE.md`。部署后用 `/api/_health/routers` 确认实际加载的路由。
- **API 契约**：改了请求或响应结构，就运行 `make openapi-export`，重新生成 `openapi.snapshot.json` 和 `frontend/api-types.gen.ts`。`tests/api/test_openapi_export.py` 会拦截漂移。
- **信号**：信号的权重、周期、定时分组等只在 `alpha_agent/signals/registry.py` 里改，前端镜像由测试校验一致。
- **迁移**：只新增 `V0NN__name.sql`，不修改已经应用过的迁移。`brain-mining-loop`（每天 08:00 UTC）和 `brain-backfill-selfcorr`（每天 09:00 UTC）都会先对生产库执行 `scripts/apply_migrations.py`，所以迁移一旦合入 `main`，就会在下一次调度时进入生产库。含迁移的 PR 要写明回滚方式，按生产变更对待。
- **函数时长**：后端部署在 Vercel Hobby 套餐，单次函数上限 300 秒。定时任务端点要支持 `limit` / `offset` 分片，并在预算内完成；不要把批量计算放进用户请求路径。
- **数据保留**：Neon 免费档只有 0.5 GB 存储，历史上打满过三次。新增持续写入的表时，同时设计保留策略。
- **用户可见错误**：按状态码映射成可操作的本地化提示，不直接展示后端的原始报错。
- **UI 与视觉设计**：做较大的界面或视觉改动前，先和仓库所有者确认设计方法与验收方式。

## 交付流程

1. 非琐碎的改动先给方案，经所有者批准后再写代码。
2. 每个改动从最新的 `origin/main` 切出独立分支。
3. 本地自测，修掉常规问题。
4. 以 PR 交付，写清验证过什么、没验证什么、需要所有者做什么。
5. 不合并、不部署。合并与发布由所有者决定。

## 需要所有者逐项授权的动作

- 删除远端分支，关闭或重开 PR，强推，改写 Git 历史。
- 启用或停用工作流，修改调度。
- 新增、修改或删除 GitHub secrets，以及 Vercel、Neon 的环境变量。
- 修改 Vercel 或 Neon 的项目设置、套餐和额度。
- 手动触发生产定时任务，或调用任何生产环境的写接口。

不得为了绕过额度新开 Neon 或 Vercel 账号。可行的办法是降低负载、设置保留期、升级付费档，或合规地拆分工作负载。

对生产环境只做只读核验。常用端点：`https://alpha-api.bobbyzhong.com/api/_health`、`/api/_health/routers`、`/api/picks/lean?limit=5`、`/openapi.json`，以及前端的 `https://alpha.bobbyzhong.com/api/auth/session`。预览部署失败不等于生产失败。

## 公开仓库卫生

本仓库是公开的。不要写入：

- 密钥、令牌、连接串、密码，以及它们在日志或命令输出里的回显；
- 账户邮箱、账户显示名等个人身份信息；
- 任何公司内部资料或公司内部的模型调用接口；
- 个人投资、持仓与账户数据。

提交前检查 `git diff --cached`，提交身份使用 GitHub 的 noreply 地址。构建中间产物和一次性脚本不放进仓库；新增二进制文档前先问所有者。Cloudflare、Vercel 等工具生成的本地缓存目录要被 `.gitignore` 覆盖。

## 运维手册

- Neon 配额或磁盘事故：`docs/runbooks/2026-08-01-neon-quota-recovery.md`。顺序不可颠倒：先确认配额，再清理并回收空间，最后恢复定时任务。
- 后端资源约束：`docs/operations/backend-efficiency.md`。

## 沟通

面向所有者的说明和文档默认使用简体中文：先给结论，用连贯的段落，中文用全角标点，正文不用破折号当标点。代码、路径和命令保持原样。
