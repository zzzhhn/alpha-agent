"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";

interface PipelineStage {
  readonly id: string;
  readonly labelKey: string;
  readonly href: string;
}

const PIPELINE_STAGES: readonly PipelineStage[] = [
  { id: "data", labelKey: "stage.data", href: "/market" },
  { id: "feature", labelKey: "stage.feature", href: "/market" },
  { id: "inference", labelKey: "stage.inference", href: "/inference" },
  { id: "strategy", labelKey: "stage.strategy", href: "/alpha" },
  { id: "risk", labelKey: "stage.risk", href: "/gateway" },
  { id: "execution", labelKey: "stage.execution", href: "/orders" },
  { id: "audit", labelKey: "stage.audit", href: "/audit" },
];

function getActiveStageId(pathname: string): string {
  const stageMap: Record<string, string> = {
    "/market": "data",
    "/inference": "inference",
    "/alpha": "strategy",
    "/portfolio": "strategy",
    "/orders": "execution",
    "/gateway": "risk",
    "/audit": "audit",
  };
  return stageMap[pathname] ?? "inference";
}

export function Breadcrumb() {
  const pathname = usePathname();
  const { locale } = useLocale();
  const activeStageId = getActiveStageId(pathname);

  return (
    <nav
      className="flex flex-wrap items-center gap-1 text-xs text-muted"
      aria-label="Pipeline stages"
    >
      {PIPELINE_STAGES.map((stage, index) => {
        const isActive = stage.id === activeStageId;
        const isLast = index === PIPELINE_STAGES.length - 1;

        return (
          <span key={stage.id} className="flex items-center gap-1">
            <Link
              href={stage.href}
              className={clsx(
                "rounded px-1.5 py-0.5 transition-all duration-200",
                isActive
                  ? "border-b-2 border-accent font-semibold text-accent"
                  : "hover:bg-white/5 hover:text-text-secondary"
              )}
              aria-current={isActive ? "step" : undefined}
            >
              {t(
                locale,
                stage.labelKey as Parameters<typeof t>[1]
              )}
            </Link>
            {!isLast && (
              <span className="text-[10px] text-border" aria-hidden="true">
                {"\u203A"}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
