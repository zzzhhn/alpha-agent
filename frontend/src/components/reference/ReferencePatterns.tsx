import type { Locale } from "@/lib/i18n";
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

const MIGRATIONS: ReadonlyArray<{
  legacy: string;
  canonical: string;
  status: string;
  tone: TmBadgeTone;
}> = [
  { legacy: "ui/Button", canonical: "TmButton", status: "ALIASED", tone: "positive" },
  { legacy: "raw input/select/textarea", canonical: "TmField", status: "IN PROGRESS", tone: "warning" },
  { legacy: "native range", canonical: "TmRange", status: "READY", tone: "positive" },
  { legacy: "local pagination", canonical: "TmPagination", status: "READY", tone: "positive" },
  { legacy: "page-local tables", canonical: "TmTable", status: "READY", tone: "positive" },
  { legacy: "local empty/error blocks", canonical: "TmStatePane", status: "READY", tone: "positive" },
  { legacy: "page-local dialogs", canonical: "TmDialog", status: "READY", tone: "positive" },
  { legacy: "page-local drawers", canonical: "TmDrawer", status: "READY", tone: "positive" },
  { legacy: "custom listbox dropdowns", canonical: "TmSelectMenu", status: "READY", tone: "positive" },
  { legacy: "ui/Card / glass-card", canonical: "TmPane", status: "PENDING", tone: "warning" },
  { legacy: "HoverTip + InfoTooltip", canonical: "TmTooltip", status: "ALIASED", tone: "positive" },
  { legacy: "component hex colors", canonical: "chartTokens", status: "READY", tone: "positive" },
];

export function ReferencePatterns({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  return (
    <div>
      <TmCols2>
        <TmPane title="PATTERN.ASYNC" bodyClassName="divide-y divide-tm-rule">
          <PatternRow label="LOADING" text={zh ? "保留几何，说明阶段；不使用无文案的无限 spinner。" : "Preserve geometry and narrate the stage; never use an unexplained infinite spinner."} />
          <PatternRow label="EMPTY" text={zh ? "说明缺少什么、为何重要，以及唯一下一步。" : "Name what is absent, why it matters, and the one next step."} />
          <PatternRow label="ERROR" text={zh ? "错误留在受影响面板，重试不清空其他上下文。" : "Keep the error local; retry without erasing unrelated context."} />
          <PatternRow label="STALE / PARTIAL" text={zh ? "显示时间与缺失范围，只刷新受影响证据。" : "Show timestamp and missing scope; refresh only affected evidence."} />
        </TmPane>

        <TmPane title="PATTERN.LIST + MUTATION" bodyClassName="divide-y divide-tm-rule">
          <PatternRow label="ROW" text={zh ? "整行安全时可选择；行内操作阻止冒泡并有独立名称。" : "Select the whole row when safe; inline actions stop propagation and have distinct names."} />
          <PatternRow label="PAGING" text={zh ? "分页保留筛选；切换每页数量回到第一页。" : "Pagination preserves filters; changing page size returns to page one."} />
          <PatternRow label="MUTATION" text={zh ? "可逆操作优先撤销；不可逆操作才增加确认摩擦。" : "Prefer undo for reversible actions; add confirmation friction only when necessary."} />
          <PatternRow label="PRIMARY" text={zh ? "每个屏幕上下文只有一个实心绿色主操作。" : "Each screen context has one filled green primary action."} />
        </TmPane>
      </TmCols2>

      <TmPane title="MIGRATION.STATUS" meta={zh ? "旧资产必须有明确替代与收尾状态" : "every legacy asset needs an explicit replacement and closure state"}>
        <TmTableFrame>
          <TmTable density="standard" caption={zh ? "设计资产迁移状态" : "Design asset migration status"}>
            <TmTableHead>
              <TmTableRow>
                <TmTableHeaderCell>{zh ? "旧资产" : "Legacy asset"}</TmTableHeaderCell>
                <TmTableHeaderCell>{zh ? "统一资产" : "Canonical asset"}</TmTableHeaderCell>
                <TmTableHeaderCell textAlign="right">{zh ? "状态" : "Status"}</TmTableHeaderCell>
              </TmTableRow>
            </TmTableHead>
            <TmTableBody>
              {MIGRATIONS.map((item) => (
                <TmTableRow key={item.legacy}>
                  <TmTableRowHeader className="font-normal text-tm-fg-2">{item.legacy}</TmTableRowHeader>
                  <TmTableCell className="text-tm-fg">{item.canonical}</TmTableCell>
                  <TmTableCell textAlign="right"><TmBadge tone={item.tone}>{item.status}</TmBadge></TmTableCell>
                </TmTableRow>
              ))}
            </TmTableBody>
          </TmTable>
        </TmTableFrame>
      </TmPane>
    </div>
  );
}

function PatternRow({ label, text }: { readonly label: string; readonly text: string }) {
  return (
    <div className="grid min-h-14 grid-cols-[110px_1fr] gap-4 px-4 py-3">
      <span className="font-tm-mono text-xs tracking-[0.06em] text-tm-muted">{label}</span>
      <p className="text-xs leading-5 text-tm-fg-2">{text}</p>
    </div>
  );
}
