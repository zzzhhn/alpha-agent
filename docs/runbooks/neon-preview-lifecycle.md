# Neon 预览数据库回收

## 2026-11-03 事故与恢复

后端 Vercel 预览部署在构建前约一秒失败，顶层报错为 `BUILD_FAILED / Resource provisioning failed`，构建日志为空。生产部署正常。

读取失败部署 `dpl_DCx4zQezF5N3GWPZR269Hv7exGgL` 的 `/v1/deployments/{id}/integrations` 后，根因明确为 Neon 的 `Create database branch for deployment` 动作报错：`Branch limit reached. Upgrade your plan or delete unused branches.`

项目 `gentle-king-25994955` 有 10 个分支：生产 `main` 和 9 个已合并 PR 的 Vercel 预览副本。经用户明确同意后删除以下 9 个副本，未删除代码、修改套餐或写入生产数据。删除的旧预览测试数据不能恢复。

| 预览分支（均以 `preview/codex/` 开头） | 最后合并 PR |
| --- | --- |
| alpha-workbench-release | #65 |
| alpha-paper-bot-title | #64 |
| research-workspaces-refinement | #66 |
| alpha-paper-account-tabs | #63 |
| alpha-paper-bot-plan | #60 |
| alpha-paper-bot-release-fixes | #62 |
| alpha-bounded-recovery | #54 |
| brain-llm-screen-resilience | #25 |
| brain-options-diversity | #24 |

清理后分支为 1/10。对原失败部署原代码重新部署，Neon 资源创建动作转为 `succeeded`，新预览 `dpl_5unF9akYghLR3ft9v5P4EqXyFohW` 达到 `READY`。新建的隔离数据库为 `preview/codex/advanced-research-refinement`，因此验证后占用 2/10。生产 `/api/_health` 仍返回 `db: ok`。

## 长期规则

`neon-preview-cleanup` 在本仓库 PR **合并**后运行，不处理仅关闭未合并的 PR，不增加定时轮询。也可手动指定一个 PR，默认只预演。

只允许删除同时满足以下条件的一个数据库分支：

- PR 来自 `zzzhhn/alpha-agent` 自己的分支，已合并且已关闭。
- 精确匹配 `preview/<PR head ref>`，由 Vercel 创建。
- 固定项目 `gentle-king-25994955`，父分支为生产 `br-blue-salad-anselaqv`。
- 不是生产、默认、受保护或受删除限制的分支，且没有子分支。
- 同名 Git 分支没有开放 PR；若 Git 分支仍存在，它没有超过已合并 PR 的新提交。
- 实际删除前再次检查状态，删除后确认目标已消失。

不会使用 `preview/*` 通配删除，不会操作其他 Neon 项目。历史 Vercel 预览 URL 会因其数据库被删除而失去数据连接；代码和生产版本不受影响。如果还需要保留一个预览用于演示，请在合并前保护其 Neon 分支。

## 凭证与启用

需在 GitHub Actions Secret 中配置 `NEON_PREVIEW_CLEANUP_KEY`，且必须是仅限此 Neon 项目的 API key。不得复用覆盖其他项目的个人 key，不得写入代码、聊天或日志。项目级 key 仍具有该项目的管理权限，预览限定由清理代码和生产分支限制共同执行，不应声称 key 本身仅能删除预览。

工作流仅检出可信 `main` 上的清理脚本，GitHub token 只有仓库内容和 PR 读取权限。未配置 key 时只明确提示未启用，不制造持续失败邮件。

手动预演：在 GitHub Actions 的 `neon-preview-cleanup` 选择 Run workflow，填写已合并 PR 编号，保持 `apply=false`。检查回执中的分支名和 `would_delete` 后才改为 `apply=true`。

本次凭证启用状态与真实运行验收需以工作流记录为准；文件存在、测试通过或缺少 key 时的跳过，均不等于自动回收已启用。

## 诊断顺序

1. 构建日志为空时先查部署的 integrations 动作，区分分支上限、资源暂停和代码构建问题。
2. 列出 Neon 分支，核对对应 PR、生产分支、保护标记和当前 Git 分支状态。
3. 仅回收明确批准且符合规则的旧预览，不切换预览连接至生产来绕过故障。
4. 重跑一个预览，检查资源创建动作、构建状态和部署上的健康接口。

官方参考：[预览分支回收](https://neon.com/docs/guides/vercel-branch-cleanup)、[Vercel 原生集成](https://neon.com/docs/guides/vercel-managed-integration)。此集成随 Vercel 部署删除才回收数据库，PR 合并不是即时回收信号；单纯缩短保留时间也可能被最近部署等保留例外阻挡。
