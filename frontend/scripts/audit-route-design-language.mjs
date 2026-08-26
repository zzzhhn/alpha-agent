import fs from "node:fs";
import path from "node:path";

const SRC = path.resolve("src");
const DASHBOARD = path.join(SRC, "app/(dashboard)");
const EXTENSIONS = [".tsx", ".ts", ".jsx", ".js"];

function filesUnder(directory, output = []) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) filesUnder(target, output);
    else if (EXTENSIONS.includes(path.extname(entry.name)) && !entry.name.match(/\.(test|spec)\./)) output.push(target);
  }
  return output;
}

function resolveImport(fromFile, specifier) {
  let base;
  if (specifier.startsWith("@/")) base = path.join(SRC, specifier.slice(2));
  else if (specifier.startsWith(".")) base = path.resolve(path.dirname(fromFile), specifier);
  else return null;
  for (const candidate of [base, ...EXTENSIONS.map((extension) => `${base}${extension}`), ...EXTENSIONS.map((extension) => path.join(base, `index${extension}`))]) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
  }
  return null;
}

function dependencies(entry) {
  const visited = new Set();
  const queue = [entry];
  while (queue.length) {
    const file = queue.shift();
    if (!file || visited.has(file)) continue;
    visited.add(file);
    const source = fs.readFileSync(file, "utf8");
    for (const match of source.matchAll(/(?:from\s+|import\s*\()?["']([^"']+)["']/g)) {
      const target = resolveImport(file, match[1]);
      if (target && !visited.has(target)) queue.push(target);
    }
  }
  return visited;
}

const rawColorPattern = /\b(?:text|bg|border|ring|outline|from|via|to)-(?:red|green|emerald|amber|yellow|orange|blue|sky|cyan|teal|lime|purple|violet|pink|rose|zinc|gray|slate|neutral|stone)-(?:\d{2,3})(?:\/\d{1,3})?\b/g;
const legacyTokenPattern = /var\(--(?:background|foreground|border|muted|card-bg|muted-foreground|accent|destructive)\)/g;
const legacyUtilityPattern = /\b(?:text|bg|border|ring)-(?:text|muted|card|card-inner|border|green|red|yellow|accent|background|foreground)\b/g;
const consumerGeometryPattern = /\b(?:rounded-(?:md|lg|xl|2xl|3xl)|backdrop-blur(?:-\w+)?)\b/g;

const pages = filesUnder(DASHBOARD).filter((file) => path.basename(file) === "page.tsx").sort();
const routeReports = [];
const allViolations = new Map();

for (const page of pages) {
  const route = `/${path.relative(DASHBOARD, path.dirname(page)).split(path.sep).filter((part) => !part.startsWith("(")).join("/")}`;
  const graph = dependencies(page);
  const report = {
    route,
    screen: false,
    header: false,
    subbar: false,
    state: false,
    violations: [],
  };
  for (const file of graph) {
    const source = fs.readFileSync(file, "utf8");
    report.screen ||= /\bTmScreen\b/.test(source);
    report.header ||= /\bWorkbenchHeader\b/.test(source);
    report.subbar ||= /\bTmSubbar\b/.test(source);
    report.state ||= /\bTmStatePane\b/.test(source);
    const findings = [
      ...[...source.matchAll(rawColorPattern)].map((match) => `raw-color:${match[0]}`),
      ...[...source.matchAll(legacyTokenPattern)].map((match) => `legacy-token:${match[0]}`),
      ...[...source.matchAll(legacyUtilityPattern)].map((match) => `legacy-utility:${match[0]}`),
      ...[...source.matchAll(consumerGeometryPattern)].map((match) => `consumer-geometry:${match[0]}`),
      ...(source.includes('from "@/components/ui/Card"') || source.includes("from '@/components/ui/Card'") ? ["legacy-card:ui/Card"] : []),
      ...(/className\s*=\s*["'][^"']*\bglass-card\b/.test(source) ? ["legacy-card:glass-card"] : []),
    ];
    if (!findings.length) continue;
    const relative = path.relative(SRC, file).split(path.sep).join("/");
    for (const finding of [...new Set(findings)]) {
      const key = `${relative} · ${finding}`;
      allViolations.set(key, (allViolations.get(key) ?? new Set()).add(route));
      report.violations.push(key);
    }
  }
  routeReports.push(report);
}

console.log("ROUTE.DESIGN.LANGUAGE.INVENTORY");
for (const report of routeReports) {
  console.log(`${report.route.padEnd(18)} screen=${report.screen ? "yes" : "NO "} header=${report.header ? "yes" : "no "} subbar=${report.subbar ? "yes" : "no "} state=${report.state ? "yes" : "no "} findings=${new Set(report.violations).size}`);
}
console.log(`\nUNIQUE FINDINGS ${allViolations.size}`);
for (const [finding, routes] of [...allViolations].sort(([a], [b]) => a.localeCompare(b))) {
  console.log(`${finding} · routes=${[...routes].sort().join(",")}`);
}

const missingShells = routeReports.filter((report) => !report.screen || !report.header);
if (missingShells.length || allViolations.size) {
  for (const report of missingShells) {
    console.error(`missing route shell · ${report.route} · TmScreen=${report.screen} · WorkbenchHeader=${report.header}`);
  }
  process.exitCode = 1;
}
