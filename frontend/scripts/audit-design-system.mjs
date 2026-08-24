import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ROOT = path.resolve("src");
const CONTROL_TAGS = new Set(["button", "input", "select", "textarea"]);
const CONTROL_EXCEPTIONS = new Map([
  ["components/ui/SegmentedTabs.tsx", "canonical ARIA tab implementation"],
  ["components/ui/toast/Toast.tsx", "toast infrastructure controls"],
]);
const TABLE_EXCEPTIONS = new Map([
  ["components/backtest/TmMonthlyReturnsHeatmap.tsx", "semantic year-by-month heatmap matrix"],
]);
const NATIVE_TITLE_BUDGET = 35;

function collectFiles(directory, files = []) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) collectFiles(target, files);
    else if (entry.name.endsWith(".tsx") && !entry.name.match(/\.(test|spec)\.tsx$/)) files.push(target);
  }
  return files;
}

function relative(file) {
  return path.relative(ROOT, file).split(path.sep).join("/");
}

const rawControls = [];
const nativeTables = [];
const nativeTitles = [];

for (const file of collectFiles(ROOT)) {
  const rel = relative(file);
  const source = fs.readFileSync(file, "utf8");
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const canonicalInternal = rel.startsWith("components/tm/");

  function visit(node) {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(tree);
      const line = tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1;
      if (!canonicalInternal && CONTROL_TAGS.has(tag)) rawControls.push({ rel, line, tag });
      if (!canonicalInternal && tag === "table") nativeTables.push({ rel, line, tag });
      if (/^[a-z]/.test(tag)) {
        const title = node.attributes.properties.find(
          (property) => ts.isJsxAttribute(property) && property.name.getText(tree) === "title",
        );
        if (title) nativeTitles.push({ rel, line, tag });
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(tree);
}

const unexpectedControls = rawControls.filter(({ rel, tag }) => {
  const reason = CONTROL_EXCEPTIONS.get(rel);
  if (!reason) return true;
  return rel !== "components/ui/SegmentedTabs.tsx"
    && rel !== "components/ui/toast/Toast.tsx";
});
const unexpectedTables = nativeTables.filter(({ rel }) => !TABLE_EXCEPTIONS.has(rel));

console.log("DESIGN.SYSTEM.AUDIT");
console.log(`raw controls: ${rawControls.length} total, ${unexpectedControls.length} unexpected`);
console.log(`native tables: ${nativeTables.length} total, ${unexpectedTables.length} unexpected`);
console.log(`native title attributes: ${nativeTitles.length}/${NATIVE_TITLE_BUDGET} compatibility budget`);

for (const [file, reason] of CONTROL_EXCEPTIONS) console.log(`allowed control · ${file} · ${reason}`);
for (const [file, reason] of TABLE_EXCEPTIONS) console.log(`allowed table · ${file} · ${reason}`);

for (const item of unexpectedControls) console.error(`unexpected <${item.tag}> · ${item.rel}:${item.line}`);
for (const item of unexpectedTables) console.error(`unexpected <table> · ${item.rel}:${item.line}`);

if (nativeTitles.length > NATIVE_TITLE_BUDGET) {
  console.error(`native title budget exceeded by ${nativeTitles.length - NATIVE_TITLE_BUDGET}`);
}

if (unexpectedControls.length || unexpectedTables.length || nativeTitles.length > NATIVE_TITLE_BUDGET) {
  process.exitCode = 1;
}
