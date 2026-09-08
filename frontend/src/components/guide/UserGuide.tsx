"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmPane, TmScreen } from "@/components/tm/TmPane";
import { TmInput } from "@/components/tm/TmField";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmSubbar, TmSubbarKV, TmStatusPill } from "@/components/tm/TmSubbar";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { GUIDE, GUIDE_SOURCES, GUIDE_VERSION, type Copy } from "./content";

export function UserGuide() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const copy = (value: Copy) => value[zh ? 0 : 1];
  const [chapter, setChapter] = useState(GUIDE[0].id);
  const [query, setQuery] = useState("");
  const needle = query.trim().toLocaleLowerCase();
  const visible = GUIDE.flatMap((section) => section.entries
    .filter((entry) => needle
      ? [section.title, entry.title, entry.body, ...(entry.steps ?? [])].flat().join(" ").toLocaleLowerCase().includes(needle)
      : section.id === chapter)
    .map((entry) => ({ ...entry, chapterTitle: section.title })));

  return (
    <TmScreen className="[&>*]:shrink-0">
      <WorkbenchHeader eyebrow={zh ? "参考 · 决策流程" : "Reference · Decision workflow"}
        title={zh ? "使用手册" : "User Guide"}
        subtitle={zh ? "知道何时研究、何时验证，以及何时不操作。" : "Know when to research, validate and take no action."}
        statuses={[{ label: zh ? "内容版本" : "Version", value: GUIDE_VERSION },
          { label: zh ? "用途" : "Purpose", value: zh ? "研究与模拟" : "Research & paper", tone: "warning" }]} />
      <TmSubbar>
        <TmSubbarKV label={zh ? "阅读路径" : "Reading path"} value={zh ? "开始 → 日常 → 研究 → 释义" : "Start → Routine → Research → Metrics"} />
        <TmStatusPill tone="warn">{zh ? "不是盈利承诺，也不是实时状态页" : "No profit promise; not live service status"}</TmStatusPill>
      </TmSubbar>
      <div className="flex flex-wrap items-end gap-3 border-b border-tm-rule p-4">
        <div className="w-full max-w-xl"><TmInput label={zh ? "搜索整本手册" : "Search the whole guide"}
          value={query} onChange={setQuery}
          placeholder={zh ? "例如：创收、Self-correlation、过期、成本" : "Try: income, self-correlation, stale, costs"} /></div>
        {needle ? <TmButton variant="secondary" onClick={() => setQuery("")}>{zh ? "清除搜索" : "Clear search"}</TmButton> : null}
      </div>
      {!needle ? <SegmentedTabs className="shrink-0" idBase="guide-chapter" ariaLabel={zh ? "手册章节" : "Guide chapters"}
        items={GUIDE.map((section) => ({ key: section.id, label: copy(section.title) }))}
        active={chapter} onChange={setChapter} /> : null}
      <div id={needle ? "guide-search-results" : `guide-chapter-panel-${chapter}`}
        role={needle ? "region" : "tabpanel"}
        aria-label={needle ? (zh ? "全书搜索结果" : "Guide search results") : undefined}
        aria-labelledby={needle ? undefined : `guide-chapter-tab-${chapter}`} className="min-w-0">
        {needle ? <p role="status" className="px-4 py-3 text-sm text-tm-muted">{zh ? `找到 ${visible.length} 项` : `${visible.length} results`}</p> : null}
        {visible.length === 0 ? <p className="p-4 text-sm text-tm-fg-2">{zh ? "没有匹配项。试试“回测”“登录”或清除搜索返回章节。" : "No matches. Try backtest or sign-in, or clear the search to return to chapters."}</p> : null}
        {visible.map((entry) => <TmPane key={entry.id} title={<h2 className="text-balance">{copy(entry.title)}</h2>}
          meta={needle ? copy(entry.chapterTitle) : undefined} bodyClassName="p-4 md:p-6">
          <div className="max-w-[75ch] space-y-4 text-sm leading-7 text-tm-fg-2">
            <p>{copy(entry.body)}</p>
            {entry.steps ? <ol className="list-decimal space-y-2 pl-5 marker:text-tm-accent">
              {entry.steps.map((step, i) => <li key={i}>{copy(step)}</li>)}
            </ol> : null}
            {entry.href && entry.link ? <TmLinkButton href={entry.href} prefetch={false} variant="secondary">{copy(entry.link)}</TmLinkButton> : null}
          </div>
        </TmPane>)}
      </div>
      <TmPane title={<h2>{zh ? "来源与更新边界" : "Sources and scope"}</h2>} bodyClassName="p-4">
        <p className="mb-3 text-sm leading-6 text-tm-muted">{zh ? "功能说明依据当前实现；外部规则请核对官方原文。手册本身不触发模型、仿真或数据库查询，共享页面的健康指示与登录组件仍按原规则工作。" : "Feature guidance follows the current implementation; verify external rules at the source. The guide triggers no model runs, simulations or database queries; shared health and auth components retain their usual behavior."}</p>
        <div className="flex flex-wrap gap-2">{GUIDE_SOURCES.map((source) => <TmLinkButton key={source.href} href={source.href} prefetch={false} variant="ghost">{copy(source.label)}</TmLinkButton>)}</div>
      </TmPane>
    </TmScreen>
  );
}
