export type Locale = "zh" | "en";

const translations = {
  zh: {
    /* Sidebar */
    "nav.inference": "模型推理",
    "nav.market": "市场数据",
    "nav.alpha": "Alpha 信号",
    "nav.portfolio": "投资组合",
    "nav.orders": "订单执行",
    "nav.gateway": "系统总线",
    "nav.audit": "审计跟踪",

    /* Sidebar groups */
    "group.analysis": "分析引擎",
    "group.execution": "执行层",
    "group.infra": "基础设施",

    /* Pipeline breadcrumb */
    "stage.data": "数据采集",
    "stage.feature": "特征提取",
    "stage.inference": "模型推理",
    "stage.strategy": "策略生成",
    "stage.risk": "风控网关",
    "stage.execution": "订单执行",
    "stage.audit": "审计跟踪",

    /* Common */
    "common.loading": "加载中...",
    "common.error": "加载失败",
    "common.retry": "重试",
    "common.noData": "暂无数据",
    "common.lastUpdate": "最后更新",
    "common.status": "状态",
    "common.healthy": "健康",
    "common.degraded": "降级",
    "common.down": "停机",

    /* KPI */
    "kpi.latency": "延迟",
    "kpi.uptime": "正常运行",
    "kpi.throughput": "吞吐量",
    "kpi.errors": "错误",

    /* Backtest */
    "nav.backtest": "回测引擎",
    "group.research": "研究工具",
    "backtest.title": "策略回测",
    "backtest.ticker": "股票代码",
    "backtest.startDate": "开始日期",
    "backtest.endDate": "结束日期",
    "backtest.rsiPeriod": "RSI 周期",
    "backtest.rsiOversold": "RSI 超卖线",
    "backtest.rsiOverbought": "RSI 超买线",
    "backtest.macdFast": "MACD 快线",
    "backtest.macdSlow": "MACD 慢线",
    "backtest.bollingerPeriod": "布林带周期",
    "backtest.bollingerStd": "布林带宽度 (σ)",
    "backtest.stopLoss": "止损 (%)",
    "backtest.takeProfit": "止盈 (%)",
    "backtest.positionSize": "仓位比例 (%)",
    "backtest.resetDefaults": "恢复默认",
    "backtest.paramGuide": "参数说明",
    "backtest.run": "运行回测",
    "backtest.running": "运行中...",
    "backtest.equityCurve": "权益曲线",
    "backtest.metrics": "绩效指标",
    "backtest.trades": "交易记录",
    "backtest.totalReturn": "总收益",
    "backtest.sharpe": "夏普比率",
    "backtest.sortino": "索提诺比率",
    "backtest.maxDrawdown": "最大回撤",
    "backtest.winRate": "胜率",
    "backtest.totalTrades": "总交易数",
    "backtest.finalValue": "最终价值",
    "backtest.params": "策略参数",
    "backtest.searchTicker": "搜索股票...",

    /* Phase 2: Factor Analytics + Gate Editor */
    "nav.factors": "因子分析",
    "nav.gates": "门控编辑",
    "factors.title": "因子分析面板",
    "factors.registry": "因子库",
    "factors.liveStats": "实时特征统计",
    "factors.correlation": "相关性矩阵",
    "factors.noFactors": "因子库为空，运行 Pipeline 后将自动填充",
    "gates.title": "多时间框架门控",
    "gates.threshold": "通过阈值",
    "gates.weights": "权重分配",
    "gates.trend": "4H 趋势",
    "gates.momentum": "1H 动量",
    "gates.entry": "15M 入场",
    "gates.composite": "综合评分",
    "gates.passed": "通过",
    "gates.failed": "未通过",
    "gates.simulate": "模拟评估",
    "gates.simulating": "评估中...",

    /* Phase 3: Stress Test */
    "nav.stress": "压力测试",
    "stress.title": "投资组合压力测试",
    "stress.scenario": "选择情景",
    "stress.positions": "持仓配置",
    "stress.addPosition": "添加持仓",
    "stress.run": "运行压力测试",
    "stress.running": "计算中...",
    "stress.portfolioImpact": "组合影响",
    "stress.positionBreakdown": "持仓分解",
    "stress.value": "市值",
    "stress.shock": "冲击",
    "stress.pnl": "盈亏",

    /* Theme */
    "theme.dark": "深色",
    "theme.light": "浅色",
    "theme.toggle": "切换主题",

    /* Brand */
    "brand.name": "AlphaCore",
    "brand.tag": "v2.0",
    "brand.systemOnline": "系统在线",
  },
  en: {
    "nav.inference": "Inference",
    "nav.market": "Market Data",
    "nav.alpha": "Alpha Signals",
    "nav.portfolio": "Portfolio",
    "nav.orders": "Orders",
    "nav.gateway": "System Bus",
    "nav.audit": "Audit Trail",

    "group.analysis": "Analysis Engine",
    "group.execution": "Execution",
    "group.infra": "Infrastructure",

    "stage.data": "Data Collection",
    "stage.feature": "Feature Extraction",
    "stage.inference": "Model Inference",
    "stage.strategy": "Strategy",
    "stage.risk": "Risk Gate",
    "stage.execution": "Execution",
    "stage.audit": "Audit",

    "common.loading": "Loading...",
    "common.error": "Failed to load",
    "common.retry": "Retry",
    "common.noData": "No data",
    "common.lastUpdate": "Last updated",
    "common.status": "Status",
    "common.healthy": "Healthy",
    "common.degraded": "Degraded",
    "common.down": "Down",

    "kpi.latency": "Latency",
    "kpi.uptime": "Uptime",
    "kpi.throughput": "Throughput",
    "kpi.errors": "Errors",

    "nav.backtest": "Backtest",
    "group.research": "Research Tools",
    "backtest.title": "Strategy Backtest",
    "backtest.ticker": "Ticker",
    "backtest.startDate": "Start Date",
    "backtest.endDate": "End Date",
    "backtest.rsiPeriod": "RSI Period",
    "backtest.rsiOversold": "RSI Oversold",
    "backtest.rsiOverbought": "RSI Overbought",
    "backtest.macdFast": "MACD Fast",
    "backtest.macdSlow": "MACD Slow",
    "backtest.bollingerPeriod": "Bollinger Period",
    "backtest.bollingerStd": "Bollinger Width (σ)",
    "backtest.stopLoss": "Stop Loss (%)",
    "backtest.takeProfit": "Take Profit (%)",
    "backtest.positionSize": "Position Size (%)",
    "backtest.resetDefaults": "Reset Defaults",
    "backtest.paramGuide": "Parameter Guide",
    "backtest.run": "Run Backtest",
    "backtest.running": "Running...",
    "backtest.equityCurve": "Equity Curve",
    "backtest.metrics": "Performance Metrics",
    "backtest.trades": "Trade History",
    "backtest.totalReturn": "Total Return",
    "backtest.sharpe": "Sharpe Ratio",
    "backtest.sortino": "Sortino Ratio",
    "backtest.maxDrawdown": "Max Drawdown",
    "backtest.winRate": "Win Rate",
    "backtest.totalTrades": "Total Trades",
    "backtest.finalValue": "Final Value",
    "backtest.params": "Strategy Parameters",
    "backtest.searchTicker": "Search ticker...",

    "nav.factors": "Factor Analytics",
    "nav.gates": "Gate Editor",
    "factors.title": "Factor Analytics Panel",
    "factors.registry": "Factor Registry",
    "factors.liveStats": "Live Feature Stats",
    "factors.correlation": "Correlation Matrix",
    "factors.noFactors": "Factor registry is empty. Run the pipeline to populate.",
    "gates.title": "Multi-Timeframe Gates",
    "gates.threshold": "Pass Threshold",
    "gates.weights": "Weight Allocation",
    "gates.trend": "4H Trend",
    "gates.momentum": "1H Momentum",
    "gates.entry": "15M Entry",
    "gates.composite": "Composite Score",
    "gates.passed": "PASS",
    "gates.failed": "FAIL",
    "gates.simulate": "Simulate Gates",
    "gates.simulating": "Simulating...",

    "nav.stress": "Stress Test",
    "stress.title": "Portfolio Stress Test",
    "stress.scenario": "Select Scenario",
    "stress.positions": "Portfolio Positions",
    "stress.addPosition": "Add Position",
    "stress.run": "Run Stress Test",
    "stress.running": "Computing...",
    "stress.portfolioImpact": "Portfolio Impact",
    "stress.positionBreakdown": "Position Breakdown",
    "stress.value": "Value",
    "stress.shock": "Shock",
    "stress.pnl": "P&L",

    "theme.dark": "Dark",
    "theme.light": "Light",
    "theme.toggle": "Toggle theme",

    "brand.name": "AlphaCore",
    "brand.tag": "v2.0",
    "brand.systemOnline": "System Online",
  },
} as const;

type TranslationKey = keyof (typeof translations)["zh"];

export function t(locale: Locale, key: TranslationKey): string {
  return translations[locale][key] ?? key;
}

export function getLocaleFromStorage(): Locale {
  if (typeof window === "undefined") return "zh";
  const stored = localStorage.getItem("alphacore-locale");
  return stored === "en" ? "en" : "zh";
}

export function setLocaleToStorage(locale: Locale): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("alphacore-locale", locale);
}
