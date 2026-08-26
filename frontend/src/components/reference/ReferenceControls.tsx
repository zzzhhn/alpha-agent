"use client";

import { useState, type ReactNode } from "react";
import { Play, RefreshCw, Trash2 } from "lucide-react";
import { t, type Locale } from "@/lib/i18n";
import { TmButton, TmDisclosureButton, TmIconButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmCheckbox, TmInput, TmNumberInput, TmRange, TmSelect, TmTextarea } from "@/components/tm/TmField";
import { TmCols2, TmPane } from "@/components/tm/TmPane";
import { TmChip } from "@/components/tm/TmSubbar";
import { TmToggleGroup } from "@/components/tm/TmToggleGroup";
import { TmSelectMenu } from "@/components/tm/TmSelectMenu";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";

type DemoTab = "overview" | "evidence" | "history";

export function ReferenceControls({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  const [query, setQuery] = useState("rank(ts_mean(returns, 12))");
  const [universe, setUniverse] = useState("SP500");
  const [notesByLocale, setNotesByLocale] = useState<Record<Locale, string>>({
    zh: "解释这一参数如何改变决策。",
    en: "Explain how this parameter changes the decision.",
  });
  const [tab, setTab] = useState<DemoTab>("overview");
  const [chip, setChip] = useState("all");
  const [density, setDensity] = useState<"compact" | "standard">("compact");
  const [breakdown, setBreakdown] = useState(false);
  const [disclosureOpen, setDisclosureOpen] = useState(false);
  const [topPct, setTopPct] = useState(20);
  const [family, setFamily] = useState("options");
  const [threshold, setThreshold] = useState(0.7);

  return (
    <div>
      <TmPane
        title={t(locale, "reference.pane.controlButton")}
        meta={zh ? "一屏仅一个实心绿色主操作" : "one filled green primary action per screen"}
        bodyClassName="p-4"
      >
        <div className="grid gap-4 xl:grid-cols-3">
          <Specimen label={t(locale, "reference.group.variants")}>
            <TmButton variant="primary"><Play className="h-3.5 w-3.5" />{zh ? "运行分析" : "Run analysis"}</TmButton>
            <TmButton variant="secondary"><RefreshCw className="h-3.5 w-3.5" />{zh ? "刷新" : "Refresh"}</TmButton>
            <TmButton variant="ghost">{zh ? "查看详情" : "View details"}</TmButton>
            <TmLinkButton href="/reference" variant="secondary">
              {zh ? "导航链接" : "Navigation link"}
            </TmLinkButton>
            <TmButton variant="danger"><Trash2 className="h-3.5 w-3.5" />{zh ? "删除" : "Delete"}</TmButton>
          </Specimen>
          <Specimen label={t(locale, "reference.group.sizes")}>
            <TmButton size="xs" variant="secondary">XS · 24</TmButton>
            <TmButton size="sm" variant="secondary">SM · 28</TmButton>
            <TmButton size="md" variant="secondary">MD · 32</TmButton>
            <TmIconButton
              label={zh ? "刷新示例" : "Refresh example"}
              icon={<RefreshCw className="h-3.5 w-3.5" />}
            />
          </Specimen>
          <Specimen label={t(locale, "reference.group.states")}>
            <TmButton loading loadingLabel={zh ? "运行中" : "Running"}>{zh ? "运行" : "Run"}</TmButton>
            <span className="inline-flex flex-col items-start gap-1">
              <TmButton variant="secondary" disabled>{zh ? "不可用" : "Disabled"}</TmButton>
              <span className="max-w-44 text-xs leading-5 text-tm-muted">
                {zh ? "前置条件：先选择数据集。" : "Prerequisite: select a dataset first."}
              </span>
            </span>
          </Specimen>
        </div>
      </TmPane>

      <TmCols2>
        <TmPane title={t(locale, "reference.pane.controlField")} bodyClassName="grid gap-4 p-4 sm:grid-cols-2">
          <TmInput
            label={zh ? "因子表达式" : "Factor expression"}
            hint={zh ? "标准高度 32px" : "Standard 32px density"}
            value={query}
            onChange={setQuery}
          />
          <TmSelect
            label={zh ? "股票池" : "Universe"}
            value={universe}
            onChange={setUniverse}
            options={[
              { value: "SP500", label: "S&P 500" },
              { value: "TOP1000", label: "TOP 1000" },
            ]}
          />
          <TmNumberInput
            label={zh ? "多头分位" : "Long percentile"}
            value={topPct}
            onChange={setTopPct}
            min={1}
            max={50}
            suffix="%"
          />
          <TmInput
            label={zh ? "错误示例" : "Error example"}
            value="unsupported_field"
            onChange={() => undefined}
            error={zh ? "字段不在当前数据集中。" : "Field is unavailable in this dataset."}
          />
          <TmInput
            label={zh ? "禁用示例" : "Disabled example"}
            value={zh ? "等待上游数据" : "Waiting for upstream data"}
            onChange={() => undefined}
            disabled
          />
          <TmCheckbox
            checked={breakdown}
            onChange={setBreakdown}
            label={zh ? "返回每日明细" : "Return daily breakdown"}
            hint={zh ? "显式开启高成本证据。" : "Explicitly opt in to heavier evidence."}
          />
          <TmRange
            label={zh ? "自相关门槛" : "Self-correlation threshold"}
            hint={zh ? "方向键支持精细调整" : "Arrow keys support precise adjustment"}
            value={threshold}
            onChange={setThreshold}
            min={0.5}
            max={0.9}
            step={0.01}
            formatValue={(value) => value.toFixed(2)}
          />
          <TmTextarea
            label={zh ? "研究备注" : "Research note"}
            hint={zh ? "仅在长文本需要时使用" : "Use only when long text is required"}
            value={notesByLocale[locale]}
            onChange={(next) =>
              setNotesByLocale((current) => ({ ...current, [locale]: next }))
            }
            className="sm:col-span-2"
          />
        </TmPane>

        <TmPane title={t(locale, "reference.pane.controlNavigation")} bodyClassName="space-y-5 p-4">
          <div>
            <p className="mb-2 font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{t(locale, "reference.group.selectMenu")}</p>
            <TmSelectMenu
              value={family}
              onChange={setFamily}
              ariaLabel={zh ? "选择研究家族" : "Select research family"}
              buttonClassName="w-full"
              menuMinWidth={260}
              options={[
                {
                  value: "options",
                  label: zh ? "期权多机制" : "Options mechanisms",
                  meta: zh ? "隐含波动率、偏度、期限结构" : "IV, skew, and term structure",
                },
                {
                  value: "fundamental",
                  label: zh ? "基本面" : "Fundamental",
                  meta: zh ? "质量、估值与修正" : "quality, value, and revisions",
                },
                {
                  value: "sentiment",
                  label: zh ? "情绪" : "Sentiment",
                  meta: zh ? "新闻与行为代理" : "news and behavioral proxies",
                },
              ]}
            />
            <p className="mt-1 text-xs leading-5 text-tm-muted">
              {zh ? "支持方向键、Home、End、Enter、Space 与 Escape。" : "Supports arrows, Home, End, Enter, Space, and Escape."}
            </p>
          </div>
          <div>
            <p className="mb-2 font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{t(locale, "reference.group.segmentedTabs")}</p>
            <SegmentedTabs
              idBase="reference-control-demo"
              ariaLabel={zh ? "控件示例分类" : "Control example categories"}
              items={[
                { key: "overview", label: zh ? "概览" : "Overview" },
                { key: "evidence", label: zh ? "证据" : "Evidence" },
                { key: "history", label: zh ? "历史" : "History" },
              ]}
              active={tab}
              onChange={setTab}
            />
            <div
              id={`reference-control-demo-panel-${tab}`}
              role="tabpanel"
              aria-labelledby={`reference-control-demo-tab-${tab}`}
              className="border-x border-b border-tm-rule p-3 text-xs text-tm-fg-2"
            >
              {zh ? "方向键、Home 和 End 均可切换。" : "Arrow keys, Home, and End all switch tabs."}
            </div>
          </div>
          <div>
            <p className="mb-2 font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{t(locale, "reference.group.disclosure")}</p>
            <TmDisclosureButton
              expanded={disclosureOpen}
              onClick={() => setDisclosureOpen((current) => !current)}
              label={zh ? "显示补充证据" : "Show supporting evidence"}
              meta={zh ? "3 个面板" : "3 panes"}
            />
            {disclosureOpen ? (
              <div className="border-x border-b border-tm-rule p-3 text-xs text-tm-fg-2">
                {zh ? "展开状态与键盘焦点共享同一规范。" : "Expanded state and keyboard focus share one convention."}
              </div>
            ) : null}
          </div>
          <div>
            <p className="mb-2 font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{t(locale, "reference.group.toggle")}</p>
            <TmToggleGroup
              value={density}
              onChange={setDensity}
              ariaLabel={zh ? "密度选择" : "Density selection"}
              options={[
                { value: "compact", label: zh ? "紧凑" : "Compact" },
                { value: "standard", label: zh ? "标准" : "Standard" },
              ]}
            />
          </div>
          <div>
            <p className="mb-2 font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{t(locale, "reference.group.filterChips")}</p>
            <div className="flex flex-wrap gap-1.5">
              {["all", "passed", "review"].map((value) => (
                <TmChip key={value} on={chip === value} onClick={() => setChip(value)}>
                  {value.toUpperCase()}
                </TmChip>
              ))}
            </div>
          </div>
        </TmPane>
      </TmCols2>
    </div>
  );
}

function Specimen({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div className="min-w-0 border border-tm-rule bg-tm-bg-2 p-3">
      <p className="mb-3 font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{label}</p>
      <div className="flex flex-wrap items-start gap-2">{children}</div>
    </div>
  );
}
