# 模拟机器人的换仓归因

这份对照回答的是：在同一笔起点持仓和现金下，已记录的模拟成交改变了多少期末净值。它不检验择时策略是否能复现，也不能据此推断真实成交价格或者市场冲击。

## 口径

- 日期是美东日历日，起点是窗口第一场 XNYS 常规交易前一个交易日的收盘；账户晚于起点建立时，按该账本期初持仓和现金开始。终点是窗口最后一个 XNYS 常规交易日的收盘，含提前收市。当前账本周期以前的成交不混入起点。
- `actual` 重放窗口内已成交订单的股数、模拟成交价和实际记入账本的手续费。`hold` 不交易。`reduce_only` 不买入、不做空，只用历史卖出的时间和价格减期初原有持仓，股数不超过尚未卖出的原有持仓。若卖单需要裁切，只有在账本费率能反证原费用为比例费时才同步裁切手续费。这个对照减少长仓，不保证减少每一类风险。
- 三个组合用同一终点的可核验原始收盘价，不拿调整价、上次成交价或过时行情补空。已持仓的账本当日收盘净值可用于实际组，但不会被当作其他组合或个股的收盘价。缺资料返回 `null`，同时披露成交、费用、滑点和标价覆盖率。
- 逐笔净贡献计算为 `方向 × 股数 × (共同终点价 − 成交价) − 手续费`，买为正方向，卖为反方向。已证实的模拟滑点是 `方向 × 股数 × (成交价 − 原始参考价)`；若从原始参考价算毛贡献，扣滑点及手续费各一次后等于净贡献。从成交价算时，滑点已经包含在内。逐笔贡献是价格记账，不会假装跳过前一笔后仍能原样提交后一笔。
- 主结果遵循模拟账本，不记未入账股息。事后研究可另列现金分红敏感性，按除息日开始前各组的持股估算。涉及拆股等需重建股份单位的行动，不从股价直接推断。

## 复跑

账户归因接口为 `GET /api/paper/accounts/{account_id}/bot/turnover-attribution`，仅所有者可读，响应不缓存。`start_date`、`end_date` 可选，默认最近已收盘的 XNYS 交易日及之前共 14 个日历日。显式选择未收盘的交易日仍可核验已经成交的订单，但不会公布期末组合对照。

只读脚本可以读取本机私有行情回执。先把 `PAPER_ATTRIBUTION_OWNER_EMAIL` 设置为经授权审核的账户邮箱，并提供 `DATABASE_URL` 环境变量，或用 `--env-file` 指向含 `DATABASE_URL` 的文件。脚本默认仅将状态和覆盖率输出到终端。完整金额和逐笔表可以写入不在版本控制中的私有目录：

```sh
python -m scripts.research.paper_turnover_attribution \
  --start-date 2026-11-10 --end-date 2026-11-20 \
  --quote-receipt /path/to/private/alpaca-quote-receipt.json \
  --private-json /path/to/private/turnover.json \
  --private-markdown /path/to/private/turnover.md
```

回执包含 `retrieved_at`、`opening`、`terminal`、`calendar`、`actions`。两个行情字段是 Alpaca SIP 最后一根常规交易分钟的请求及响应；读取时核对每个标的、时间戳、OHLC 与成交量。日历和 XNYS 交叉核对。公司行动回执在处理日两侧留缓冲，再按除息或生效日期筛选；供应商不能保证行动数据立即完整。回执是事后取得的估值证据，不是模型决策时已知的行情。对接依据：[Alpaca 历史行情定义](https://docs.alpaca.markets/us/reference/stockbars)、[Alpaca 公司行动时间及数据限制](https://docs.alpaca.markets/us/reference/corporateactions-1)。
