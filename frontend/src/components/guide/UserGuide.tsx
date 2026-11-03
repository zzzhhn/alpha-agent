"use client";

import { useRef, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmPane, TmScreen } from "@/components/tm/TmPane";
import { TmInput } from "@/components/tm/TmField";
import { TmButton, TmLinkButton, TmRowButton } from "@/components/tm/TmButton";
import { TmStatusPill } from "@/components/tm/TmSubbar";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { GUIDE, GUIDE_SOURCES, GUIDE_VERSION, type Copy } from "./content";
import { guideTopics, searchGuideTopics, selectedGuideTopic } from "./guide-navigation";

export function UserGuide() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const copy = (value: Copy) => value[zh ? 0 : 1];
  const [chapter, setChapter] = useState(GUIDE[0].id);
  const [topic, setTopic] = useState<string>();
  const [query, setQuery] = useState("");
  const [searchTopic, setSearchTopic] = useState<string>();
  const searchInput = useRef<HTMLInputElement>(null);
  const searching = query.trim().length > 0;
  const visible = searching ? searchGuideTopics(query) : guideTopics(chapter);
  const selected = selectedGuideTopic(visible, searching ? searchTopic : topic);
  const changeQuery = (value: string) => {
    setQuery(value);
    setSearchTopic(undefined);
  };

  const reader = (
    <div className="grid min-w-0 md:grid-cols-[248px_minmax(0,1fr)]">
      <nav aria-label={searching ? (zh ? "搜索结果" : "Search results") : (zh ? "本章主题" : "Chapter topics")}
        className="min-w-0 border-b border-tm-rule bg-tm-bg-2 md:border-b-0 md:border-r">
        <div className="border-b border-tm-rule px-4 py-2 font-tm-mono text-xs font-semibold text-tm-muted">
          {searching ? (
            <span role="status">{zh ? `找到 ${visible.length} 项` : `${visible.length} ${visible.length === 1 ? "result" : "results"}`}</span>
          ) : (zh ? "本章主题" : "Chapter topics")}
        </div>
        <ol key={searching ? query.trim() : chapter} role="list"
          className="max-h-52 divide-y divide-tm-rule overflow-y-auto overscroll-y-contain md:max-h-80">
          {visible.map(({ entry, chapterTitle }, index) => {
            const active = entry.id === selected?.entry.id;
            return (
              <li key={entry.id}>
                <TmRowButton aria-current={active || undefined} aria-controls="guide-article"
                  onClick={() => (searching ? setSearchTopic : setTopic)(entry.id)}
                  className={`flex min-h-11 items-baseline gap-2.5 border-l-2 py-2.5 pl-3.5 pr-4 text-sm leading-5 hover:!bg-tm-bg-3 ${active
                    ? "border-tm-accent bg-tm-bg font-semibold text-tm-accent"
                    : "border-transparent text-tm-fg-2"}`}>
                  <span aria-hidden="true" className="font-tm-mono text-xs tabular-nums text-tm-muted">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="min-w-0">
                    {copy(entry.title)}
                    {searching ? <span className="block text-xs font-normal text-tm-muted">{copy(chapterTitle)}</span> : null}
                  </span>
                </TmRowButton>
              </li>
            );
          })}
        </ol>
      </nav>
      {selected ? (
        <TmPane className="min-w-0" bodyClassName="px-5 py-6 md:px-8 md:py-7">
          <article id="guide-article" aria-labelledby="guide-article-title" className="max-w-[70ch]">
            {searching ? <p className="mb-1 font-tm-mono text-xs font-semibold text-tm-accent">{copy(selected.chapterTitle)}</p> : null}
            <h2 id="guide-article-title" className="mb-4 text-balance font-tm-serif text-2xl font-semibold tracking-tight text-tm-fg">
              {copy(selected.entry.title)}
            </h2>
            <p className="text-sm leading-7 text-tm-fg-2">{copy(selected.entry.body)}</p>
            {selected.entry.steps ? (
              <ol role="list" className="mt-5 divide-y divide-tm-rule border-y border-tm-rule text-sm leading-6 text-tm-fg-2">
                {selected.entry.steps.map((step, index) => (
                  <li key={index} className="flex items-baseline gap-3 py-3">
                    <span aria-hidden="true" className="min-w-5 font-tm-mono text-xs font-semibold tabular-nums text-tm-accent">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span>{copy(step)}</span>
                  </li>
                ))}
              </ol>
            ) : null}
            {selected.entry.href && selected.entry.link ? (
              <TmLinkButton href={selected.entry.href} prefetch={false} variant="secondary" className="mt-5">
                {copy(selected.entry.link)}
              </TmLinkButton>
            ) : null}
          </article>
        </TmPane>
      ) : (
        <TmPane className="min-w-0" bodyClassName="px-5 py-7 md:px-8">
          <h2 className="font-tm-serif text-lg font-semibold text-tm-fg">
            {searching ? (zh ? "没有匹配的主题" : "No matching topics") : (zh ? "本章暂无主题" : "No topics in this chapter")}
          </h2>
          <p className="mt-2 text-sm leading-6 text-tm-muted">
            {searching
              ? (zh ? "试试“回测”“登录”，或清除搜索回到原主题。" : "Try “backtest” or “sign-in”, or clear search to return to your topic.")
              : (zh ? "请选择其他章节。" : "Choose another chapter.")}
          </p>
        </TmPane>
      )}
    </div>
  );

  return (
    <TmScreen className="[&>*]:shrink-0">
      <WorkbenchHeader title={zh ? "使用手册" : "User Guide"}
        subtitle={zh ? "知道何时研究、何时验证，以及何时不操作。" : "Know when to research, validate and take no action."}
        statuses={[{ label: zh ? "内容版本" : "Version", value: GUIDE_VERSION }]} />
      <div className="flex flex-wrap items-end justify-between gap-x-5 gap-y-3 px-4 py-3 md:px-6">
        <div className="flex w-full max-w-xl items-end gap-2">
          <TmInput ref={searchInput} type="search" className="min-w-0 flex-1"
            label={zh ? "搜索整本手册" : "Search the whole guide"} value={query} onChange={changeQuery}
            placeholder={zh ? "例如：模拟仓、Self-correlation、成本" : "Try: paper, self-correlation, costs"} />
          {searching ? <TmButton size="md" variant="secondary" onClick={() => {
            changeQuery("");
            searchInput.current?.focus();
          }}>{zh ? "清除搜索" : "Clear search"}</TmButton> : null}
        </div>
        <TmStatusPill tone="warn">{zh ? "不是盈利承诺，也不是实时状态页" : "No profit promise; not live service status"}</TmStatusPill>
      </div>
      {searching ? (
        <section aria-label={zh ? "全书搜索结果" : "Guide search results"}>{reader}</section>
      ) : (
        <div className="min-w-0">
          <SegmentedTabs idBase="guide-chapter" ariaLabel={zh ? "手册章节" : "Guide chapters"}
            items={GUIDE.map((section) => ({ key: section.id, label: copy(section.title) }))}
            active={chapter} onChange={(next) => {
              if (next === chapter) return;
              setChapter(next);
              setTopic(undefined);
            }} />
          {GUIDE.map((section) => (
            <section key={section.id} id={`guide-chapter-panel-${section.id}`} role="tabpanel"
              aria-labelledby={`guide-chapter-tab-${section.id}`} hidden={section.id !== chapter}>
              {section.id === chapter ? reader : null}
            </section>
          ))}
        </div>
      )}
      <TmPane title={<h2>{zh ? "来源与更新边界" : "Sources and scope"}</h2>} bodyClassName="px-4 py-3 md:px-6">
        <p className="mb-2 max-w-[90ch] text-sm leading-6 text-tm-muted">
          {zh
            ? `手册记录 ${GUIDE_VERSION} 版本的功能，不触发模型、仿真或数据库查询。共享健康指示与登录仍按原规则工作；外部规则请核对官方原文。`
            : `This guide describes the ${GUIDE_VERSION} version and triggers no model runs, simulations or database queries. Shared health and sign-in still work as usual. Verify external rules at the source.`}
        </p>
        <ul className="flex flex-wrap gap-x-3 gap-y-1">
          {GUIDE_SOURCES.map((source) => (
            <li key={source.href} className="min-w-0">
              <TmLinkButton href={source.href} prefetch={false} variant="ghost"
                className="!h-auto !justify-start !whitespace-normal !px-0 py-1 text-left underline decoration-tm-rule-2 underline-offset-4">
                {copy(source.label)}
              </TmLinkButton>
            </li>
          ))}
        </ul>
      </TmPane>
    </TmScreen>
  );
}
