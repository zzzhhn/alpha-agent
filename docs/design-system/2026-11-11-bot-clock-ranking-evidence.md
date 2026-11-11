# GitHub 调度迟到与排名摘要污染修复

## 现场证据

- 工作流 active，默认分支 main 存在 schedule，未被禁用。纽约时区写法有效，不能误判为仅支持 UTC。
- 2026-11-09 美国交易日：Vercel 在 20:31、20:34 UTC 自然访问，两次 HTTP 200，只有一个 close_before 轮次。
- 当晚 GitHub 独立 schedule 直到 23:41:13 UTC 才创建 run，preflight 于 23:41:16 开始；不是在我方 worker 内等待几小时。最晚配置时点为 20:42 UTC，因此该事件至少晚于当日最后一个时点约 179 分钟，但旧日志没有保留 cron 表达式，不能指认它原本对应哪一个时点。
- [迟到的 GitHub run](https://github.com/zzzhhn/alpha-agent/actions/runs/42722452996) 成功退出但没有创建交易：`processed=false`、`active=false`、`enqueued=0`。此前的 `slots_checked` 表述不能清晰反映“已过窗口”。
- [GitHub 官方 schedule 说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) 明确允许负载下延迟或丢弃；[官方时区支持更新](https://github.blog/changelog/2026-03-19-github-actions-late-march-2026-updates/) 证实当前写法正确。不能将公共调度器的内部负载细节推断为已查明事实。
- 排名案例：当轮快照 78 的 COIN 为 6、FRT 为 10，持仓只覆盖前 8 中的 7 只；输入却包含旧轮次“与前 8 完全一致”的原文。模型输出复用了旧表述，又引用了新排名。输入混合了历史意见与当前事实，是本次修复的直接对象。
- 最新核验：2026-11-10 开盘轮次正常结束，实际订单表有 2 笔 filled；收盘轮次正常 no_trade。不能把这两次结果泛化成策略盈利能力证明。

## 变更与不变项

1. Vercel 保持主时钟、GitHub schedule 保持 best-effort 备用。没有增加频率、重试、窗口长度或新服务。
2. 记录到达来源、时间、GitHub run ID、允许的 cron 表达式；服务端返回是否在窗口、是否开市、新入队与复用数量。晚到返回 `outside_schedule_window`，不补过期决策。原始 intended timestamp 不可得时不编造延迟秒数。
3. 修正重复时钟复用旧 run 却计为新入队的统计。继续使用原账户锁与 slot_key，不改变成交幂等边界。
4. 模型上下文 schema 3：历史只保留结构化决策/结果和来源，不再反馈旧 summary；当前排名及持仓重合度由当前快照计算，缺失保留未知。原历史记录不改写。
5. 强化来源规则，明确 previous_rank、持仓笔记与历史结果不能覆盖当前排名；排名分差不等于预期收益，不能直接与成本 bps 比较。
6. 计算出的 ranking_context 保存到既有诊断 JSON，可在运行证据中检查；不新增数据库表或全市场抓取，不增加模型调用。保留 BYOK、账户配置和交易新鲜度门槛。

## 验证与边界

本地针对性检查覆盖真实排名矛盾回归、未知排名、历史摘要隔离、迟到不补跑、重复计数与日志脱敏；首次运行的测试 fixture 缺少必需时间字段，修正 fixture 后 35 项通过，所改 Python lint 通过。

上述验证证明上下文与调度契约变化，不声称任意未来模型文字绝无错误。新自然轮次的行为需以后续实际 run 为准，不额外调用模型来获取一份漂亮验收结果。合并部署状态见本批 PR。

侧栏与推荐 UI 尚未实施，已交接到 `docs/handoffs/2026-11-11-work-computer-roadmap.md`；不得在交付汇报中称作已经上线。
