# 交易方法论 P0：冻结基线与实验协议

版本 **quant-p0-v1.0.0-20261111**，冻结日2026-11-11。
权威机器定义：`alpha_agent/research_eval/protocol.py:24` 的 frozen dataclass。
最终序列化协议SHA256：`b56a596ca324b9bced92100bb8b151c156125bb44ae9320d575d865d16a6057b`；CLI会输出同一fingerprint。任何字段变化均须新版本与新预注册，不能悄悄沿用本ID。
本文件定义离线比较；不授权交易、账户参数更新、任务调度或部署。现有L2/bot保持不变。
当前判定 **Evidence insufficient**；现状和待查SQL见[审计](2026-11-11-quant-p0-evidence-audit.md)。

## 冻结决策

1. 主问题：在可得信息、现金、持仓及成本约束下，原策略是否有**可复验的成本后增量**。不以命中率、订单数或模型自述决定是否赚钱。
2. 原策略观察臂：tactical v3 / strategic v2 / **一个固定配置版本与cohort的bot**。实际bot配置需SQL核验；未知前保持未激活，不能用默认配置冒充。基线臂仅EW与12–1动量，禁止继续筛选第三种直到出现赢家。
3. 主要比较：SPY与同eligible集合等权；RSP和零息现金为环境参照。全家族预留 **5臂×4持有期×2主要对照=40项**，自比较/不可计算项仍占预算，不能减少分母。
4. 1/3/5/20 XNYS sessions；auxiliary命中阈值 **0、50bps**，只作固定描述，不用于挑选交易或显著性宣传。方向多头 `r>threshold`、空头 `r<−threshold`；HOLD为 `abs(r)<=threshold`。阈值恰好相等不算方向命中；缺失为unknown。
5. 历史窗口都可能已被原项目看过；下列“historical test”只是**本次禁止调参的最终历史检查块**，不是新鲜OOS。唯一最终前瞻OOS固定 **2026-11-12→2027-11-12**，按本机XNYS日历预期252个自然交易日；不足或污染仍判insufficient，禁止滑动起点/追补决策/延长至显著。

## 实际可得数据与固定日期

本次直接读了全部5个bundle Parquet的schema/行数/date范围，而不是引用旧April runbook。
离线清单脚本 `scripts/research/inspect_bundled_data.py` 可复算；清单只在 `/tmp/alpha-quant-p0-bundled-inventory-20261111.json`，不提交数据副本。

| 文件（均在alpha_agent/data/） | 实读数据范围与规模 | 使用决定 |
| --- | --- | --- |
| factor_universe_sp500_v3.parquet | **2023-10-30→2026-10-30**，413,670行、570 symbols，含SPY/RSP；568股票 | 唯一主价格bundle；adjustment=all / Alpaca SIP（来源/调整属性由manifest声明，非本次向供应商核验）；不能将missing改成0 |
| factor_universe_sp100_v2.parquet | 2025-04-25→2026-04-24，24,849行、99 symbols，含SPY但无RSP | 仅旧数据完整性诊断，不替换主样本 |
| factor_universe_1y.parquet | 2025-04-21→2026-04-17，9,250行、37 symbols，含SPY但无RSP | 同上，禁止与v3拼成更好成绩 |
| fundamentals_pit_sp500_v3.parquet | filing_date 2022-02-16→2026-10-31，10,045行、565 symbols | 两个所选价格基线不依赖财报；如分析原因子则遵守publication≤决策与200日过期；10-31财报不能进入10-30决策 |
| fundamentals_pit.parquet | filing_date 2025-06-09→2026-05-15，444行、98 symbols | 旧版本，不向主样本广播旧快照 |

价格v3 SHA256：`7eb89dd7c33f54ccb515640b7465cd5f4d0c81ffba6a0bce1b0c135668b7bf4c`。
PIT v3 SHA256：`4beb26555e2b96551298719a58bfbe1757ab22a1f3e1cdbd21d81933ce9a96da`。
membership以决策日最近effective快照为准；manifest声明最新补充至2026-10-06、PSKY缺当前价，不替换成PARA。结果前须另保存所用CSV/manifest的hash；本批没有宣称成分/公司行动已完整。
`factor_backtest.py:361–417`为filing_date asof join；`evolution/research_panel.py:100–108`实际只取最近504sessions。本协议历史更长，**必须直接读取bundle**；不能误用现有504 loader再宣称覆盖本表训练起点。

| 用途 | 冻结起止（含首尾） | 日历长度 / 使用方式 |
| --- | --- | --- |
| 仅指标warmup | 2023-10-30→2024-10-30 | 253 sessions；不报策略业绩；为12–1提供回看 |
| train / fold1开发前缀 | 2024-10-31→2025-06-30 | 164 sessions；只检查实现/数据契约；基线无拟合参数 |
| validation fold1 | 2025-08-01→2025-10-31 | 65 sessions；中间至少21session purge/embargo |
| validation fold2 | 2025-12-02→2026-02-27 | 60 sessions；开发前缀扩展至2025-10-31；必须对扩展前缀重新做purge，不能把被跳过的日期拼成相邻收益 |
| 最终历史检查块 | 2026-04-01→2026-10-30 | 148 sessions；此前March间隔，仍不独立于历史研究；只能一次性诊断，无调参/Go权 |
| 最终forward OOS | 2026-11-12→2027-11-12 | 252预期sessions；数据尚不存在，不能声称已有；不得用于修改参数或选窗口 |

每块的h日结果需完整label结束于同块内。决策D收盘后可用，入场为D+1close，离场D+1+h close；因此块尾最后h+1个决策没有成熟标签，标记not_matured，**不借下一块价格凑足**。例如148个价格sessions最多有127个完整20日决策标签，再考虑缺价只会更少。
完整日历应本地用`exchange_calendars.get_calendar('XNYS', start='2023-10-30', end='2027-11-12')`显式范围生成；现有app helper的默认预生成范围会在2027-11-11结束，越界应报错，不能缩短或重新选择窗口。
rolling只允许 expanding train→下一个contiguous validation，不做随机CV或k-fold row stacking。训练样本的label_end必须早于评估首日；决策块之间至少留21整sessions（entry delay1+max horizon20）。helper `purged_training_dates`按调用方给的完整日历剔除，不能按非缺失价格行数代替session。
信号历史与snapshot若不存在，不可用今日模型/参数回算成“历史发布”；此时只评估规则基线/数据可用性，相应原策略比较项为unknown。

## 一致样本与成交成本

**先固定窗口，再检查覆盖**。每臂提交相同session向量和interval起止、版本、现金/持仓/NAV、价格basis与质量。
global intersection一次计算所有臂共同日期，报告每臂missing、common/expected比例；不是两两各选最有利窗口。残缺交集仅作端点诊断，不能删掉缺日后当连续一日NAV/vol/HAC。offline `matched_summary`在缺任意预期session时返回`incomplete_path, metrics=None`。
价格/身份缺失、correction晚发布、缺分红对账的区间不能成为skill样本；同时保留全部这些自然机会及失败原因。亏损样本没有额外排除条件。

| 比较层 | 统一约定 |
| --- | --- |
| 原L2两书 | 读真实冻结snapshot/订单/连续现金股数；不重写历史。d1_close、单边10bps综合成本，原Top50/2%目标上限/weekly；不额外重复扣同一成本 |
| bot原账本 | 当前cohort/config版本、实际受理时间、raw next-minute-bar、fee10+slip5仅为默认；实际值以SQL B/F为准。NAV已net不能再次扣费；模型美元成本未知则分列unknown |
| 同条件无LLM对照 | 若讨论“LLM增益”，必须相同bot候选、时钟、持仓数/单名/现金/成交分钟/费用/失败机会。当前无此真实ledger（`bot_analytics.py:230–231`）；只有日线bundle时结论为无法隔离LLM增益 |
| SPY / RSP | 只在共同起点买入、同入场延迟/成本，持有至固定终点并按共同持仓终态处理；含初始费用，不把first post-fee NAV重新归一为100来擦除费用；cash零息。RSP含ETF自身费用且成分池不同，不是完全相同eligible universe |
| eligible等权 | decision时所有eligible/in_universe、身份有效且当时可得必要字段的股票；权重min(1/N,2%)，不足50保留现金。不要只用未来有完整价格的幸存者重排N；已持有标的缺价须标缺失 |
| 同日线离线控制 | 所有基线用同一v3调整口径、同PIT池、整股、无空头/杠杆、先卖后买、现金非负、initial capital $1m。没有真实corporate-action/raw现金账时仅为adjusted单位的研究仿真，不能与raw bot称完全匹配 |
| 成本压力 | 事前全报单边总10/15/20/30bps四档；10为L2原综合假设、bot默认为fee10+slip5。stress为敏感性描述，不挑有利档、不自动改变线上参数 |

本次“连续NAV”计算器接受每区间gross return与buy/sell reference-notional / beginning NAV。
`r_net = r_gross − b*((1+s)*(1+f)−1) − sell*(1−(1−s)*(1−f))`，包含滑点后名义金额的费用交叉项。
买/卖都收费；初始买入和任何已发生卖出明确提供。**不虚构末日清仓**；主报告为共同mark-to-market终态，另有统一单边退出stress时全臂同报，不把只扣某一方退出费的结果并列。
share/cash/cap的实际执行须由离线重放器/已有账本证明；本次returns计算器**不验证可行交易、不生成订单**。nav输入负买卖/非有限数/资不抵债报错，-100%后不能继续虚构交易。

## 两个解释性基线：依据与固定构造

**B1 eligible EW monthly**：每月最后一个XNYS收盘后，以该时点冻结的eligible集合等权，D+1close执行；不估预期收益/协方差。未到月末继续持有；首个评估块起点首次建仓按同成本计入，不把首个自然月末前现金等待擦除。证券退出eligible并不意味着可伪造缺价卖出；缺执行价保持未成交及质量阻断。
[DeMiguel、Garlappi、Uppal 原论文（RFS 2009）](https://academic.oup.com/rfs/article-abstract/22/5/1915/1592901?login=false)把1/N作为估计型配置的样本外对照；本项目采用此控制思想，不移植论文结果为项目收益承诺。数据仅需历史成分/eligible、日线与公司行动；不需要财报、LLM或训练服务。

**B2 12–1 momentum long-only Top50 monthly**：每月末D，用截至D已知的adjusted close，`close[D−21]/close[D−252]−1`（session索引，252/21是本项目预注册的日线近似），降序，tie按ticker字典序，Top50、每名目标≤2%、不足留现金；D+1close执行。不做空、不调lookback、分位数、持仓数、止损或行业择时。
[Jegadeesh & Titman 原论文（1993）](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x)研究中期收益延续；[French官方Prior 2–12定义](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_10_port_form_pr_12_2.html)提供跳过最近月的参考。这里不是论文long-short因子、NYSE分组或日历月复刻，日线252/21近似、long-only和Top50均为项目控制设计。

两个控制组的**再平衡gross notional/NAV预算固定20%/次**，只对已建仓后的月度调仓生效；第一次从现金建仓预算100%，照付成本。先算目标与漂移权重，若完整调仓gross>20%，对所有差额同比例缩小，再向下取整股；先卖后买，现金不足按ticker顺序缩减买入，不递补后排名。残余留现金，不因未达目标追加下一天交易。预算不是paper bot现行参数，也不是建议改它；EW此处称“eligible_equal_weight”的控制版本，成分目标相同但实际权重可有漂移。

这样每年最多12次再平衡，已建仓年内调仓gross理论上≤240%（另加首次建仓/统一退出假设）；单边10bps时该调仓预算的线性费用上界约24bps/年，忽略漂移分母与滑点交叉项；**这是预算算术，不是已实现换手或收益**。
月度节流预期降低费用，但可能滞后排名/成分变化，动量会有反转和集中风险，EW会有小规模/再平衡暴露。sector snapshot不能做历史行业中性化证明。上界不是未来保本保证。

成本：复用当前约41万行bundle和同环境Parquet库，约数百万次标量/向量运算，一台本机可离线完成；实际耗时/峰值内存**未测**，不报虚构秒数。个人项目新增付费数据/模型调用/训练/DB均为0，月度研究不需要新服务；raw bot同条件历史分钟不存在则保持unknown，不采购补齐。本批只交构造与指标harness，未运行上述策略、未产出收益排名。

## 统计规则：先写下来，不能看结果挑窗口

- 主要经济量为每个固定比较的净收益差（百分点），以及relative wealth `(1+R_arm)/(1+R_bench)−1`。逐期超额 `r_arm−r_bench` 的均值用于统计；不能把差值序列复利当两条NAV的端点差。
- 日超额HAC使用Bartlett Newey–West，`L=max(h−1,floor(4*(n/100)^(2/9)))`；日超额用h=1，重叠h日标签用相应h。n不足L+2或零方差不生成t/显著性。方法依据：[Newey & West 原文](https://www.nber.org/papers/t0055)。HAC不能修复输入因果错误。
- 主检验使用从冻结窗口第一个完整执行interval锚定的**非重叠h日块，offset=0**；同时报告offset=0…h−1全部敏感性，不能选择最大值。缺日整个块None、不移动之后的锚；尾部不足h不算成熟样本。非重叠块仍可能序列相关，另给HAC。
- 推断单位是**组合日期/时间块**，不能把同日50只股票、两次唤起、20日重叠标签当独立样本。多个fold保持各自日历和持仓初始化，不拼接成假连续NAV。
- 40项家族控制FWER=.05；报告全部，Holm step-down，无法计算项p=1。可同时给Bonferroni .05/40界；不以单项p<.05宣称赢。没有充足渐近样本不出正式p值；h=20一年仅约12个非重叠块，保持探索性。
- DSR按[Bailey & López de Prado 2014 原文Eq.1/3](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)：使用同频**未年化**SR、完整试验集合SR的样本SD、Pearson kurtosis与skew、样本长度，N默认全部尝试数。独立N折减须事前证明，不能为通过而折减；历史尝试数未知则DSR标unverified。不是用赢家的Sharpe标准误伪装“全试验方差”。
- DSR仅用非重叠同频数据，未把序列相关修复等同于DSR；HAC单报。低样本/零variance/缺完整trial registry返回None，不返回100%胜率。代码输出的probability只是该方法的统计诊断，不是盈利概率。
- 0/50bps hit表和10/15/20/30成本stress均为预写描述敏感性，不另挑赢家/作显著性结论。若未来要检验其中最优项，必须把所有新尝试纳入扩大后的新family，旧40预算不可沿用。
- 禁止：看完结果改起止、用“最近最好5天”宣传、阈值/模型/池子筛选后只报最优、把已有historical holdout反复当新OOS、去掉亏损样本、缺失补零、逼bot交易充样本。

## 判定门与自然样本需求

**Go**只表示可以讨论下一阶段受控模拟，不代表赚钱承诺；按每个原策略臂分别判定，基线自己胜出不能让原策略Go。必须同时具备：无未解P0身份/PIT污染，固定forward窗口完整且≥252可比较sessions，费用/滑点/现金/版本一致，全部预注册结果和失败分母公开；该臂绝对net收益为正、对两个主要基准的增量均为正且40项家族校正后支持；DSR所需registry可靠且probability≥.95；DD/vol/暴露相对基线一起评审。原账户没有已批准的DD/行业预算，不能临时编一个通过线；若要风险预算门须另版本事前定，不在本协议悄悄改变运行风险。
**No-go**：已知证据污染却要晋升，或满足完整性/精度门后仍无成本后增量；可用“区间上界≤0”判断无正增量证据，不把不显著误说成等于0。
其余 **Evidence insufficient**。当前属于此项：tactical无估值、strategic有gap/stale、bot未知、raw/adjusted与公司行动未对齐。

自然样本的数字要给出假设：日均超额最小有用量预设 **5bps/日**仅作功效规划，假定日超额σ=100bps、独立近似、双侧α=.05、power=.8：

| 规划量 | 单一检验 | 40项Bonferroni保守规划 |
| --- | --- | --- |
| 95%均值CI半宽≤5bps | `ceil((1.960*100/5)^2)` = **1537独立日** | 临界z=3.227，**4166独立日** |
| 检出均值5bps/日，80% power | `ceil(((1.960+.842)*100/5)^2)` = **3140独立日** | **6623独立日** |
| 检出均值10bps/日，80% power | **785独立日** | **1656独立日** |

这是**假设情景**，不是根据当前收益反推的预测或样本承诺；σ减半需样本约1/4，序列正相关/非平稳会增加需求。252日独立近似下单项半宽约12.35bps，40项约20.33bps；因此一年通常只能完成观察完整性审查。实际HAC SE比IID大时按design effect放大需求，并保留固定截止、到期判insufficient；另开新协议才能继续验证，不能事后延长本试验直到显著。
当前tactical有效0，所以至少还需252个自然完整日作第一评审；有5/10bps小效应的盈利结论可能需数千个有效独立日。自然交易笔数没有最低强制值：保持现金/持仓也有每日NAV；缺价/坏身份不能通过多下单补齐。原strategic39估值不能当成39个干净独立日抵扣前瞻窗口，bot未知不得估算已完成比例。

## 可复算交付与验证

包`alpha_agent/research_eval/`仅Python标准库，无现有app模块导入、DB、网络或LLM。含global-date alignment、gross/net NAV双边cost、DD/vol/excess、turnover流量、cost drag、exposure/HHI、HAC、非重叠h块、DSR、Holm及冻结协议。
`scripts/research/evaluate.py`读取本地JSON：`sessions`为完整期望交易日列表；`net_returns`为臂名→日期→已含成本的interval return（坏质量用null），可选`trial_sharpes`为horizon→同频完整试验SR列表。没有registry就不出DSR；返回`complete`只是所给数值覆盖完整，不是PIT/经济价值验收。
脚本不自动导出私有账户、不交易、不重放策略；输入的session日历、价格basis、资金流、分红和成本须由调用方证明。这里只由returns能算路径指标，不能从net returns反推真实turnover/cost drag/暴露；这些须另给流量/权重调用相应primitive，不得用0占位。

```sh
# 在指定worktree执行，避免editable install落到main checkout。
PYTHONPATH=. /Users/bobby/Desktop/alpha-agent/.venv/bin/python -c \
  'import alpha_agent; print(alpha_agent.__file__)'
PYTHONPATH=. /Users/bobby/Desktop/alpha-agent/.venv/bin/python scripts/research/evaluate.py
# 已脱敏离线输入；输出放/tmp，禁止提交生产导出。
PYTHONPATH=. /Users/bobby/Desktop/alpha-agent/.venv/bin/python scripts/research/evaluate.py /tmp/eval-input.json \
  > /tmp/quant-p0-evaluation.json
PYTHONPATH=. /Users/bobby/Desktop/alpha-agent/.venv/bin/python scripts/research/inspect_bundled_data.py \
  > /tmp/quant-p0-bundled-inventory.json
PYTHONPATH=. /Users/bobby/Desktop/alpha-agent/.venv/bin/pytest tests/research_eval -q
/Users/bobby/Desktop/alpha-agent/.venv/bin/ruff check alpha_agent/research_eval tests/research_eval scripts/research
```

本批测试全部为明确synthetic fixture，覆盖缺日不压缩、亏损保留、买卖费用、初始费用/DD、现金暴露、短样本/零variance、HAC手算、DSR公式参照、Holm、21session purge与CLI缺失拒绝。指定pytest **23 passed**，指定ruff **All checks passed**。没有DB测试、模型调用或真实收益回测；单元通过不能证明赚钱。

## 版本 v1.1.0（2026-11-12）：线上因子恢复预设

**为什么改版本**：经用户批准，线上因子从自定义成交量表达式恢复为平台预设。v1.0.0 冻结时，线上因子是 `group_neutralize(zscore(ts_zscore(volume,20)),sector)`，在冻结研究面板（截至 2026-10-30）上计算。该表达式扣成本后 3 折验证均为负，换手约 200%/日。恢复后改为 `subtract(rank(ts_mean(returns, 12)), rank(ts_std(returns, 60)))`，读每日行情。tactical、strategic 和 bot 三臂的输入都受影响，按本协议“任何字段变化均须新版本”的规定，另立 v1.1.0。

| 字段 | v1.0.0（存档，不改） | v1.1.0 |
| --- | --- | --- |
| version | quant-p0-v1.0.0-20261111 | quant-p0-v1.1.0-20261112 |
| frozen_on | 2026-11-11 | 2026-11-12 |
| final_forward | 2026-11-12 → 2027-11-12 | **2026-11-13 → 2027-11-15**，按 XNYS 日历正好 252 个交易日 |
| factor_regime | 未记录（隐含：自定义成交量表达式，冻结面板） | 预设表达式，`live_daily_prices`，11-12 收盘后生效；前任表达式与面板一并记录 |
| 其余全部评估规则 | — | 与 v1.0.0 相同（臂、持有期、对照、40 项家族、成本、purge/embargo、基线构造） |
| fingerprint | `b56a596c…6057b` | 由 `alpha_agent/research_eval/protocol.py` 的 `FrozenProtocolV11` 计算，CLI 输出 |

规则：

1. **不拼接**（`splice_with_superseded=False`）：v1.0.0 窗口内的 11-12 交易日样本由自定义表达式产生，不并入 v1.1.0 的 252 日前瞻记录，只作为 v1.0.0 存档单独描述。
2. **生效点**：以第一份使用预设表达式的研究快照为准。若 11-12 收盘后的研究运行未完成（定时任务延迟、价格覆盖不足），第一个合格快照之前的交易日按“technical_failure”记入分母，不顺延窗口终点，也不回补决策。
3. **改动方式**：管理员接口 `POST /api/factor-lab/live-expression/restore-preset`，写入 `config_change_log`（source=manual，旧值→null）。如需改回，再手动设置旧表达式，并按本协议另立版本。
4. **不改变**：已发布快照、L2 两本账、bot 配置 v4、费用和调度均未改动。
