import { t, type Locale } from "@/lib/i18n";
import { TM_CHART_CSS } from "@/components/charts";
import { TmRadarChart, type TmRadarDatum } from "@/components/charts/TmRadarChart";
import { TmCols2, TmPane } from "@/components/tm/TmPane";
import {
  TmTable, TmTableBody, TmTableCell, TmTableFrame, TmTableHead,
  TmTableHeaderCell, TmTableRow, TmTableRowHeader,
} from "@/components/tm/TmTable";

const RADAR_VALUES = [
  { zh: "动量", en: "Momentum", positive: 2.2, negative: 0, raw: 2.2 },
  { zh: "技术", en: "Technical", positive: 0.8, negative: 0, raw: 0.8 },
  { zh: "情绪", en: "Sentiment", positive: 0, negative: 1.1, raw: -1.1 },
  { zh: "催化", en: "Catalyst", positive: 1.7, negative: 0, raw: 1.7 },
  { zh: "内部", en: "Insider", positive: 0, negative: 0, raw: null },
  { zh: "资金流", en: "Flow", positive: 0, negative: 0.7, raw: -0.7 },
] as const;

type CoverageStatus = "live" | "registered" | "source-only";
type CoverageItem = Readonly<{
  zh: string;
  en: string;
  component: string;
  route: string;
  status: CoverageStatus;
}>;

const COVERAGE: readonly CoverageItem[] = [
  { zh: "归因雷达", en: "Attribution radar", component: "charts/TmRadarChart", route: "stock/[ticker], reference", status: "live" },
  { zh: "日线与成交量", en: "Daily price + volume", component: "stock/PriceChart", route: "stock/[ticker]", status: "registered" },
  { zh: "解释区间", en: "Explain range", component: "stock/ExplainRangePanel", route: "stock/[ticker]", status: "registered" },
  { zh: "日内钻取", en: "Intraday drill-down", component: "stock/IntradayDrawer", route: "stock/[ticker]", status: "registered" },
  { zh: "净值与回撤", en: "Equity + drawdown", component: "backtest/TmEquityDrawdownChart", route: "backtest", status: "registered" },
  { zh: "样本划分", en: "Train/test split", component: "backtest/TrainTestSplitPane", route: "backtest", status: "registered" },
  { zh: "换手分布", en: "Turnover distribution", component: "backtest/TurnoverProfilePane", route: "backtest", status: "registered" },
  { zh: "滚动验证", en: "Walk-forward IC", component: "backtest/WalkforwardPane", route: "backtest", status: "registered" },
  { zh: "盈亏分布", en: "Win/loss histogram", component: "backtest/WinLossDistributionPane", route: "backtest", status: "registered" },
  { zh: "水下回撤", en: "Underwater drawdown", component: "backtest/TmDrawdownChart", route: "report", status: "registered" },
  { zh: "月度热力图", en: "Monthly heatmap", component: "backtest/TmMonthlyReturnsHeatmap", route: "report", status: "registered" },
  { zh: "因子收益", en: "Factor PnL", component: "charts/FactorPnLChart", route: "report", status: "registered" },
  { zh: "净值对比", en: "Equity comparison", component: "charts/TmCompareEquityChart", route: "report", status: "registered" },
  { zh: "IC 时序", en: "IC timeseries", component: "signal/TmICTimeseriesChart", route: "report", status: "registered" },
  { zh: "暴露分解", en: "Exposure breakdown", component: "signal/TmExposureChart", route: "report", status: "registered" },
  { zh: "滚动相关性", en: "Rolling correlation", component: "app/report inline Recharts", route: "report", status: "registered" },
  { zh: "因子分布与活跃度", en: "Factor distribution + activity", component: "app/factors inline Recharts", route: "factors", status: "registered" },
  { zh: "校准曲线", en: "Calibration curve", component: "evolution/ReliabilityChart", route: "evolution", status: "registered" },
  { zh: "IC 趋势", en: "IC trend", component: "evolution/IcTrendChart", route: "evolution", status: "registered" },
  { zh: "演化健康轨迹", en: "Evolution health path", component: "evolution/EvolutionObservatory", route: "evolution", status: "registered" },
  { zh: "BRAIN 收益", en: "BRAIN PnL", component: "brain/BrainPnLChart", route: "brain", status: "registered" },
  { zh: "因子烟雾测试", en: "Alpha smoke equity", component: "alpha/SmokePane", route: "alpha", status: "registered" },
  { zh: "模拟仓净值", en: "Paper equity", component: "picks/paper/PaperCurvePane", route: "paper", status: "registered" },
  { zh: "旧版净值面板", en: "Legacy equity pane", component: "backtest/EquityCurvePane", route: "source-only", status: "source-only" },
  { zh: "旧版回撤面板", en: "Legacy drawdown pane", component: "backtest/DrawdownPane", route: "source-only", status: "source-only" },
  { zh: "旧版 IC 时序", en: "Legacy IC timeseries", component: "signal/ICTimeseriesChart", route: "source-only", status: "source-only" },
  { zh: "覆盖率刻度", en: "Coverage meters", component: "data/UniverseCard", route: "data", status: "registered" },
  { zh: "选股分布条", en: "Screener distribution bars", component: "app/screener graph primitives", route: "screener", status: "registered" },
  { zh: "评级聚合条", en: "Rating aggregation bar", component: "stock/RatingBadge", route: "stock/[ticker]", status: "registered" },
  { zh: "刷新进度条", en: "Refresh progress", component: "picks/RefreshButton", route: "picks", status: "registered" },
  { zh: "范围控件轨道", en: "Range-control track", component: "tm/TmField", route: "shared", status: "registered" },
] as const;

export function ReferenceVisualizations({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  const radarData: readonly TmRadarDatum[] = RADAR_VALUES.map((item) => ({
    label: zh ? item.zh : item.en,
    positive: item.positive,
    negative: item.negative,
    raw: item.raw,
  }));
  return (
    <div>
      <TmCols2>
        <TmPane
          title={t(locale, "reference.pane.visualRadar")}
          meta={zh ? "股票详情页使用的真实生产组件" : "the real production component used on stock detail"}
          bodyClassName="p-4"
        >
          <TmRadarChart
            data={radarData}
            positiveLabel={zh ? "偏多" : "Bullish"}
            negativeLabel={zh ? "偏空" : "Bearish"}
            unavailableLabel={zh ? "暂无可比数据" : "Not comparable"}
            ariaLabel={zh ? "六维股票信号归因示例" : "Six-axis stock signal attribution example"}
            summary={zh ? "示例：固定六维，内部维度缺测时保留轴，以虚线和缺测标签区分中性零值。" : "Example: six fixed axes. Missing Insider data keeps its axis and is distinguished from a neutral zero."}
          />
        </TmPane>

        <TmPane
          title={t(locale, "reference.pane.visualFamilies")}
          meta={zh ? "所有图表共享语义色和 12px 最小字号" : "all charts share semantic colors and a 12px minimum"}
          bodyClassName="grid gap-px bg-tm-rule p-px sm:grid-cols-2"
        >
          <ChartFamily kind="line" label={zh ? "趋势与净值" : "Trend and equity"} />
          <ChartFamily kind="bar" label={zh ? "分布与对比" : "Distribution and comparison"} />
          <ChartFamily kind="heat" label={zh ? "热力矩阵" : "Heatmap matrix"} />
          <ChartFamily kind="drawdown" label={zh ? "回撤与风险" : "Drawdown and risk"} />
        </TmPane>
      </TmCols2>

      <TmPane
        title={t(locale, "reference.pane.visualCoverage")}
        meta={zh ? "全量生产登记：实时样例、已登记与仅源码三种状态" : "complete production registry: live, registered, and source-only states"}
      >
        <TmTableFrame>
          <TmTable caption={zh ? "生产图表覆盖清单" : "Production visualization coverage registry"}>
            <TmTableHead><TmTableRow>
              <TmTableHeaderCell>{zh ? "图形类型" : "Chart family"}</TmTableHeaderCell>
              <TmTableHeaderCell>{zh ? "生产组件" : "Production component"}</TmTableHeaderCell>
              <TmTableHeaderCell>{zh ? "页面" : "Route"}</TmTableHeaderCell>
              <TmTableHeaderCell>{zh ? "覆盖状态" : "Coverage status"}</TmTableHeaderCell>
            </TmTableRow></TmTableHead>
            <TmTableBody>
              {COVERAGE.map((item) => (
                <TmTableRow key={item.component}>
                  <TmTableRowHeader className="font-normal">{zh ? item.zh : item.en}</TmTableRowHeader>
                  <TmTableCell><code className="font-tm-mono text-xs">{item.component}</code></TmTableCell>
                  <TmTableCell><code className="font-tm-mono text-xs text-tm-muted">{item.route}</code></TmTableCell>
                  <TmTableCell><CoverageLabel status={item.status} zh={zh} /></TmTableCell>
                </TmTableRow>
              ))}
            </TmTableBody>
          </TmTable>
        </TmTableFrame>
      </TmPane>
    </div>
  );
}

function CoverageLabel({ status, zh }: { readonly status: CoverageStatus; readonly zh: boolean }) {
  const copy = {
    live: zh ? "实时样例" : "Live specimen",
    registered: zh ? "已登记" : "Registered",
    "source-only": zh ? "仅源码" : "Source-only",
  }[status];
  const tone = status === "live" ? "text-tm-pos" : status === "source-only" ? "text-tm-warn" : "text-tm-info";
  return <span className={`font-tm-mono text-xs ${tone}`}>{copy}</span>;
}

function ChartFamily({ kind, label }: { readonly kind: "line" | "bar" | "heat" | "drawdown"; readonly label: string }) {
  return (
    <figure className="bg-tm-bg p-3">
      <svg viewBox="0 0 240 96" role="img" aria-label={label} className="h-24 w-full border border-tm-rule bg-tm-bg-2">
        {kind === "line" ? <polyline points="8,78 46,63 83,68 122,38 160,51 198,24 232,30" fill="none" stroke={TM_CHART_CSS.positive} strokeWidth="3" /> : null}
        {kind === "bar" ? [28, 54, 74, 42, 66].map((height, index) => <rect key={height} x={18 + index * 44} y={88 - height} width="24" height={height} fill={index < 2 ? TM_CHART_CSS.negative : TM_CHART_CSS.information} />) : null}
        {kind === "heat" ? Array.from({ length: 18 }, (_, index) => <rect key={index} x={8 + (index % 6) * 38} y={8 + Math.floor(index / 6) * 28} width="30" height="20" fill={index % 4 === 0 ? TM_CHART_CSS.negative : index % 3 === 0 ? TM_CHART_CSS.warning : TM_CHART_CSS.positive} opacity={0.35 + (index % 3) * 0.25} />) : null}
        {kind === "drawdown" ? <><path d="M8 18 L48 23 L88 38 L128 72 L168 49 L208 34 L232 29 L232 88 L8 88 Z" fill={TM_CHART_CSS.negative} opacity="0.22" /><polyline points="8,18 48,23 88,38 128,72 168,49 208,34 232,29" fill="none" stroke={TM_CHART_CSS.negative} strokeWidth="3" /></> : null}
      </svg>
      <figcaption className="mt-2 text-xs text-tm-muted">{label}</figcaption>
    </figure>
  );
}
