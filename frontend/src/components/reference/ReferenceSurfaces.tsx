"use client";

import { useState } from "react";
import { t, type Locale } from "@/lib/i18n";
import { TmBadge } from "@/components/tm/TmBadge";
import { TmPane } from "@/components/tm/TmPane";
import { TmTooltip } from "@/components/tm/TmTooltip";
import { TmButton } from "@/components/tm/TmButton";
import { TmDialog } from "@/components/tm/TmDialog";
import { TmDrawer } from "@/components/tm/TmDrawer";

export function ReferenceSurfaces({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  const [dialogOpen, setDialogOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  return (
    <div>
      <TmPane
          title={t(locale, "reference.pane.surfaceTooltip")}
          meta={zh ? "hover、focus 与 Escape 语义一致" : "same hover, focus, and Escape behavior"}
          bodyClassName="p-4"
        >
          <div className="flex min-h-24 flex-wrap items-center justify-center gap-6">
            {(["top", "right", "bottom", "left"] as const).map((placement) => (
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
                <span className="inline-flex h-7 items-center border border-tm-rule bg-tm-bg-2 px-3 font-tm-mono text-xs uppercase text-tm-fg-2">
                  {placement}
                </span>
              </TmTooltip>
            ))}
          </div>
        </TmPane>

      <TmPane title={t(locale, "reference.pane.surfaceContract")} meta={zh ? "没有完成的资产不冒充生产组件" : "planned assets never masquerade as production-ready"}>
        <div className="grid gap-px bg-tm-rule p-px sm:grid-cols-2 xl:grid-cols-4">
          <Contract name="TmTooltip" state="READY" />
          <Contract name="TmSelectMenu" state="READY" />
          <Contract name="TmDialog" state="READY" />
          <Contract name="TmDrawer" state="READY" />
        </div>
      </TmPane>

      <TmPane
        title={t(locale, "reference.pane.surfaceDialog")}
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
          className="min-h-[360px] !max-w-[1120px]"
        >
          <p className="text-xs leading-5 text-tm-fg-2">
            {zh ? "焦点不会离开对话框，关闭后会回到触发按钮。" : "Focus stays inside the dialog and returns to its trigger after close."}
          </p>
        </TmDialog>
      </TmPane>

      <TmPane
        title={t(locale, "reference.pane.surfaceDrawer")}
        meta={zh ? "保留主页面上下文的侧向任务工作区" : "a side task workspace that preserves page context"}
        bodyClassName="p-4"
      >
        <TmButton variant="secondary" onClick={() => setDrawerOpen(true)}>
          {zh ? "打开抽屉示例" : "Open drawer example"}
        </TmButton>
        <TmDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          closeLabel={zh ? "关闭抽屉" : "Close drawer"}
          eyebrow="DRAWER.SAMPLE"
          title={zh ? "创建模拟订单" : "Create paper order"}
          description={
            zh
              ? "抽屉适合短任务与上下文编辑，不用于替代完整页面。"
              : "Use drawers for short contextual tasks, not as a substitute for a full page."
          }
          width="xl"
        >
          <div className="space-y-3 text-xs leading-5 text-tm-fg-2">
            <p>{zh ? "焦点进入抽屉后保持在其中，Escape 关闭并恢复到触发按钮。" : "Focus remains inside, Escape closes, and focus returns to the trigger."}</p>
            <div className="border border-tm-rule bg-tm-bg-2 p-3 font-tm-mono text-xs text-tm-muted">
              {zh ? "示例内容，不连接真实账户。" : "Sample content, not connected to a live account."}
            </div>
          </div>
        </TmDrawer>
      </TmPane>
    </div>
  );
}

function Contract({ name, state }: { readonly name: string; readonly state: "READY" | "PLANNED" }) {
  return (
    <div className="flex min-h-16 items-center justify-between bg-tm-bg px-3 py-3">
      <code className="font-tm-mono text-xs text-tm-fg">{name}</code>
      <TmBadge tone={state === "READY" ? "positive" : "warning"}>{state}</TmBadge>
    </div>
  );
}
