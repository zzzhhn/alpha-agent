# Alpha Agent desktop redesign image generation manifest

> Generated 2026-08-03 with native `image_gen`.  
> Native output: 1672×941 PNG.  
> Review copy: 3840×2160 PNG, resized for annotation and review.  
> The review copy is not described as native 4K.

## Factor Alpha

### References

- `current-picks-1920x1080.png`
- `current-paper-1920x1080.png`

### Native output

- `proposed-factors-native.png`
- Generated source: `exec-0074f07d-372f-4c9d-86b2-445b2d10ab8f.png`

### Final prompt

```text
Create a highest-fidelity, production-ready desktop web-app UI mockup for AlphaCore, a personal quantitative research workstation. Treat the two referenced screenshots as the exact visual baseline: near-black terminal workstation, restrained emerald green accent, fine 1px borders, compact data-dense typography, no gradients, no glassmorphism, no rounded consumer-fintech cards, no oversized hero copy, no decorative illustration, no emoji, no mobile layout. Canvas should target 16:9 and 4K-detail quality.

SCREEN: redesigned 因子 Alpha module, a "Factor Decision Workbench". It must feel like the same product generation as 今日推荐 and 模拟仓, but not copy their layouts mechanically.

Use the existing left sidebar and top workstation bar. Main desktop area:
1. A compact context header titled "因子 Alpha", subtitle "从假设到可检验表达式", with freshness and engine-health status on the right.
2. One dominant hypothesis composer across the top. Show a natural-language hypothesis such as "盈利质量改善且估值分位较低的股票，未来 20 日超额收益更高". Include universe and horizon controls. The only emerald primary button is "运行验证".
3. Directly below, a horizontal decision verdict strip answering whether the factor is worth keeping. Show honest metrics with thresholds: IC +0.034 通过, Sharpe 1.23 通过, MaxDD -12.4% 注意, 覆盖率 96%. Include a small "保存候选" secondary action, not accent-filled.
4. Below, a 3-column evidence workbench:
   left pane "表达式与数据血缘" showing rank(ts_mean(...)), operators, source fields, point-in-time and lag badges;
   center pane "样本内 / 样本外证据" with a restrained equity/IC chart and regime bands;
   right pane "反证与风险门槛" with look-ahead, turnover, crowding, stability checks, each with pass/caution states and plain-language next step.
5. Bottom compact "最近实验" table with 4 rows and compare/pin/reopen tertiary actions.

Interaction philosophy: decision-first, one primary action, visible status, progressive evidence, recoverable actions, honest unknown states, traceability. Use exact clean Chinese labels sparingly and keep all text readable. The screenshot should look ready for handoff to a frontend engineer, at 1920x1080 composition with extremely crisp 4K-style detail.
```

## Backtest

### References

- `current-picks-1920x1080.png`
- `current-paper-1920x1080.png`
- `current-backtest-1920x1080.png`

### Native output

- `proposed-backtest-native.png`
- Generated source: `exec-66236638-4f3b-4ecf-8895-98ff2b1a2f24.png`

### Final prompt

```text
Create a highest-fidelity, production-ready desktop web-app UI mockup for AlphaCore, a personal quantitative research workstation. Use the referenced screenshots as exact visual baseline: near-black terminal workstation, restrained emerald green accent, fine 1px rules, compact data-dense typography, square/very slightly rounded panes, no gradients, no glassmorphism, no consumer-fintech dashboard cards, no huge hero copy, no decorative art, no emoji, desktop only. Canvas target 16:9 with 4K-detail quality.

SCREEN: redesigned 回测 Backtest module as an "Experiment Validation Cockpit", matching the product generation and design philosophy of 今日推荐 and 模拟仓.

Keep the same top workstation bar and left sidebar. Main desktop area:
1. Compact title row "回测 Backtest", subtitle "反驳、比较并保留可信策略", with compute budget, data freshness, and queue status on the right.
2. A sticky experiment setup strip at top with factor expression, universe, long-short direction, holding period, transaction cost, and advanced parameters collapsed. Exactly one emerald primary button "运行回测". Include a small estimated cost/time hint.
3. Immediately below, a verdict strip that answers "是否值得继续". Show Sharpe 1.18 通过, MaxDD -14.7% 注意, IC +0.028 通过, turnover 42% 注意, annual return 16.2%. Show deltas versus pinned baseline and make "固定为基线" a secondary outline action.
4. The main workbench is split 2:1:
   left larger pane "收益路径与基准" with equity curve, benchmark, drawdown overlay, train/test boundary, and regime bands;
   right pane "验证门槛" with out-of-sample, walk-forward stability, transaction-cost sensitivity, concentration, and leakage checks. Each row has status plus a next-step link.
5. Under this, a compact comparison rail showing current run vs baseline and previous run. Then four collapsed analysis groups with concise summaries: 风险归因, 市场状态, 持仓, 执行成本. Only the group with a warning is expanded enough to show the issue.
6. Bottom "本次会话实验" table, 5 recent runs, with compare, refill, pin, and save tertiary actions.

Interaction philosophy: one primary action, visible progress and ETA, comparisons over isolated metrics, honest thresholds, partial results preserved after error, recoverable pin/save, resource-aware design for a small personal server. Use exact clean Chinese labels sparingly and keep text readable. It must look implementation-ready for a frontend engineer.
```

## Alerts

### References

- `current-picks-1920x1080.png`
- `current-paper-1920x1080.png`
- `current-alerts-1920x1080.png`

### Native output

- `proposed-alerts-native.png`
- Generated source: `exec-af7dcabe-b404-4f31-b45b-cbe8a85fd3f5.png`

### Final prompt

```text
Create a highest-fidelity, production-ready desktop web-app UI mockup for AlphaCore, a personal quantitative research workstation. Use the referenced screenshots as exact visual baseline: near-black terminal workstation, restrained emerald green accent, fine 1px borders, compact data-dense typography, square/very slightly rounded panes, no gradients, no glassmorphism, no consumer-fintech cards, no huge hero text, no decorative illustration, no emoji, desktop only. Canvas target 16:9 with 4K-detail quality.

SCREEN: a complete redesign of 警报 Alerts, the weakest current module. Transform it from a raw event table into a "Decision Triage Queue" matching 今日推荐 and 模拟仓.

Preserve the top bar and left sidebar. Main desktop layout:
1. Compact title "警报 Alerts", subtitle "只处理会改变决策的信息". On the right show feed freshness, ingestion health, and "3 条需处理".
2. Directly under title, a decision summary strip: "今天有 3 条关键变化，1 条影响当前持仓，2 条影响今日候选". Provide a small secondary "规则与阈值" button. Do not make refresh the primary action.
3. Three-column workbench:
   left narrow column is queue navigation and filters: "需处理 3", "关注列表 5", "仅记录 18", "已处理", plus severity, source, and relevance filters. Show compact saved views.
   center wide column is the alert decision queue. Each alert is a structured row/card, not a log line. Show severity, time, ticker, what changed, why it matters, confidence/source count, and linked object such as "当前持仓" or "今日候选". Example critical alert: SLB "分析师一致预期下修 + 新闻速度异常", likely impact on an open paper position. Example warning: URI "成交量异常且因子评分下滑". Example info: SPY "市场状态切换至高波动". Rows have clear selected state.
   right contextual inspector for selected SLB alert. Sections: "变化证据" with small timeline and source list; "组合影响" showing position weight and recommendation link; "建议动作" with exactly one emerald primary button "审查并处理", plus secondary "稍后提醒" and "标记已处理". Include a short caveat that evidence is correlated, not proven causal.
4. Bottom or center footer shows audit trail and keyboard hints, but stays compact.

Critical interaction philosophy: Alerts is an inbox for decisions, not a notification archive. Rank by decision relevance × severity × freshness × confidence. One primary action only. Preserve audit trail, allow undo after resolving, explicit stale/partial/error states, no fabricated causal claims, and do not imply the system can trade automatically. Use readable Chinese labels and crisp implementation-ready spacing.
```

## Evolution Monitor

### References

- `current-picks-1920x1080.png`
- `current-paper-1920x1080.png`
- `current-evolution-1920x1080.png`

### Native output

- `proposed-evolution-native.png`
- Generated source: `exec-d4ef6d40-f1ac-4d6b-83c3-9bbf30ae3ccd.png`

### Final prompt

```text
Create a highest-fidelity, production-ready desktop web-app UI mockup for AlphaCore, a personal quantitative research workstation. Use the referenced screenshots as exact visual baseline: near-black terminal workstation, restrained emerald green accent, fine 1px borders, compact data-dense typography, square/very slightly rounded panes, no gradients, no glassmorphism, no consumer-fintech cards, no huge hero copy, no decorative art, no emoji, desktop only. Canvas target 16:9 with 4K-detail quality.

SCREEN: redesigned 演化监控 Evolution Monitor as a "Model Change Observatory", matching 今日推荐 and 模拟仓 while preserving technical depth.

Keep the same top bar and left sidebar. Main desktop area:
1. Compact title "演化监控", subtitle "观察样本外变化，审查每一次模型调整". On the right show last update, evaluator health, small compute budget, and one pending review.
2. A top health and decision strip, not four equal KPI cards. Headline: "整体可用，校准过度自信，1 项权重变化需审查". Show compact sub-status for calibration, signal IC, adaptive weights, and proposals. Exactly one emerald primary action "审查变化".
3. Main layout is a 2:1 workbench:
   left large area "样本外表现时间线" with an uncluttered small-multiples or selectively highlighted chart. Focus on 3 meaningful signals, allow the other 10 signals to be muted and discoverable. Overlay vertical change markers such as guarded promotion, news guard, earnings guard, rollback. Show regime bands and confidence/coverage hints.
   right inspector "本次变化证据" for selected signal "分析师". Show before / shadow / guarded weights, IC trend, calibration, support window, and explicit "同期事件" links. Include a note: "事件与指标同期发生，仅作相关性线索，不推断因果".
4. Under the timeline, a compact promotion funnel with live → shadow → guarded → promoted/rolled back stages and counts. Highlight one candidate near promotion.
5. Bottom has two concise panes: "待审提议" with one proposal row and approve/reject secondary actions; "变更账本" table with time, signal, from/to weight, trigger, evidence window, reviewer, rollback availability. Changes must be traceable and reversible.
6. Avoid the current visual problem of plotting 13 equally prominent colored lines and stacking giant charts. Progressive disclosure: show only decision-relevant signals by default, with "查看全部 13 个信号" secondary affordance.

Interaction philosophy: monitor changes as reviewable decisions, not passive telemetry; show health and next action first; preserve auditability; no causal speculation; resource-aware polling and on-demand detail for a small server. Use clean readable Chinese labels and implementation-ready density.
```
