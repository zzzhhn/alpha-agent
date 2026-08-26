"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { explainAst } from "@/lib/api";
import type { AstNode } from "@/lib/types";
import { TmDisclosureButton } from "@/components/tm/TmButton";

interface ASTDrawerProps {
  readonly expression: string;
}

/** Lazy-loaded AST tree view. Mounts collapsed; first expansion fetches the
 *  tree from the backend so the drawer doesn't pay the round-trip until the
 *  user actually wants to look at it. */
export function ASTDrawer({ expression }: ASTDrawerProps) {
  const { locale } = useLocale();
  const [open, setOpen] = useState(false);
  const [tree, setTree] = useState<AstNode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Reset whenever the upstream expression changes — old tree would be stale.
  useEffect(() => {
    setTree(null);
    setError(null);
    setOpen(false);
  }, [expression]);

  async function load() {
    setLoading(true);
    setError(null);
    const res = await explainAst(expression);
    if (res.error || !res.data) {
      setError(res.error ?? "unknown error");
    } else {
      setTree(res.data.tree);
    }
    setLoading(false);
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && tree === null && !loading) {
      void load();
    }
  }

  return (
    <Card padding="md">
      <TmDisclosureButton
        expanded={open}
        onClick={toggle}
        label={t(locale, "alpha.ast.title")}
        className="h-auto border-0 bg-transparent px-0 font-sans text-base font-semibold tracking-normal text-text hover:border-transparent hover:bg-transparent hover:text-text"
      />

      {open && (
        <div className="mt-3">
          {loading && (
            <p className="text-[13px] text-muted">{t(locale, "common.loading")}</p>
          )}
          {error && (
            <p className="text-[13px] text-red">
              {t(locale, "alpha.ast.error")}: {error}
            </p>
          )}
          {tree && (
            <div className="font-mono text-[13px]">
              <ASTNode node={tree} depth={0} />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function ASTNode({ node, depth }: { readonly node: AstNode; readonly depth: number }) {
  const indent = depth * 16;

  if (node.type === "literal") {
    return (
      <div style={{ paddingLeft: indent }} className="py-0.5">
        <span className="text-yellow">{node.value}</span>
        <span className="ml-2 text-xs text-muted">literal</span>
      </div>
    );
  }

  if (node.type === "operand") {
    return (
      <div style={{ paddingLeft: indent }} className="py-0.5">
        <span className="text-green">{node.name}</span>
        <span className="ml-2 text-xs text-muted">operand</span>
      </div>
    );
  }

  return (
    <div className="py-0.5">
      <div style={{ paddingLeft: indent }}>
        <span className="text-accent">{node.name}</span>
        <span className="text-muted">(</span>
        <span className="ml-2 text-xs text-muted">
          operator · {node.args.length} arg{node.args.length === 1 ? "" : "s"}
        </span>
      </div>
      {node.args.map((child, idx) => (
        <ASTNode key={idx} node={child} depth={depth + 1} />
      ))}
      <div style={{ paddingLeft: indent }}>
        <span className="text-muted">)</span>
      </div>
    </div>
  );
}
