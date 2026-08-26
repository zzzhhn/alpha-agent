import { t, type Locale } from "@/lib/i18n";
import { TmBadge, type TmBadgeTone } from "@/components/tm/TmBadge";
import { TmCols2, TmPane } from "@/components/tm/TmPane";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";

type BilingualCopy = Readonly<{ zh: string; en: string }>;
type MigrationStatus = "canonical" | "aliased" | "in-progress" | "exception" | "source-only";

type MigrationItem = Readonly<{
  id: string;
  category: BilingualCopy;
  legacy: string;
  canonical: string;
  consumers: BilingualCopy;
  owner: BilingualCopy;
  status: MigrationStatus;
  closure: BilingualCopy;
}>;

const STATUS_META: Readonly<Record<MigrationStatus, {
  label: BilingualCopy;
  meaning: BilingualCopy;
  tone: TmBadgeTone;
}>> = {
  canonical: {
    label: { zh: "已固化", en: "Canonical" },
    meaning: { zh: "生产采用、参考样例和自动证据一致。", en: "Production adoption, reference specimen, and automated evidence agree." },
    tone: "positive",
  },
  aliased: {
    label: { zh: "兼容别名", en: "Aliased" },
    meaning: { zh: "旧入口已映射到统一资产，待消费方归零后删除。", en: "The legacy entry maps to the canonical asset until its consumers reach zero." },
    tone: "info",
  },
  "in-progress": {
    label: { zh: "迁移中", en: "In progress" },
    meaning: { zh: "统一方向已确定，但仍缺消费方迁移或浏览器证据。", en: "The target is fixed, but consumer migration or browser evidence remains." },
    tone: "warning",
  },
  exception: {
    label: { zh: "受控例外", en: "Exception" },
    meaning: { zh: "因语义或基础设施需要保留，并由审计锁定范围。", en: "Retained for semantic or infrastructure reasons with an audited boundary." },
    tone: "neutral",
  },
  "source-only": {
    label: { zh: "仅源码", en: "Source only" },
    meaning: { zh: "不再由页面加载，等待删除或迁移结论。", en: "Not route-mounted; awaiting an explicit delete or migrate decision." },
    tone: "warning",
  },
};

const MIGRATIONS: readonly MigrationItem[] = [
  {
    id: "semantic-token-bridge",
    category: { zh: "基础 · 语义令牌", en: "Foundation · semantic tokens" },
    legacy: "--border / --muted / raw Tailwind colors",
    canonical: "--tm-* / chartTokens",
    consumers: { zh: "全站主题、Settings、RatingBadge、旧 IC 图", en: "Global themes, Settings, RatingBadge, legacy IC chart" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "in-progress",
    closure: { zh: "清除旧 IC 图的旧变量及剩余原始颜色工具类。", en: "Remove legacy variables from the old IC chart and remaining raw color utilities." },
  },
  {
    id: "typography-floor",
    category: { zh: "基础 · 字体层级", en: "Foundation · typography" },
    legacy: "route-local font sizes below 12px",
    canonical: "TM type roles / 12px visible floor",
    consumers: { zh: "全部生产页面与图表", en: "All production routes and charts" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "canonical",
    closure: { zh: "自动审计持续阻止小于 12px 的可见文字。", en: "The audit continues to reject visible type below 12px." },
  },
  {
    id: "pane-title-localization",
    category: { zh: "基础 · 区块标题", en: "Foundation · pane titles" },
    legacy: "HYPOTHESIS.INPUT / RISK.METRICS / …",
    canonical: "typed zh/en keys + localized TmPane title",
    consumers: { zh: "报告、回测、因子库、设置及共享面板", en: "Report, Backtest, Zoo, Settings, and shared panes" },
    owner: { zh: "设计系统 + 功能页", en: "Design system + feature routes" },
    status: "aliased",
    closure: { zh: "逐页把兼容映射调用替换为直接的本地化 key。", en: "Replace compatibility-map callers with direct localized keys route by route." },
  },
  {
    id: "button-family",
    category: { zh: "控件 · 按钮", en: "Control · buttons" },
    legacy: "ui/Button + page-local actions",
    canonical: "TmButton family",
    consumers: { zh: "认证、BRAIN、回测、警报、设置及全部工作台", en: "Auth, BRAIN, Backtest, Alerts, Settings, and all workbenches" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "aliased",
    closure: { zh: "旧 Button 已代理 TmButton；消费方归零后删除别名。", en: "Legacy Button proxies TmButton; remove the alias when consumers reach zero." },
  },
  {
    id: "field-family",
    category: { zh: "控件 · 字段", en: "Control · fields" },
    legacy: "raw input / select / textarea / range",
    canonical: "TmField family + TmSelectMenu",
    consumers: { zh: "认证、回测、设置、警报、选股、推荐与 BRAIN", en: "Auth, Backtest, Settings, Alerts, Screener, Picks, and BRAIN" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "canonical",
    closure: { zh: "审计为 0 个未解释原生字段；持续执行无增长门禁。", en: "Audit reports zero unexplained native fields; retain the no-growth gate." },
  },
  {
    id: "exclusive-toggle",
    category: { zh: "控件 · 互斥切换", en: "Control · exclusive toggle" },
    legacy: "local segmented selectors",
    canonical: "TmToggleGroup",
    consumers: { zh: "顶栏、BRAIN 审计筛选、警报筛选", en: "Topbar, BRAIN audit filters, and Alerts filters" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "canonical",
    closure: { zh: "新增互斥选择器必须先进入统一组件。", en: "Any new exclusive selector must enter the canonical component first." },
  },
  {
    id: "pagination-family",
    category: { zh: "控件 · 分页", en: "Control · pagination" },
    legacy: "page-local pagination",
    canonical: "TmPagination",
    consumers: { zh: "选股、演化、BRAIN、设计系统", en: "Screener, Evolution, BRAIN, and Design System" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "canonical",
    closure: { zh: "仓库扫描未发现第二套本地分页实现。", en: "Repository scan finds no second local pagination implementation." },
  },
  {
    id: "table-family",
    category: { zh: "数据显示 · 表格", en: "Data display · tables" },
    legacy: "page-local standard tables",
    canonical: "TmTable family",
    consumers: { zh: "推荐、模拟仓、BRAIN、回测、警报、选股、演化与股票详情", en: "Picks, Paper, BRAIN, Backtest, Alerts, Screener, Evolution, and Stock" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "exception",
    closure: { zh: "标准表格已统一；月度收益热力矩阵保留原生 table 语义。", en: "Standard tables are canonical; the monthly heatmap retains native table semantics." },
  },
  {
    id: "state-feedback",
    category: { zh: "反馈 · 生命周期", en: "Feedback · lifecycle" },
    legacy: "local loading / empty / error blocks",
    canonical: "TmStatePane + shared recovery grammar",
    consumers: { zh: "警报、回测、数据、方法论、模拟仓、今日推荐与信号页", en: "Alerts, Backtest, Data, Methodology, Paper, Picks, and Signal" },
    owner: { zh: "设计系统 + 功能页", en: "Design system + feature routes" },
    status: "canonical",
    closure: { zh: "新增异步面板必须提供阶段、缺失范围和局部恢复动作。", en: "New async surfaces must expose stage, missing scope, and local recovery." },
  },
  {
    id: "tooltip-family",
    category: { zh: "浮层 · 提示", en: "Surface · tooltip" },
    legacy: "HoverTip + InfoTooltip",
    canonical: "TmTooltip",
    consumers: { zh: "今日推荐、数据、股票详情、回测与因子库", en: "Picks, Data, Stock, Backtest, and Zoo" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "aliased",
    closure: { zh: "两个兼容包装已代理 TmTooltip；新代码禁止继续扩散。", en: "Both wrappers proxy TmTooltip; new code must not expand their use." },
  },
  {
    id: "icon-registry",
    category: { zh: "图标 · 生产登记", en: "Icon · production registry" },
    legacy: "route-local glyph choices",
    canonical: "Lucide registry + text-glyph boundary",
    consumers: { zh: "49 个生产图标与 12 个文字字形例外", en: "49 production icons and 12 text-glyph exceptions" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "exception",
    closure: { zh: "审计阻止未登记图标；语义符号例外维持显式清单。", en: "Audit rejects unregistered icons; semantic glyph exceptions stay explicit." },
  },
  {
    id: "visualization-registry",
    category: { zh: "图表 · 生产覆盖", en: "Chart · production coverage" },
    legacy: "route-local Recharts / SVG / metric graphics",
    canonical: "chartTokens + registered chart families",
    consumers: { zh: "25 个检测图表资产与各页面微型图形", en: "25 detected chart assets and route-level micro-graphics" },
    owner: { zh: "数据可视化", en: "Data visualization" },
    status: "in-progress",
    closure: { zh: "已全量登记，但目前只有雷达图为真实共享样例；继续补齐真实组件样例和稳定状态。", en: "Fully registered, but only the radar is a live shared specimen; add real specimens and stable states." },
  },
  {
    id: "source-only-visualizations",
    category: { zh: "图表 · 旧源码", en: "Chart · legacy source" },
    legacy: "EquityCurvePane / DrawdownPane / ICTimeseriesChart",
    canonical: "current Backtest + Signal chart family",
    consumers: { zh: "无页面消费，仅保留 3 个源码文件", en: "No route consumers; three source files remain" },
    owner: { zh: "回测 + 信号", en: "Backtest + Signal" },
    status: "source-only",
    closure: { zh: "确认无历史入口依赖后删除，或迁移仍有价值的逻辑。", en: "Delete after confirming no historical entry depends on them, or migrate valuable logic." },
  },
  {
    id: "overlay-family",
    category: { zh: "浮层 · 对话框与抽屉", en: "Surface · dialog and drawer" },
    legacy: "page-local modal / drawer focus logic",
    canonical: "TmDialog + TmDrawer + useTmModalFocus",
    consumers: { zh: "因子示例库、模拟下单、设计系统", en: "Alpha example library, simulated orders, and Design System" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "in-progress",
    closure: { zh: "焦点与关闭契约已统一；仍需把 toast、tour 等瞬态层纳入同一登记。", en: "Focus and close contracts are canonical; register toast, tour, and other transient layers." },
  },
  {
    id: "pane-card-family",
    category: { zh: "布局 · 区块容器", en: "Layout · pane container" },
    legacy: "ui/Card / glass-card",
    canonical: "TmPane + TmScreen",
    consumers: { zh: "大部分工作台已迁移；旧 IC 图与 AST 抽屉仍引用 Card", en: "Most workbenches migrated; legacy IC chart and AST drawer still import Card" },
    owner: { zh: "设计系统 + 功能页", en: "Design system + feature routes" },
    status: "in-progress",
    closure: { zh: "迁移仍在挂载的 Card 消费方，再移除 glass-card 命名空间。", en: "Migrate mounted Card consumers, then remove the glass-card namespace." },
  },
  {
    id: "workbench-composition",
    category: { zh: "布局 · 工作台骨架", en: "Layout · workbench composition" },
    legacy: "route-local page shells",
    canonical: "TmScreen + WorkbenchHeader + TmSubbar + TmPane",
    consumers: { zh: "桌面端仪表盘页面", en: "Desktop dashboard routes" },
    owner: { zh: "设计系统 + 功能页", en: "Design system + feature routes" },
    status: "in-progress",
    closure: { zh: "补充骨架、双栏、吸顶和窄屏退化的可视化样例与路由清单。", en: "Add specimens and route inventory for shell, columns, sticky regions, and narrow fallback." },
  },
  {
    id: "native-title-budget",
    category: { zh: "可访问性 · 原生提示", en: "Accessibility · native titles" },
    legacy: "native title attributes",
    canonical: "TmTooltip or truncation-only title",
    consumers: { zh: "36 个截断或兼容提示", en: "36 truncation or compatibility hints" },
    owner: { zh: "设计系统 + 功能页", en: "Design system + feature routes" },
    status: "exception",
    closure: { zh: "保留 36 项无增长预算；承载解释内容时迁移到 TmTooltip。", en: "Hold the 36-item no-growth budget; migrate explanatory content to TmTooltip." },
  },
  {
    id: "native-control-internals",
    category: { zh: "控件 · 原生内部件", en: "Control · native internals" },
    legacy: "SegmentedTabs + toast infrastructure controls",
    canonical: "ARIA-native internals behind canonical APIs",
    consumers: { zh: "设计系统 tabs 与 toast 基础设施", en: "Design-system tabs and toast infrastructure" },
    owner: { zh: "设计系统", en: "Design system" },
    status: "exception",
    closure: { zh: "仅允许审计清单内的 3 个原生控件，不得扩张。", en: "Only the three audited native controls are allowed; the boundary must not grow." },
  },
];

export function ReferencePatterns({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  const copy = (value: BilingualCopy) => zh ? value.zh : value.en;
  const counts = MIGRATIONS.reduce<Record<MigrationStatus, number>>(
    (result, item) => ({ ...result, [item.status]: result[item.status] + 1 }),
    { canonical: 0, aliased: 0, "in-progress": 0, exception: 0, "source-only": 0 },
  );

  return (
    <div>
      <TmCols2>
        <TmPane title={t(locale, "reference.pane.patternAsync")} bodyClassName="divide-y divide-tm-rule">
          <PatternRow label="LOADING" text={zh ? "保留几何，说明阶段；不使用无文案的无限 spinner。" : "Preserve geometry and narrate the stage; never use an unexplained infinite spinner."} />
          <PatternRow label="EMPTY" text={zh ? "说明缺少什么、为何重要，以及唯一下一步。" : "Name what is absent, why it matters, and the one next step."} />
          <PatternRow label="ERROR" text={zh ? "错误留在受影响面板，重试不清空其他上下文。" : "Keep the error local; retry without erasing unrelated context."} />
          <PatternRow label="STALE / PARTIAL" text={zh ? "显示时间与缺失范围，只刷新受影响证据。" : "Show timestamp and missing scope; refresh only affected evidence."} />
        </TmPane>

        <TmPane title={t(locale, "reference.pane.patternList")} bodyClassName="divide-y divide-tm-rule">
          <PatternRow label="ROW" text={zh ? "整行安全时可选择；行内操作阻止冒泡并有独立名称。" : "Select the whole row when safe; inline actions stop propagation and have distinct names."} />
          <PatternRow label="PAGING" text={zh ? "分页保留筛选；切换每页数量回到第一页。" : "Pagination preserves filters; changing page size returns to page one."} />
          <PatternRow label="MUTATION" text={zh ? "可逆操作优先撤销；不可逆操作才增加确认摩擦。" : "Prefer undo for reversible actions; add confirmation friction only when necessary."} />
          <PatternRow label="PRIMARY" text={zh ? "每个屏幕上下文只有一个实心绿色主操作。" : "Each screen context has one filled green primary action."} />
        </TmPane>
      </TmCols2>

      <TmPane
        title={t(locale, "reference.pane.migration")}
        meta={zh ? `${MIGRATIONS.length} 项资产 · 状态、负责人和收尾证据可追踪` : `${MIGRATIONS.length} assets · status, owner, and closure evidence are traceable`}
      >
        <div className="grid border-b border-tm-rule bg-tm-bg-2 sm:grid-cols-2 xl:grid-cols-5">
          {(Object.keys(STATUS_META) as MigrationStatus[]).map((status) => (
            <div key={status} className="min-w-0 border-b border-tm-rule px-3 py-3 last:border-b-0 sm:border-r sm:last:border-r-0 xl:border-b-0">
              <div className="flex items-center justify-between gap-3">
                <MigrationBadge status={status} zh={zh} />
                <strong className="font-tm-mono text-lg tabular-nums text-tm-fg">{counts[status]}</strong>
              </div>
              <p className="mt-2 text-xs leading-5 text-tm-muted">{copy(STATUS_META[status].meaning)}</p>
            </div>
          ))}
        </div>

        <TmTableFrame>
          <TmTable density="standard" className="min-w-[1560px]" caption={zh ? "完整设计资产迁移状态" : "Complete design asset migration status"}>
            <TmTableHead>
              <TmTableRow>
                <TmTableHeaderCell className="w-[190px]">{zh ? "资产分类" : "Asset category"}</TmTableHeaderCell>
                <TmTableHeaderCell className="w-[230px]">{zh ? "旧资产" : "Legacy asset"}</TmTableHeaderCell>
                <TmTableHeaderCell className="w-[230px]">{zh ? "统一资产" : "Canonical asset"}</TmTableHeaderCell>
                <TmTableHeaderCell className="w-[280px]">{zh ? "消费页面 / 范围" : "Consumers / scope"}</TmTableHeaderCell>
                <TmTableHeaderCell className="w-[160px]">{zh ? "负责人" : "Owner"}</TmTableHeaderCell>
                <TmTableHeaderCell className="w-[140px]">{zh ? "状态" : "Status"}</TmTableHeaderCell>
                <TmTableHeaderCell>{zh ? "遗留动作 / 验证证据" : "Remaining action / evidence"}</TmTableHeaderCell>
              </TmTableRow>
            </TmTableHead>
            <TmTableBody>
              {MIGRATIONS.map((item) => (
                <TmTableRow key={item.id} data-migration-id={item.id}>
                  <TmTableRowHeader className="align-top py-3 font-normal text-tm-fg">{copy(item.category)}</TmTableRowHeader>
                  <TmTableCell className="align-top py-3"><code className="whitespace-normal text-xs text-tm-fg-2">{item.legacy}</code></TmTableCell>
                  <TmTableCell className="align-top py-3"><code className="whitespace-normal text-xs text-tm-accent">{item.canonical}</code></TmTableCell>
                  <TmTableCell className="align-top py-3 leading-5">{copy(item.consumers)}</TmTableCell>
                  <TmTableCell className="align-top py-3 leading-5">{copy(item.owner)}</TmTableCell>
                  <TmTableCell className="align-top py-3"><MigrationBadge status={item.status} zh={zh} /></TmTableCell>
                  <TmTableCell className="align-top py-3 leading-5 text-tm-fg-2">{copy(item.closure)}</TmTableCell>
                </TmTableRow>
              ))}
            </TmTableBody>
          </TmTable>
        </TmTableFrame>
        <p className="border-t border-tm-rule px-3 py-2 text-xs leading-5 text-tm-muted">
          {zh
            ? "状态来自当前源码、生产消费关系和自动设计审计。登记不等于已经迁移，受控例外也不等于缺陷；每项都必须保留明确的边界与收尾条件。"
            : "Status is derived from current source, production consumers, and the design audit. Registration is not migration, and an exception is not a defect; every item retains an explicit boundary and closure condition."}
        </p>
      </TmPane>
    </div>
  );
}

function MigrationBadge({ status, zh }: { readonly status: MigrationStatus; readonly zh: boolean }) {
  const meta = STATUS_META[status];
  return <TmBadge tone={meta.tone}>{zh ? meta.label.zh : meta.label.en}</TmBadge>;
}

function PatternRow({ label, text }: { readonly label: string; readonly text: string }) {
  return (
    <div className="grid min-h-14 grid-cols-[110px_1fr] gap-4 px-4 py-3">
      <span className="font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{label}</span>
      <p className="text-xs leading-5 text-tm-fg-2">{text}</p>
    </div>
  );
}
