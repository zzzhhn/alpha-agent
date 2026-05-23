# Phase UX-0 Architecture Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land two cross-page architectural foundations before any single-page redesign begins: (1) a custom Toast system that all subsequent mutation feedback funnels through, and (2) `loading.tsx` skeletons for the four dashboard pages currently missing them. Together these address Principle 3 (Visibility of system status) for ALL pages with one set of changes, instead of forcing every per-page redesign to reinvent the same patterns.

**Architecture:** A small custom Toast subsystem (no new npm dep): `ToastProvider` context + `useToast` hook with `toast.success`/`toast.error`/`toast.info` API + `ToastViewport` portal in the dashboard layout. Each toast renders with `tm-*` design tokens and auto-dismisses on a per-toast timer (default 4s, configurable, `error` stays until manually dismissed). The 4 missing `loading.tsx` files mirror the existing `/picks/loading.tsx` pattern: route-level Suspense skeleton with `animate-pulse` matching the real page layout shape.

**Tech Stack:** Next.js 14 App Router (Server Components + route-level `loading.tsx`), TypeScript, Tailwind, lucide-react icons. No new dependencies.

**Scope decisions (locked 2026-05-23):**
- Toast API mirrors sonner/react-hot-toast conventions (`toast.success(msg)`, etc.) for muscle-memory portability.
- This phase only PROVIDES the Toast system; existing 5 pages keep their inline error state for now. Each subsequent per-page redesign will migrate that page's feedback to `useToast` as part of its scope. Avoids touching 4 pages we have not yet redesigned.
- `loading.tsx` files are routed Suspense boundaries (Next.js convention) and do not require any prop changes elsewhere.

**UX principles trace:**
1. **Visibility**: 4 new loading.tsx skeletons + Toast = the system speaks during initial fetch AND during mutations. Two of the most common "is anything happening?" gaps closed at once.
2. **Forgiveness**: Toast error variant carries an optional `action: { label, onClick }` field so callers can offer a one-click recovery (e.g., "Retry") inline with the error message — Undo affordance baked into the architecture.
3. **Respects user time**: loading.tsx eliminates the visible blank-page period during RSC fetch (skeleton appears <100ms after navigation).
4. **Affordance**: Toast `kind` maps to color + icon (success = `tm-pos` + Check; error = `tm-neg` + AlertCircle; info = `tm-fg-2` + Info). The visual signals what kind of feedback it is at a glance.

---

## Dependencies + grounding

- Existing precedent: `frontend/src/app/(dashboard)/picks/loading.tsx` is the canonical example of an animate-pulse skeleton matching the real page structure. Read it first.
- Existing dashboard layout: `frontend/src/app/(dashboard)/layout.tsx` is where `<ToastProvider>` must wrap the children so `useToast` is reachable from every page.
- Existing UI components: `frontend/src/components/ui/Button.tsx`, `Card.tsx`, etc. are the precedent style. New Toast components live in `frontend/src/components/ui/toast/`.
- `tm-*` token palette: tokens like `tm-pos`, `tm-neg`, `tm-warn`, `tm-fg-1`, `tm-fg-2`, `tm-card`, `tm-line`, `tm-accent` already in use across the app. Toast component uses these tokens (NOT raw Tailwind palette).
- lucide-react icons used: `CheckCircle2`, `AlertCircle`, `Info`, `X` (close button), with `strokeWidth={1.75}` per project convention.

---

## File Structure

- `frontend/src/components/ui/toast/ToastProvider.tsx` (new): React Context provider + reducer for toast queue.
- `frontend/src/components/ui/toast/useToast.ts` (new): hook returning `{ toast: { success, error, info, dismiss } }`.
- `frontend/src/components/ui/toast/Toast.tsx` (new): single-toast component (icon + message + optional action button + dismiss X).
- `frontend/src/components/ui/toast/ToastViewport.tsx` (new): portal-mounted stacked container, fixed bottom-right.
- `frontend/src/components/ui/toast/index.ts` (new): barrel exports.
- `frontend/src/app/(dashboard)/layout.tsx` (modify): wrap children in `<ToastProvider>` + `<ToastViewport>`.
- `frontend/src/app/(dashboard)/alpha/loading.tsx` (new)
- `frontend/src/app/(dashboard)/backtest/loading.tsx` (new)
- `frontend/src/app/(dashboard)/factor-lab/loading.tsx` (new)
- `frontend/src/app/(dashboard)/evolution/loading.tsx` (new)

---

### Task 1: Toast subsystem (Provider + hook + Toast + Viewport)

**Files:**
- Create: 5 files under `frontend/src/components/ui/toast/`

- [ ] **Step 1: READ precedents**

```bash
cat frontend/src/app/(dashboard)/picks/loading.tsx
cat frontend/src/components/ui/Button.tsx | head -30
grep -nE 'tm-pos|tm-neg|tm-warn|tm-card|tm-line|tm-accent' frontend/src/app/globals.css | head -10
```
Confirm the tm-* token names are usable as Tailwind classes (they should be, via `tailwind.config.ts` mapping).

- [ ] **Step 2: Implement `ToastProvider.tsx`**

```tsx
"use client";

import { createContext, useCallback, useReducer, type ReactNode } from "react";

export type ToastKind = "success" | "error" | "info";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastItem {
  id: string;
  kind: ToastKind;
  message: string;
  duration: number; // ms; 0 = sticky (error default)
  action?: ToastAction;
}

interface ToastContextValue {
  items: ToastItem[];
  enqueue: (toast: Omit<ToastItem, "id">) => string;
  dismiss: (id: string) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

type Action =
  | { type: "enqueue"; item: ToastItem }
  | { type: "dismiss"; id: string };

function reducer(state: ToastItem[], action: Action): ToastItem[] {
  if (action.type === "enqueue") return [...state, action.item];
  if (action.type === "dismiss") return state.filter(t => t.id !== action.id);
  return state;
}

let _id = 0;
const _nextId = () => `t${++_id}_${Date.now()}`;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, dispatch] = useReducer(reducer, []);

  const enqueue = useCallback((t: Omit<ToastItem, "id">) => {
    const id = _nextId();
    dispatch({ type: "enqueue", item: { ...t, id } });
    if (t.duration > 0) {
      setTimeout(() => dispatch({ type: "dismiss", id }), t.duration);
    }
    return id;
  }, []);

  const dismiss = useCallback((id: string) => {
    dispatch({ type: "dismiss", id });
  }, []);

  return (
    <ToastContext.Provider value={{ items, enqueue, dismiss }}>
      {children}
    </ToastContext.Provider>
  );
}
```

- [ ] **Step 3: Implement `useToast.ts`**

```ts
"use client";

import { useContext } from "react";
import { ToastContext, type ToastAction } from "./ToastProvider";

interface ToastOptions {
  duration?: number;
  action?: ToastAction;
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be called inside <ToastProvider>");
  }
  return {
    toast: {
      success: (message: string, opts?: ToastOptions) =>
        ctx.enqueue({
          kind: "success",
          message,
          duration: opts?.duration ?? 4000,
          action: opts?.action,
        }),
      error: (message: string, opts?: ToastOptions) =>
        // Errors are sticky by default (duration=0); users must dismiss or
        // take the offered action. Forgiveness UX: an error should not
        // disappear before the user has a chance to read it.
        ctx.enqueue({
          kind: "error",
          message,
          duration: opts?.duration ?? 0,
          action: opts?.action,
        }),
      info: (message: string, opts?: ToastOptions) =>
        ctx.enqueue({
          kind: "info",
          message,
          duration: opts?.duration ?? 3000,
          action: opts?.action,
        }),
      dismiss: (id: string) => ctx.dismiss(id),
    },
  };
}
```

- [ ] **Step 4: Implement `Toast.tsx`**

```tsx
"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useContext } from "react";
import { ToastContext, type ToastItem } from "./ToastProvider";

const _styles = {
  success: {
    border: "border-tm-pos/40",
    bg: "bg-tm-pos/10",
    icon: <CheckCircle2 className="h-4 w-4 text-tm-pos" strokeWidth={1.75} />,
  },
  error: {
    border: "border-tm-neg/40",
    bg: "bg-tm-neg/10",
    icon: <AlertCircle className="h-4 w-4 text-tm-neg" strokeWidth={1.75} />,
  },
  info: {
    border: "border-tm-line",
    bg: "bg-tm-card",
    icon: <Info className="h-4 w-4 text-tm-fg-2" strokeWidth={1.75} />,
  },
};

export function Toast({ item }: { item: ToastItem }) {
  const ctx = useContext(ToastContext);
  if (!ctx) return null;
  const style = _styles[item.kind];
  return (
    <div
      role={item.kind === "error" ? "alert" : "status"}
      className={`flex items-start gap-3 rounded border ${style.border} ${style.bg} px-3 py-2 shadow-sm min-w-[280px] max-w-[480px]`}
    >
      <div className="mt-0.5">{style.icon}</div>
      <div className="flex-1 text-sm text-tm-fg-1">{item.message}</div>
      {item.action && (
        <button
          onClick={() => {
            item.action!.onClick();
            ctx.dismiss(item.id);
          }}
          className="text-sm font-semibold text-tm-accent hover:underline"
        >
          {item.action.label}
        </button>
      )}
      <button
        onClick={() => ctx.dismiss(item.id)}
        aria-label="Dismiss"
        className="text-tm-fg-2 hover:text-tm-fg-1"
      >
        <X className="h-3.5 w-3.5" strokeWidth={1.75} />
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Implement `ToastViewport.tsx`**

```tsx
"use client";

import { useContext } from "react";
import { ToastContext } from "./ToastProvider";
import { Toast } from "./Toast";

export function ToastViewport() {
  const ctx = useContext(ToastContext);
  if (!ctx) return null;
  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
    >
      {ctx.items.map(item => (
        <div key={item.id} className="pointer-events-auto">
          <Toast item={item} />
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Implement `index.ts` barrel**

```ts
export { ToastProvider } from "./ToastProvider";
export { ToastViewport } from "./ToastViewport";
export { useToast } from "./useToast";
export type { ToastKind, ToastAction, ToastItem } from "./ToastProvider";
```

- [ ] **Step 7: tsc + lint clean**

```bash
cd frontend && npx tsc --noEmit && npx next lint
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/ui/toast/
git commit -m "feat(ui): Toast subsystem (Provider + useToast + Toast + Viewport) (Phase UX-0)"
```

---

### Task 2: Wire ToastProvider into dashboard layout

**Files:**
- Modify: `frontend/src/app/(dashboard)/layout.tsx`

- [ ] **Step 1: READ the existing layout**

```bash
cat "frontend/src/app/(dashboard)/layout.tsx"
```
Identify where children are rendered. Insertion point: wrap `{children}` in `<ToastProvider>...{children}<ToastViewport/></ToastProvider>`.

- [ ] **Step 2: Wire**

Import and wrap. Example shape (adapt to the actual layout file's existing structure):
```tsx
import { ToastProvider, ToastViewport } from "@/components/ui/toast";

// inside the layout's return JSX, wrap children:
<ToastProvider>
  {/* ...existing layout chrome (sidebar, top nav)... */}
  {children}
  <ToastViewport />
</ToastProvider>
```

The provider must be a Client Component subtree; if the layout file is a Server Component (likely), `<ToastProvider>` itself is `"use client"` so it can wrap server-rendered `{children}`.

- [ ] **Step 3: Manual sanity (optional, dev)**

Add a temporary test in `picks/page.tsx` or similar: `const { toast } = useToast(); useEffect(() => toast.info("layout wired"), []);`. Verify the toast appears bottom-right. REVERT before commit.

- [ ] **Step 4: tsc + build clean**

```bash
cd frontend && npx tsc --noEmit && npm run build
```
Pre-existing `/picks` ECONNREFUSED still acceptable; the new layout must build.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/app/(dashboard)/layout.tsx"
git commit -m "feat(layout): wire ToastProvider + ToastViewport into dashboard (Phase UX-0)"
```

---

### Task 3: 4 missing `loading.tsx` skeletons

**Files:**
- Create: `frontend/src/app/(dashboard)/alpha/loading.tsx`
- Create: `frontend/src/app/(dashboard)/backtest/loading.tsx`
- Create: `frontend/src/app/(dashboard)/factor-lab/loading.tsx`
- Create: `frontend/src/app/(dashboard)/evolution/loading.tsx`

Each is an `animate-pulse` skeleton matching the layout shape of the real page. NOT a generic spinner; the skeleton's block heights/widths should mimic where the real content lands so the page transition feels stable, not jumpy.

- [ ] **Step 1: READ the canonical precedent**

```bash
cat "frontend/src/app/(dashboard)/picks/loading.tsx"
```
Note the structure: top-level container, repeated rectangular blocks with `animate-pulse bg-tm-card rounded` etc. Mirror this style.

- [ ] **Step 2: Build each loading.tsx**

For each page, look at its real `page.tsx` structure (top-level sections + their approximate heights) and emit a skeleton with the same shape. Skeletons are pure presentational, no state, no fetch.

Reference shapes (adapt heights/columns to match the real page when you read it):

**/alpha** — header (h-8) + textarea (h-32) + 3 cards row (h-24 each) + result panes (5x h-32). Real page has many panes; for the skeleton, render 4 placeholder panes (h-32 each) below the textarea area. The skeleton implies that results appear after submission.

**/backtest** — header (h-8) + form panel (h-48 with 4 input rows of h-8) + chart placeholder (h-64) + metrics row (h-24).

**/factor-lab** — header (h-8) + current expression pre (h-12) + diagnostic block (h-16) + propose button area (h-10) + pending table placeholder (h-32) + history table placeholder (h-32).

**/evolution** — header (h-8) + 5 TmPane placeholders (h-48 each, stacked).

Skeleton template:
```tsx
export default function Loading() {
  return (
    <main className="flex flex-col gap-4 p-6">
      <div className="h-8 w-48 animate-pulse rounded bg-tm-card" />
      <div className="h-32 w-full animate-pulse rounded bg-tm-card" />
      <div className="h-24 w-full animate-pulse rounded bg-tm-card" />
      <div className="h-32 w-full animate-pulse rounded bg-tm-card" />
      <div className="h-32 w-full animate-pulse rounded bg-tm-card" />
    </main>
  );
}
```
Adjust block dimensions per page so the skeleton's silhouette resembles the real layout (e.g. /backtest has a left form column + right results column on wide screens; the skeleton should mirror that grid).

- [ ] **Step 3: Visual sanity**

After implementing, run `npm run dev` and navigate to each page; observe the skeleton flash during initial fetch. If a skeleton's shape is wildly different from the real page (e.g. real page has 6 panes, skeleton has 2), the page transition will jump visibly — adjust block sizes accordingly.

- [ ] **Step 4: tsc + build clean**

```bash
cd frontend && npx tsc --noEmit && npm run build
```
All 4 new routes must build; the `/picks` prerender ECONNREFUSED is acceptable.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/app/(dashboard)/alpha/loading.tsx" "frontend/src/app/(dashboard)/backtest/loading.tsx" "frontend/src/app/(dashboard)/factor-lab/loading.tsx" "frontend/src/app/(dashboard)/evolution/loading.tsx"
git commit -m "feat(ui): loading.tsx skeletons for alpha/backtest/factor-lab/evolution (Phase UX-0)"
```

---

### Task 4: deploy + smoke

- [ ] **Step 1: push**

```bash
git push
```

- [ ] **Step 2: Smoke each route**

In a browser session (Vercel frontend URL), navigate from one page to another and observe:
- /alpha → loading skeleton appears <100ms after click, before real content lands
- /backtest → same
- /factor-lab → same
- /evolution → same
- Trigger ANY existing action (e.g. /factor-lab Propose) and confirm no Toast crash — the layout integration is non-breaking even though no page is wired to `useToast` yet.

- [ ] **Step 3: Optional integration spot-check**

Pick ONE existing page mutation (e.g. /factor-lab Approve) and convert ONE error path to `toast.error(...)` as a smoke. This is not required for Phase UX-0 completion; it's a useful integration verification.

---

## Self-Review

**Spec coverage:**
- Toast subsystem (T1+T2): provider, hook, component, viewport, layout wire. API matches sonner conventions.
- 4 loading.tsx skeletons (T3) covering all 4 dashboard pages missing them.
- Deploy + smoke (T4).

**Anti-pattern guardrails:**
- Silent exception: `useToast` throws if called outside `<ToastProvider>` (caller MUST be inside the dashboard layout; throwing surfaces the wiring mistake immediately).
- Dual-entry: NOT relevant for this phase (no backend changes, no API routes).
- Architectural debt: error toasts default to `duration=0` (sticky) so users have time to read; success/info auto-dismiss.

**5 UX principles re-checked:**
- Visibility (3): every page now has a loading skeleton; every page can call `toast.success/error/info` for mutation feedback.
- Forgiveness (4): error toast supports `action: { label, onClick }` for one-click recovery; sticky-by-default error means errors do not slip past unread.
- Affordance (5): toast kind maps to color + icon (success green/Check, error red/Alert, info gray/Info); visual signals what kind of feedback this is.
- Disappears (6): toasts auto-dismiss; no permanent inline error blobs cluttering panes after they have been read.
- Time-respect (8): loading.tsx eliminates blank-page period during RSC fetch (<100ms to skeleton).

**Out of scope (deferred):**
- Migrating each existing page's inline error state to `useToast`. This happens DURING each page's redesign in the page-by-page methodology the user chose.
- Toast positioning customization (top vs bottom, left vs right). Default is bottom-right; can be revisited per-page if needed.
- Action button styling for toast: kept minimal; a richer "Retry/Undo" pattern can be added when first consumer needs it.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-phase-ux-0-architecture.md`.

**1. Subagent-Driven (recommended)** — fresh subagent per task with two-stage review, consistent with prior phases.

**2. Inline Execution** — same-session batched execution.

Pick approach to proceed.
