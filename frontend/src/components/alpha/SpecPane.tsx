"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { extractOperands } from "@/lib/factor-spec";
import type { HypothesisTranslateResponse } from "@/lib/types";
import { TmButton } from "@/components/tm/TmButton";
import { PanePlaceholder } from "./PanePlaceholder";
import type { PaneState } from "./types";

interface Props {
  state: PaneState;
  data: HypothesisTranslateResponse | null;
  errorMessage: string | null;
  onRetry?: () => void;
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-2">
      <div className="h-3 w-3/4 animate-pulse rounded bg-tm-bg-3" />
      <div className="h-3 w-1/2 animate-pulse rounded bg-tm-bg-3" />
      <div className="h-16 w-full animate-pulse rounded bg-tm-bg-3" />
    </div>
  );
}

export function SpecPane({ state, data, errorMessage, onRetry }: Props) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const operands = data ? extractOperands(data.spec.expression) : [];

  return (
    <section className="flex min-h-[260px] flex-col gap-3 border border-tm-rule bg-tm-bg-2 p-4">
      <h3 className="font-tm-mono text-xs font-semibold uppercase tracking-[0.08em] text-tm-accent">
        {t(locale, "alpha.pane.spec" as Parameters<typeof t>[1])}
      </h3>
      {state === "waiting" ? (
        <PanePlaceholder
          hint={t(locale, "alpha.pane.waitingSpec" as Parameters<typeof t>[1])}
        />
      ) : state === "loading" ? (
        <Skeleton />
      ) : state === "error" ? (
        <div className="flex flex-col gap-2 text-xs text-tm-neg">
          <div className="break-words font-tm-mono">{errorMessage}</div>
          {onRetry && (
            <TmButton
              variant="danger"
              size="xs"
              onClick={onRetry}
              className="w-fit"
            >
              {t(locale, "alpha.pane.retranslate" as Parameters<typeof t>[1])}
            </TmButton>
          )}
        </div>
      ) : data ? (
        <>
          <pre className="overflow-x-auto border border-tm-rule bg-tm-bg p-3 font-mono text-xs leading-5 text-tm-fg">
            {data.spec.expression}
          </pre>
          <div>
            <p className="mb-1.5 font-tm-mono text-xs uppercase tracking-[0.1em] text-tm-muted">{t(locale, "alpha.pane.operators" as Parameters<typeof t>[1])}</p>
            <div className="flex flex-wrap gap-1">
              {data.spec.operators_used.map((operator) => <span key={operator} className="border border-tm-rule px-2 py-1 font-mono text-xs text-tm-fg-2">{operator}</span>)}
            </div>
          </div>
          <div>
            <p className="mb-1.5 font-tm-mono text-xs uppercase tracking-[0.1em] text-tm-muted">{zh ? "输入字段" : "Input fields"}</p>
            <div className="divide-y divide-tm-rule border-y border-tm-rule">
              {operands.length > 0 ? operands.map((operand) => (
                <div key={operand} className="flex min-h-8 items-center justify-between text-xs">
                  <code className="text-tm-fg">{operand}</code>
                  <span className="text-tm-muted">{zh ? "服务端字段白名单" : "server field allowlist"}</span>
                </div>
              )) : <p className="py-2 text-xs text-tm-muted">{zh ? "表达式不含数据字段" : "No data operand in expression"}</p>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-px border border-tm-rule bg-tm-rule text-xs">
            <div className="bg-tm-bg px-2 py-2"><p className="text-tm-muted">{zh ? "股票池" : "Universe"}</p><p className="mt-1 text-tm-fg">{data.spec.universe}</p></div>
            <div className="bg-tm-bg px-2 py-2"><p className="text-tm-muted">{zh ? "回看窗口" : "Lookback"}</p><p className="mt-1 text-tm-fg">{data.spec.lookback}D</p></div>
          </div>
          <div className="border-t border-tm-rule pt-2 text-xs leading-5 text-tm-muted">
            <p>{zh ? "处理流程" : "Processing"}</p>
            <p className="text-tm-fg-2">{zh ? "自然语言 → 受限 AST → 缓存面板 → 分组组合 → 样本外验证" : "Natural language → constrained AST → cached panel → quantile portfolio → OOS validation"}</p>
          </div>
        </>
      ) : null}
    </section>
  );
}
