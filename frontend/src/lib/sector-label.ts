import type { Locale } from "./i18n";

const ZH_SECTORS: Readonly<Record<string, string>> = {
  "Communication Services": "通信服务",
  "Consumer Cyclical": "可选消费", "Consumer Discretionary": "可选消费",
  "Consumer Defensive": "必选消费", "Consumer Staples": "必选消费",
  "Basic Materials": "基础材料", Materials: "材料", Energy: "能源",
  Financials: "金融", "Financial Services": "金融服务",
  Healthcare: "医疗保健", "Health Care": "医疗保健", Industrials: "工业",
  "Information Technology": "信息技术", "Real Estate": "房地产",
  Technology: "科技", Utilities: "公用事业", Unknown: "板块未分类",
};

export function sectorLabel(value: string, locale: Locale): string {
  return locale === "zh" ? ZH_SECTORS[value] ?? value : value === "Unknown" ? "Unclassified" : value;
}
