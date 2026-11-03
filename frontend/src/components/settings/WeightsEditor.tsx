"use client";

import { useEffect, useState } from "react";
import { TmButton } from "@/components/tm/TmButton";
import { TmTextarea } from "@/components/tm/TmField";
import { useLocale } from "@/components/layout/LocaleProvider";
import { DEFAULT_WEIGHTS, WEIGHTS_KEY } from "@/lib/weights-override";

// Single source of truth: the canonical default + storage key live in
// weights-override.ts so the editor and the client reweight engine never
// drift. Includes supply_chain (serenity seam #2) + the display-only signals.
const KEY = WEIGHTS_KEY;

const DEFAULT_JSON = JSON.stringify(DEFAULT_WEIGHTS, null, 2);

export default function WeightsEditor() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [text, setText] = useState(DEFAULT_JSON);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem(KEY);
    if (stored) setText(stored);
  }, []);

  function handleSave() {
    try {
      const parsed: unknown = JSON.parse(text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setError(zh ? "请输入由信号名和权重组成的 JSON 对象。" : "Enter a JSON object mapping signals to weights.");
        return;
      }
      const values = Object.values(parsed);
      if (
        values.length === 0 ||
        !values.every((v) => typeof v === "number" && Number.isFinite(v))
      ) {
        setError(zh ? "请填写权重，所有权重都必须是有限数值。" : "Enter weights; all values must be finite numbers.");
        return;
      }
      if ((values as number[]).some((v) => v < 0)) {
        setError(zh ? "权重不能为负数。" : "Weights cannot be negative.");
        return;
      }
      // The composite renormalizes weights across surviving signals, so the
      // absolute sum is irrelevant — only the relative values matter. We just
      // need at least one positive weight so the normalizer has a denominator.
      const sum = (values as number[]).reduce((a, b) => a + b, 0);
      if (sum <= 0) {
        setError(zh ? "至少一个权重必须大于 0。" : "At least one weight must be greater than 0.");
        return;
      }
      const prev = localStorage.getItem(KEY);
      localStorage.setItem(KEY, text);
      // The native storage event only fires in OTHER tabs; dispatch a synthetic
      // one so card components in THIS tab reweight live (mirrors useFactorMode).
      window.dispatchEvent(
        new StorageEvent("storage", { key: KEY, oldValue: prev, newValue: text }),
      );
      setError(null);
      setSavedAt(new Date().toLocaleTimeString(zh ? "zh-CN" : "en"));
    } catch (e) {
      setError(e instanceof SyntaxError
        ? (zh ? "JSON 格式有误，请检查引号、逗号和括号。" : "Invalid JSON. Check quotes, commas, and braces.")
        : (zh ? "未能保存本地权重。" : "Could not save local weights."));
    }
  }

  function handleReset() {
    setText(DEFAULT_JSON);
    setError(null);
    setSavedAt(null);
    // Clearing the stored override reverts every card to the backend-canonical
    // composite/rating (readWeightsOverride returns null when the key is gone).
    if (typeof window !== "undefined") {
      const prev = localStorage.getItem(KEY);
      if (prev !== null) {
        localStorage.removeItem(KEY);
        window.dispatchEvent(
          new StorageEvent("storage", { key: KEY, oldValue: prev, newValue: null }),
        );
      }
    }
  }

  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      <TmTextarea
        label={zh ? "信号权重（JSON）" : "Signal weights (JSON)"}
        hint={zh ? "仅保存在此浏览器。系统自动归一化，只比较权重的相对大小。" : "Stored in this browser. Weights are normalized automatically, so only relative values matter."}
        error={error ?? undefined}
        id="settings-weight-json"
        value={text}
        onChange={(next) => {
          setText(next);
          setError(null);
          setSavedAt(null);
        }}
        spellCheck={false}
        textareaClassName="h-52 min-h-0 resize-none p-2 text-xs"
      />
      <div className="flex flex-wrap items-center gap-2 border-t border-tm-rule pt-2">
        <TmButton variant="primary" onClick={handleSave}>{zh ? "保存权重" : "Save weights"}</TmButton>
        <TmButton variant="ghost" onClick={handleReset}>{zh ? "恢复默认" : "Restore defaults"}</TmButton>
        {savedAt ? (
          <span role="status" className="font-tm-mono text-xs text-tm-pos">{zh ? "已保存" : "Saved"} {savedAt}</span>
        ) : null}
      </div>
    </div>
  );
}
