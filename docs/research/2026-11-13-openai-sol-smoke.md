# GPT-6.1 Sol 机器人接入验证（2026-11-13）

## 结论与边界

已修复 Sol 请求参数不兼容；完整模型决策仍被 API 组织额度阻塞，不能标为 smoke 通过。未修改生产 BYOK、机器人模型、提示词、策略参数、账户或订单。

本次只从已有模拟机器人运行读取上下文，再经 `_build_byok_client` → `LiteLLMClient.chat` 重放；不调用 worker、下单或持仓写入。私有上下文、密钥和原始响应不进入 Git。

## 直接观察

| 检查 | 结果 |
| --- | --- |
| 官方 `/v1/models/gpt-6.1-sol` | HTTP 200，模型 ID 一致 |
| 原请求 | 本地 `UnsupportedParamsError`：推理开启时不支持 `temperature=0.3`，0.14 秒返回 |
| 修复后的请求 | 上游 `RateLimitError`：`You have no credits remaining`，4.98 秒返回 |
| 完整 JSON、`parse_decision`、生成耗时和 token 用量 | 未验证；未收到 completion，不将失败请求时间当作模型延迟 |
| 生产切换 | 未执行；保留现有 Kimi 配置 |

重放使用 2026-11-12 20:31 UTC 的存量上下文和当前 `bot-system-v2-20261113-fact-discipline` 提示词。历史 Kimi 用量为 11,359 输入 / 3,242 输出 token，仅用于容量参考；不同 tokenizer 和推理用量不支持直接等量比较。单次重放也不能证明投资收益更高。

## 兼容修复

仅对 `openai/gpt-6.1-sol`：省略不支持的 temperature，把调用方 token 上限传为 `max_completion_tokens`。普通请求、流式请求和连接探测采用相同映射。保持服务商默认推理档位；机器人仍为 4096 的总 completion 预算，其中包含推理和可见回答。

其它模型保留原参数。没有打开全局 `drop_params`，没有增加模型重试，也没有因失败扩大输出预算。额度恢复后若 4096 导致截断，应另行评估预算与执行窗口，不能自动重试或绕过 `output_truncated` 门槛。

依据：[Sol 模型说明](https://developers.openai.com/api/docs/models/gpt-6.1-sol)、[GPT-6 参数兼容说明](https://developers.openai.com/api/docs/guides/latest-model)。

## 费用场景估算（不是实测账单）

官方标准短上下文费率：每百万输入 token $2、输出 token $10；缓存命中另按缓存费率。假设一次输入 12,000 token，消耗全部 4,096 completion token，则未缓存费用为 **$0.06496/次**。按 22 个交易日、每日两轮、每轮一次调用计算，约 **$2.86/月**。补充研究、手动运行、更长输入会增加费用；这不是月度支出硬上限。

订阅福利是否有效、组织实际余额和 token 账单必须分开核验。已关联订阅不等于额度已到账或尚未用完。[官方额度说明](https://developers.openai.com/api/docs/guides/chatgpt-api-credits)

## 验证与后续

- 相关 pytest：29 passed，1 skipped（需显式本地 `ALPHA_PAPER_BOT_TEST_DSN` 的 SQL 集成测试；本次不将生产库用于测试）。
- Ruff、设计系统审计、Next.js 构建及构建内类型检查通过。无页面或 API schema 变更。
- 额度可用后，用相同只读路径记录真实 `finish_reason`、输入/输出 token、耗时、完整 JSON 校验及费用；不触发下单。
- 成功后再由用户确认将密钥保存到生产 BYOK 和切换机器人模型。
