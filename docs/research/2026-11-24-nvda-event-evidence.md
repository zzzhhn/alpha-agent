# NVDA 管理层披露：事件时间不等于机器人看到的时间

| 事件 | 董事会行动日期（8-K） | IR 页公告日期 | EDGAR 接收（纽约 / UTC） |
| --- | --- | --- | --- |
| 黄仁勋辞任，Colette Kress 出任临时 CEO | 2026-11-11 | 2026-11-12 | 2026-11-12 08:52:41 EST / 13:52:41Z |
| 黄仁勋复任，Kress 继续任 CFO | 2026-11-22 | 2026-11-23 | 2026-11-23 08:57:54 EST / 13:57:54Z |

辞任：[SEC 8-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000082/nvda-20261111.htm)、[NVIDIA 公告](https://nvidianews.nvidia.com/news/nvidia-announces-ceo-transition)。复任：[SEC 8-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000090/nvda-20261122.htm)、[NVIDIA 公告](https://nvidianews.nvidia.com/news/nvidia-board-reinstates-jensen-huang-as-president-ceo-and-board-director)。接收时间来自 [EDGAR Submissions](https://data.sec.gov/submissions/CIK0001045810.json)，不是报道首发或系统首次发现的时间；IR 页面只证明日期。两者都是独立的 `management_change`，不是同一事件的更正或相互撤回，也不能只靠标题推出涨跌方向。

`tests/news/fixtures/nvda_ceo_sec_replay.json` 与 `nvda_ceo_ir_replay.xml` 是事后构造的回归样本，未称量历史系统实际收到新闻的时间，不写入生产数据库。SEC fixture 用实际 accession 和接收时间；IR fixture 只有可核实的公告日，不补分钟。即使现在才采到旧条目，`first_seen_at` 仍是首次观察入库时间；回放不能将它提前到公告日，更不能提前到董事会行动日。

## 独立前向行情观察

精确到时刻的官方管理层、财报、指引、并购、监管事件可单独留下行情证据，即使规则没有开仓。已在开盘前获知的隔夜事件，使用上一 XNYS 交易日最后一根常规分钟线收价与目标日首根常规分钟线开价；两条都是同一提供方的未复权参考价，不是保证可成交的竞价价格。同时报告个股、同步 SPY 及简单超额收益。盘中事件和开盘后才看到的旧事件不纳入开盘跳空。实际获知后，记录首根已收到且同步的合格常规分钟线收价，另取精确 30 分钟后的同步收价；过期不补，缺 bar、公司行动、缺失复权判定和窗口不足均有原因。跳空和后续变化是行情描述，不是事件因果、成交或策略收益。

观察每轮最多两事件，对事件标的和 SPY 共用当轮价格缓存；在短窗口内才读行情。初次记录归档原始 bar、抓取时间及来源，API 仅返回摘要。上面的 NVDA 历史样本未在当时跑过新观察任务，不会从今天的历史行情倒填开盘跳空或可交易收益。没有精确披露时刻的 IR 样本不会进入该观察账本。
