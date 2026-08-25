import type { ReactNode } from "react";
import type { Locale } from "@/lib/i18n";
import { TmCols2, TmPane } from "@/components/tm/TmPane";

const COLORS = [
  ["BG", "bg-tm-bg", "--tm-bg"],
  ["RAISED", "bg-tm-bg-2", "--tm-bg-2"],
  ["HOVER", "bg-tm-bg-3", "--tm-bg-3"],
  ["FOREGROUND", "bg-tm-fg", "--tm-fg"],
  ["SECONDARY TEXT", "bg-tm-fg-2", "--tm-fg-2"],
  ["MUTED TEXT", "bg-tm-muted", "--tm-muted"],
  ["RULE", "bg-tm-rule", "--tm-rule"],
  ["STRONG RULE", "bg-tm-rule-2", "--tm-rule-2"],
  ["ACCENT", "bg-tm-accent", "--tm-accent"],
  ["ACCENT SOFT", "bg-tm-accent-soft", "--tm-accent-soft"],
  ["POSITIVE", "bg-tm-pos", "--tm-pos"],
  ["WARNING", "bg-tm-warn", "--tm-warn"],
  ["NEGATIVE", "bg-tm-neg", "--tm-neg"],
  ["INFO", "bg-tm-info", "--tm-info"],
] as const;

const SPACING = [4, 8, 12, 16, 24, 32] as const;

export function ReferenceFoundations({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  return (
    <div>
      <TmPane
        title="FOUNDATIONS.COLOR"
        meta={zh ? "语义色，不直接写 hex" : "semantic tokens, no component hex"}
        bodyClassName="grid grid-cols-2 gap-px bg-tm-rule p-px sm:grid-cols-4 xl:grid-cols-7"
      >
        {COLORS.map(([label, colorClass, token]) => (
          <div key={token} className="min-w-0 bg-tm-bg px-3 py-3">
            <div className={`h-10 w-full border border-tm-rule ${colorClass}`} />
            <p className="mt-2 font-tm-mono text-xs font-semibold text-tm-fg">{label}</p>
            <code className="font-tm-mono text-xs text-tm-muted">{token}</code>
          </div>
        ))}
      </TmPane>

      <TmCols2>
        <TmPane title="FOUNDATIONS.TYPE" bodyClassName="divide-y divide-tm-rule">
          <TypeRow label="PAGE TITLE">
            <span className="font-tm-serif text-[28px] font-semibold text-tm-fg">
              {zh ? "研究工作台" : "Research Workstation"}
            </span>
          </TypeRow>
          <TypeRow label="SECTION TITLE">
            <span className="text-[18px] font-semibold text-tm-fg">
              {zh ? "证据与决策" : "Evidence and decision"}
            </span>
          </TypeRow>
          <TypeRow label="BODY">
            <span className="font-sans text-[12px] text-tm-fg-2">
              {zh ? "解释状态、证据与下一步。" : "Explain status, evidence, and the next step."}
            </span>
          </TypeRow>
          <TypeRow label="CONTROL / DATA">
            <span className="font-tm-mono text-xs tabular-nums text-tm-fg">
              SP500_subset · SHARPE 1.84
            </span>
          </TypeRow>
          <TypeRow label="LABEL / CAPTION">
            <span className="font-tm-mono text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted">
              STATUS · UPDATED 08:32 UTC
            </span>
          </TypeRow>
        </TmPane>

        <TmPane title="FOUNDATIONS.GEOMETRY" bodyClassName="p-4">
          <p className="mb-4 max-w-prose text-xs leading-5 text-tm-fg-2">
            {zh
              ? "仅使用固定密度、间距与 0 至 2px 圆角。键盘焦点为 2px 语义绿色轮廓，不改变布局。"
              : "Use the fixed density and spacing scale with 0 to 2px radius. Keyboard focus is a 2px semantic outline that never changes layout."}
          </p>
          <div className="space-y-2">
            {SPACING.map((space) => (
              <div key={space} className="flex items-center gap-3 font-tm-mono text-xs text-tm-muted">
                <span className="w-8 tabular-nums">{space}px</span>
                <span className="h-2 bg-tm-accent" style={{ width: `${space * 3}px` }} />
              </div>
            ))}
          </div>
          <div className="mt-5 grid grid-cols-3 gap-2 font-tm-mono text-xs text-tm-fg-2">
            {["24px · XS", "28px · SM", "32px · MD"].map((height) => (
              <div key={height} className="border border-tm-rule bg-tm-bg-2 px-2 py-2 text-center">
                {height}
              </div>
            ))}
          </div>
        </TmPane>
      </TmCols2>
    </div>
  );
}

function TypeRow({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div className="grid min-h-16 grid-cols-[120px_1fr] items-center gap-4 px-4 py-3">
      <span className="font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
