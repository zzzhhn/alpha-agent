"use client";

import { useState } from "react";
import type { Locale } from "@/lib/i18n";
import { TM_CHART_CSS } from "@/components/charts";
import { TmBadge } from "@/components/tm/TmBadge";
import { TmCols2, TmPane } from "@/components/tm/TmPane";
import { TmTooltip } from "@/components/tm/TmTooltip";
import { TmButton } from "@/components/tm/TmButton";
import { TmDialog } from "@/components/tm/TmDialog";

export function ReferenceSurfaces({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  const [dialogOpen, setDialogOpen] = useState(false);
  return (
    <div>
      <TmCols2>
        <TmPane
          title="SURFACE.TOOLTIP"
          meta={zh ? "hover、focus 与 Escape 语义一致" : "same hover, focus, and Escape behavior"}
          bodyClassName="p-4"
        >
          <div className="flex min-h-24 flex-wrap items-center justify-center gap-6">
            {(["top", "bottom", "right"] as const).map((placement) => (
              <TmTooltip
                key={placement}
                placement={placement}
                ariaLabel={zh ? `显示 ${placement} 提示` : `Show ${placement} tooltip`}
                content={
                  zh
                    ? "这是生产级 TmTooltip。内容通过 portal 渲染，不会被表格或侧边栏裁剪。"
                    : "This is the production TmTooltip. Its portal is not clipped by tables or navigation."
                }
              >
                <span className="inline-flex h-7 items-center border border-tm-rule bg-tm-bg-2 px-3 font-tm-mono text-[10px] uppercase text-tm-fg-2">
                  {placement}
                </span>
              </TmTooltip>
            ))}
          </div>
        </TmPane>

        <TmPane
          title="SURFACE.CHART TOKENS"
          meta={zh ? "SVG 与 Canvas 共用语义色" : "one semantic palette for SVG and canvas"}
          bodyClassName="p-4"
        >
          <figure>
            <svg
              viewBox="0 0 520 132"
              role="img"
              aria-label={zh ? "示例净值曲线，先回撤后恢复" : "Sample equity curve with a drawdown and recovery"}
              className="h-32 w-full border border-tm-rule bg-tm-bg"
            >
              {[32, 66, 100].map((y) => (
                <line key={y} x1="0" x2="520" y1={y} y2={y} stroke={TM_CHART_CSS.grid} />
              ))}
              <polyline
                points="8,104 78,82 146,91 214,54 282,73 350,45 420,51 512,20"
                fill="none"
                stroke={TM_CHART_CSS.positive}
                strokeWidth="3"
              />
              <polyline
                points="146,91 214,54 282,73"
                fill="none"
                stroke={TM_CHART_CSS.negative}
                strokeWidth="3"
              />
            </svg>
            <figcaption className="mt-2 text-[10.5px] leading-5 text-tm-muted">
              {zh
                ? "示例数据：绿色表示正向路径，红色表示回撤段；图表必须同时提供文字总结。"
                : "Sample data: green is the positive path and red is the drawdown segment. Every chart also needs a text summary."}
            </figcaption>
          </figure>
        </TmPane>
      </TmCols2>

      <TmPane title="SURFACE.OVERLAY CONTRACT" meta={zh ? "没有完成的资产不冒充生产组件" : "planned assets never masquerade as production-ready"}>
        <div className="grid gap-px bg-tm-rule p-px sm:grid-cols-2 xl:grid-cols-4">
          <Contract name="TmTooltip" state="READY" />
          <Contract name="TmPopover" state="PLANNED" />
          <Contract name="TmDialog" state="READY" />
          <Contract name="TmDrawer" state="PLANNED" />
        </div>
      </TmPane>

      <TmPane
        title="SURFACE.DIALOG"
        meta={zh ? "焦点进入、Tab 循环、Escape 关闭并恢复焦点" : "focus entry, Tab loop, Escape close, and focus restore"}
        bodyClassName="p-4"
      >
        <TmButton variant="secondary" onClick={() => setDialogOpen(true)}>
          {zh ? "打开对话框示例" : "Open dialog example"}
        </TmButton>
        <TmDialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          closeLabel={zh ? "关闭对话框" : "Close dialog"}
          eyebrow="DIALOG.SAMPLE"
          title={zh ? "确认研究上下文" : "Confirm research context"}
          description={zh ? "示例内容，不代表真实账户或市场状态。" : "Sample content, not live account or market state."}
          className="max-w-[560px]"
        >
          <p className="text-[11px] leading-5 text-tm-fg-2">
            {zh ? "焦点不会离开对话框，关闭后会回到触发按钮。" : "Focus stays inside the dialog and returns to its trigger after close."}
          </p>
        </TmDialog>
      </TmPane>
    </div>
  );
}

function Contract({ name, state }: { readonly name: string; readonly state: "READY" | "PLANNED" }) {
  return (
    <div className="flex min-h-16 items-center justify-between bg-tm-bg px-3 py-3">
      <code className="font-tm-mono text-[11px] text-tm-fg">{name}</code>
      <TmBadge tone={state === "READY" ? "positive" : "warning"}>{state}</TmBadge>
    </div>
  );
}
