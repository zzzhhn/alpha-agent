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
