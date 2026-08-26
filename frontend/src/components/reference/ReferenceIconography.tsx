import {
  AlertCircle, AlertTriangle, ArrowDown, ArrowRight, ArrowUp, BellRing, Bookmark,
  Check, CheckCircle, CheckCircle2, ChevronDown, ChevronRight, ChevronUp, CircleHelp,
  Clipboard, Clock3, Compass, Cpu, ExternalLink, Filter, FlaskConical, Gauge, HelpCircle,
  History, Inbox, Info, LayoutGrid, Library, Loader2, Lock, LogIn, LogOut,
  MousePointerClick, Pencil, Play, RefreshCw, RotateCcw, Save, Send, ShieldAlert,
  ShieldCheck, Sparkles, Square, Star, Trash2, UserCircle, Wallet, X, XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { t, type Locale } from "@/lib/i18n";
import { TmCols2, TmPane } from "@/components/tm/TmPane";

const ICONS: ReadonlyArray<{ readonly name: string; readonly icon: LucideIcon }> = [
  { name: "AlertCircle", icon: AlertCircle }, { name: "AlertTriangle", icon: AlertTriangle },
  { name: "ArrowDown", icon: ArrowDown }, { name: "ArrowRight", icon: ArrowRight },
  { name: "ArrowUp", icon: ArrowUp }, { name: "BellRing", icon: BellRing },
  { name: "Bookmark", icon: Bookmark }, { name: "Check", icon: Check },
  { name: "CheckCircle", icon: CheckCircle }, { name: "CheckCircle2", icon: CheckCircle2 },
  { name: "ChevronDown", icon: ChevronDown }, { name: "ChevronRight", icon: ChevronRight },
  { name: "ChevronUp", icon: ChevronUp }, { name: "CircleHelp", icon: CircleHelp },
  { name: "Clipboard", icon: Clipboard }, { name: "Clock3", icon: Clock3 },
  { name: "Compass", icon: Compass }, { name: "Cpu", icon: Cpu },
  { name: "ExternalLink", icon: ExternalLink }, { name: "Filter", icon: Filter },
  { name: "FlaskConical", icon: FlaskConical }, { name: "Gauge", icon: Gauge },
  { name: "HelpCircle", icon: HelpCircle }, { name: "History", icon: History },
  { name: "Inbox", icon: Inbox }, { name: "Info", icon: Info },
  { name: "LayoutGrid", icon: LayoutGrid }, { name: "Library", icon: Library },
  { name: "Loader2", icon: Loader2 }, { name: "Lock", icon: Lock },
  { name: "LogIn", icon: LogIn }, { name: "LogOut", icon: LogOut },
  { name: "MousePointerClick", icon: MousePointerClick }, { name: "Pencil", icon: Pencil },
  { name: "Play", icon: Play }, { name: "RefreshCw", icon: RefreshCw },
  { name: "RotateCcw", icon: RotateCcw }, { name: "Save", icon: Save },
  { name: "Send", icon: Send }, { name: "ShieldAlert", icon: ShieldAlert },
  { name: "ShieldCheck", icon: ShieldCheck }, { name: "Sparkles", icon: Sparkles },
  { name: "Square", icon: Square }, { name: "Star", icon: Star },
  { name: "Trash2", icon: Trash2 }, { name: "UserCircle", icon: UserCircle },
  { name: "Wallet", icon: Wallet }, { name: "X", icon: X }, { name: "XCircle", icon: XCircle },
];

export function ReferenceIconography({ locale }: { readonly locale: Locale }) {
  const zh = locale === "zh";
  return (
    <div>
      <TmPane
        title={t(locale, "reference.pane.iconLibrary")}
        meta={zh ? `当前生产代码使用的 ${ICONS.length} 个 Lucide 图标` : `${ICONS.length} Lucide icons used by production code`}
        bodyClassName="grid grid-cols-3 gap-px bg-tm-rule p-px sm:grid-cols-5 lg:grid-cols-7"
      >
        {ICONS.map(({ name, icon: Icon }) => (
          <div key={name} className="flex min-h-20 min-w-0 flex-col items-center justify-center gap-2 bg-tm-bg px-2 py-3">
            <Icon className="h-5 w-5 text-tm-fg" aria-hidden />
            <code className="max-w-full truncate font-tm-mono text-xs text-tm-muted">{name}</code>
          </div>
        ))}
      </TmPane>

      <TmCols2>
        <TmPane title={t(locale, "reference.pane.iconRules")} bodyClassName="divide-y divide-tm-rule">
          <Rule label={zh ? "尺寸" : "Size"} text={zh ? "12px 仅用于紧凑数据行；14px 用于行内提示；16px 用于标准控件；20px 用于独立状态；24px 与 28px 仅用于空状态或品牌场景。" : "12px is reserved for compact data rows; 14px for inline cues; 16px for controls; 20px for standalone status; 24px and 28px only for empty or brand states."} />
          <Rule label={zh ? "线宽" : "Stroke"} text={zh ? "默认采用 Lucide 2px；1.2 至 1.8px 的生产例外必须与尺寸和场景一起登记。收藏态可填充，但不能与普通操作图标混用。" : "Use Lucide's 2px default. Production exceptions from 1.2 to 1.8px must be registered with size and context. Favorite states may fill, but must not mix with ordinary action icons."} />
          <Rule label={zh ? "语义" : "Meaning"} text={zh ? "装饰图标隐藏于读屏；纯图标按钮必须提供可访问名称和提示。" : "Hide decorative icons from assistive tech; icon-only buttons require an accessible name and tooltip."} />
        </TmPane>
        <TmPane title={zh ? "图标 · 文字符号边界" : "Icons · Text glyph boundary"} bodyClassName="divide-y divide-tm-rule">
          <GlyphRow glyphs={["▶", "▾", "▸", "·"]} label={zh ? "导航与折叠" : "Navigation and disclosure"} />
          <GlyphRow glyphs={["←", "→", "▲", "▼"]} label={zh ? "分页与排序" : "Pagination and sorting"} />
          <GlyphRow glyphs={["✓", "×", "⚠", "↗"]} label={zh ? "状态与外链" : "Status and external link"} />
          <p className="px-4 py-3 text-xs leading-5 text-tm-fg-2">
            {zh
              ? "这些是既有生产例外，不等同于图标库。只在紧凑导航、表格或状态文案里使用；若承担独立操作，必须迁移到 Lucide 并提供可访问名称。雷达图和演化图属于图表资产，在“图表与图形”登记。"
              : "These are registered production exceptions, not a second icon library. Use them only inside compact navigation, tables, or status copy. If a glyph becomes an independent action, migrate it to Lucide and provide an accessible name. Radar and evolution graphics belong in Visualizations."}
          </p>
        </TmPane>
      </TmCols2>
    </div>
  );
}

function GlyphRow({ glyphs, label }: { readonly glyphs: readonly string[]; readonly label: string }) {
  return (
    <div className="grid min-h-14 grid-cols-[144px_1fr] items-center gap-4 px-4 py-3">
      <span className="font-tm-mono text-xs font-semibold text-tm-muted">{label}</span>
      <span className="flex flex-wrap items-center gap-4 font-tm-mono text-sm text-tm-fg" aria-label={label}>
        {glyphs.map((glyph) => <span key={glyph} aria-hidden="true">{glyph}</span>)}
      </span>
    </div>
  );
}

function Rule({ label, text }: { readonly label: string; readonly text: string }) {
  return (
    <div className="grid min-h-16 grid-cols-[100px_1fr] gap-4 px-4 py-3">
      <span className="font-tm-mono text-xs font-semibold text-tm-muted">{label}</span>
      <p className="text-xs leading-5 text-tm-fg-2">{text}</p>
    </div>
  );
}
