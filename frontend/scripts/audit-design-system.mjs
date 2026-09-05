import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ROOT = path.resolve("src");
const CONTROL_TAGS = new Set(["button", "input", "select", "textarea"]);
const CONTROL_EXCEPTIONS = new Map([
  ["components/ui/SegmentedTabs.tsx", "canonical ARIA tab implementation"],
]);
const TABLE_EXCEPTIONS = new Map([
  ["components/backtest/TmMonthlyReturnsHeatmap.tsx", "semantic year-by-month heatmap matrix"],
]);
const NATIVE_TITLE_BUDGET = 36;

function collectFiles(directory, files = []) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) collectFiles(target, files);
    else if (entry.name.endsWith(".tsx") && !entry.name.match(/\.(test|spec)\.tsx$/)) files.push(target);
  }
  return files;
}

function collectCssFiles(directory, files = []) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) collectCssFiles(target, files);
    else if (entry.name.endsWith(".css")) files.push(target);
  }
  return files;
}

function relative(file) {
  return path.relative(ROOT, file).split(path.sep).join("/");
}

const rawControls = [];
const nativeTables = [];
const nativeTitles = [];
const undersizedType = [];
const rawReferenceTaxonomy = [];
const unlocalizedPaneTitles = [];
const productionIcons = new Set();
const referenceIcons = new Set();
const visualizationAssets = [];
const referenceVisualizationFile = path.join(ROOT, "components/reference/ReferenceVisualizations.tsx");
const referenceVisualizationSource = fs.readFileSync(referenceVisualizationFile, "utf8");
const referenceIconographySource = fs.readFileSync(path.join(ROOT, "components/reference/ReferenceIconography.tsx"), "utf8");
const referencePatternsSource = fs.readFileSync(path.join(ROOT, "components/reference/ReferencePatterns.tsx"), "utf8");
const tmPaneSource = fs.readFileSync(path.join(ROOT, "components/tm/TmPane.tsx"), "utf8");
const REQUIRED_TEXT_GLYPHS = ["▶", "▾", "▸", "·", "←", "→", "▲", "▼", "✓", "×", "⚠", "↗"];
const REQUIRED_MIGRATION_IDS = [
  "semantic-token-bridge",
  "typography-floor",
  "pane-title-localization",
  "button-family",
  "field-family",
  "exclusive-toggle",
  "pagination-family",
  "table-family",
  "state-feedback",
  "tooltip-family",
  "icon-registry",
  "visualization-registry",
  "source-only-visualizations",
  "overlay-family",
  "pane-card-family",
  "workbench-composition",
  "native-title-budget",
  "native-control-internals",
  "semantic-elevation",
  "heatmap-ramp",
  "service-health",
  "notification-view",
];
const INLINE_VISUALIZATION_KEYS = new Map([
  ["app/(dashboard)/factors/page.tsx", "app/factors inline Recharts"],
  ["app/(dashboard)/report/page.tsx", "app/report inline Recharts"],
]);

for (const file of collectFiles(ROOT)) {
  const rel = relative(file);
  const source = fs.readFileSync(file, "utf8");
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const canonicalInternal = rel.startsWith("components/tm/");
  const isIconReference = rel === "components/reference/ReferenceIconography.tsx";
  const isReference = rel.startsWith("components/reference/");

  for (const match of source.matchAll(/text-\[([\d.]+)px\]/g)) {
    if (Number(match[1]) < 12) undersizedType.push({ rel, token: match[0] });
  }
  for (const match of source.matchAll(/fontSize\s*:\s*([\d.]+)/g)) {
    if (Number(match[1]) < 12) undersizedType.push({ rel, token: match[0] });
  }
  for (const match of source.matchAll(/font-size\s*:\s*([\d.]+)px/g)) {
    if (Number(match[1]) < 12) undersizedType.push({ rel, token: match[0] });
  }
  if (isReference) {
    for (const match of source.matchAll(/<TmPane[^>]*title="([A-Z][A-Z0-9_. /+:-]+)"/g)) {
      rawReferenceTaxonomy.push({ rel, token: match[1] });
    }
  }
  if (rel !== "components/tm/TmPane.tsx") {
    for (const match of source.matchAll(/<TmPane[^>]*title="([A-Z][A-Z0-9_. /+:-]+)"/g)) {
      if (!tmPaneSource.includes(`"${match[1]}"`)) unlocalizedPaneTitles.push({ rel, token: match[1] });
    }
  }
  if (!isReference && (rel.startsWith("components/") || rel.startsWith("app/(dashboard)/")) && (
    source.includes('from "recharts"') || source.includes('import("recharts")') ||
    source.includes("<svg") || source.includes("lightweight-charts") || source.includes("chart.js")
  )) {
    visualizationAssets.push({ rel, key: INLINE_VISUALIZATION_KEYS.get(rel) ?? path.basename(rel, ".tsx") });
  }

  function visit(node) {
    if (ts.isImportDeclaration(node) && !node.importClause?.isTypeOnly && node.moduleSpecifier.getText(tree).replaceAll('"', "") === "lucide-react") {
      const imports = node.importClause?.namedBindings;
      if (imports && ts.isNamedImports(imports)) {
        for (const element of imports.elements) {
          if (element.isTypeOnly) continue;
          (isIconReference ? referenceIcons : productionIcons).add(element.propertyName?.text ?? element.name.text);
        }
      }
    }
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

for (const file of collectCssFiles(ROOT)) {
  const rel = relative(file);
  const source = fs.readFileSync(file, "utf8");
  for (const match of source.matchAll(/font-size\s*:\s*([\d.]+)px/g)) {
    if (Number(match[1]) < 12) undersizedType.push({ rel, token: match[0] });
  }
}

const unexpectedControls = rawControls.filter(({ rel, tag }) => {
  const reason = CONTROL_EXCEPTIONS.get(rel);
  if (!reason) return true;
  return rel !== "components/ui/SegmentedTabs.tsx";
});
const unexpectedTables = nativeTables.filter(({ rel }) => !TABLE_EXCEPTIONS.has(rel));
const missingIcons = [...productionIcons].filter((name) => !referenceIcons.has(name)).sort();
const extraReferenceIcons = [...referenceIcons].filter((name) => !productionIcons.has(name)).sort();
const missingVisualizations = visualizationAssets.filter(({ key }) => !referenceVisualizationSource.includes(key));
const missingTextGlyphs = REQUIRED_TEXT_GLYPHS.filter((glyph) => !referenceIconographySource.includes(`"${glyph}"`));
const missingMigrationItems = REQUIRED_MIGRATION_IDS.filter((id) => !referencePatternsSource.includes(`id: "${id}"`));

console.log("DESIGN.SYSTEM.AUDIT");
console.log(`raw controls: ${rawControls.length} total, ${unexpectedControls.length} unexpected`);
console.log(`native tables: ${nativeTables.length} total, ${unexpectedTables.length} unexpected`);
console.log(`native title attributes: ${nativeTitles.length}/${NATIVE_TITLE_BUDGET} compatibility budget`);
console.log(`undersized visible type: ${undersizedType.length}`);
console.log(`production icons: ${productionIcons.size}, reference icons: ${referenceIcons.size}, missing: ${missingIcons.length}`);
if (extraReferenceIcons.length) console.log(`reference-only icons: ${extraReferenceIcons.join(", ")}`);
console.log(`registered text glyph exceptions: ${REQUIRED_TEXT_GLYPHS.length - missingTextGlyphs.length}/${REQUIRED_TEXT_GLYPHS.length}`);
console.log(`visualization assets: ${visualizationAssets.length}, missing from reference registry: ${missingVisualizations.length}`);
console.log(`raw reference taxonomy headings: ${rawReferenceTaxonomy.length}`);
console.log(`unlocalized production pane titles: ${unlocalizedPaneTitles.length}`);
console.log(`migration ledger assets: ${REQUIRED_MIGRATION_IDS.length - missingMigrationItems.length}/${REQUIRED_MIGRATION_IDS.length}`);

for (const [file, reason] of CONTROL_EXCEPTIONS) console.log(`allowed control · ${file} · ${reason}`);
for (const [file, reason] of TABLE_EXCEPTIONS) console.log(`allowed table · ${file} · ${reason}`);

for (const item of unexpectedControls) console.error(`unexpected <${item.tag}> · ${item.rel}:${item.line}`);
for (const item of unexpectedTables) console.error(`unexpected <table> · ${item.rel}:${item.line}`);
for (const item of undersizedType) console.error(`undersized type · ${item.rel} · ${item.token}`);
for (const name of missingIcons) console.error(`icon missing from reference · ${name}`);
for (const glyph of missingTextGlyphs) console.error(`text glyph missing from reference · ${glyph}`);
for (const { rel } of missingVisualizations) console.error(`visualization missing from reference · ${rel}`);
for (const item of rawReferenceTaxonomy) console.error(`raw reference taxonomy · ${item.rel} · ${item.token}`);
for (const item of unlocalizedPaneTitles) console.error(`unlocalized pane title · ${item.rel} · ${item.token}`);
for (const id of missingMigrationItems) console.error(`migration asset missing from ledger · ${id}`);

if (nativeTitles.length > NATIVE_TITLE_BUDGET) {
  console.error(`native title budget exceeded by ${nativeTitles.length - NATIVE_TITLE_BUDGET}`);
}

if (
  unexpectedControls.length || unexpectedTables.length || nativeTitles.length > NATIVE_TITLE_BUDGET ||
  undersizedType.length || missingIcons.length || missingTextGlyphs.length || missingVisualizations.length || rawReferenceTaxonomy.length ||
  unlocalizedPaneTitles.length || missingMigrationItems.length
) {
  process.exitCode = 1;
}
