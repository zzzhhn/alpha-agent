import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const root = path.resolve("src");
const violations = [];
const css = fs.readFileSync(path.join(root, "app/globals.css"), "utf8");
const foundations = fs.readFileSync(path.join(root, "components/reference/ReferenceFoundations.tsx"), "utf8");
const tokens = new Set([...css.matchAll(/(--tm-[\w-]+)\s*:/g)].map((m) => m[1]));
for (const token of tokens) {
  if (!foundations.includes(token)) violations.push(`Token missing from reference: ${token}`);
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__tests__") continue;
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) { walk(file); continue; }
    if (file.endsWith(".css") && file !== path.join(root, "app/globals.css")) {
      const source = fs.readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
      if (/(?:#[\da-fA-F]{6}\b|(?:rgba?|hsla?)\(\s*\d)/.test(source)) {
        violations.push(`${path.relative(root, file)}: Literal CSS color outside semantic tokens`);
      }
      continue;
    }
    if (!/\.(ts|tsx)$/.test(file) || /\.(test|spec)\./.test(file)) continue;
    const rel = path.relative(root, file);
    const source = fs.readFileSync(file, "utf8");
    const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
    const add = (node, reason) => violations.push(`${rel}:${tree.getLineAndCharacterOfPosition(node.getStart()).line + 1}: ${reason}`);
    function visit(node) {
      if (ts.isStringLiteralLike(node) || ts.isTemplateExpression(node)) {
        const text = node.getText(tree);
        if (/(?:#[\da-fA-F]{6}\b|(?:rgba?|hsla?)\(\s*\d)/.test(text)) add(node, "Literal color outside semantic tokens");
        if (/text-tm-[\w-]+\/(?:[1-4]\d)\b/.test(text)) add(node, "Readable text faded below the semantic token");
        if (/\brounded-(?:lg|xl|2xl)\b/.test(text)) add(node, "Non-workstation container radius");
        if (/\bshadow-(?:sm|md|lg|xl|2xl)\b/.test(text)) add(node, "Shadow must use an elevation token");
        for (const match of text.matchAll(/text-\[([\d.]+)px\]/g)) {
          if (![12, 14, 16, 18, 24, 28].includes(Number(match[1]))) add(node, "Unregistered text size");
        }
        if (/\btext-(?:xl|[3-9]xl)\b/.test(text)) add(node, "Unregistered text scale alias");
      }
      if (ts.isJsxAttribute(node)) {
        const name = node.name.getText(tree);
        if (name === "fontSize" && ts.isJsxExpression(node.initializer) &&
            node.initializer.expression && ts.isNumericLiteral(node.initializer.expression) &&
            Number(node.initializer.expression.text) < 12) add(node, "SVG text below 12px");
        if (name === "role" && node.initializer?.getText(tree) === '"dialog"' &&
            !rel.startsWith("components/tm/")) add(node, "Dialog must use TmDialog/TmDrawer");
      }
      ts.forEachChild(node, visit);
    }
    visit(tree);
  }
}
walk(root);

const rgb = (value) => value.startsWith("#")
  ? value.slice(1).match(/../g).map((part) => Number.parseInt(part, 16))
  : value.match(/[\d.]+/g).map(Number);
const luminance = (channels) => channels.slice(0, 3).map((n) => {
  const c = n / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + 0.05) / (Math.min(luminance(a), luminance(b)) + 0.05);
let checkedPairs = 0;
for (const theme of ["dark", "light"]) {
  const block = [...css.matchAll(new RegExp(`\\[data-theme="${theme}"\\]\\s*\\{([^}]+)`, "g"))]
    .find((m) => m[1].includes("--tm-accent:"))[1];
  const values = Object.fromEntries([...block.matchAll(/(--tm-[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
  const bg = rgb(values["--tm-bg"]);
  for (const role of ["fg", "fg-2", "muted", "accent", "pos", "neg", "warn", "info"]) {
    const fg = rgb(values[`--tm-${role}`]);
    let backgrounds = [bg, rgb(values["--tm-bg-2"]), rgb(values["--tm-bg-3"])];
    const soft = values[`--tm-${role}-soft`];
    if (soft) {
      const rgba = rgb(soft);
      backgrounds.push(bg.map((c, i) => c * (1 - rgba[3]) + rgba[i] * rgba[3]));
    }
    for (const surface of backgrounds) {
      const ratio = contrast(fg, surface);
      checkedPairs++;
      if (ratio < 4.5) violations.push(`${theme} ${role} contrast ${ratio.toFixed(2)} < 4.5`);
    }
  }
}
console.log(`TOKEN.CONTRACT: ${tokens.size} tokens registered; ${checkedPairs} contrast pairs; ${violations.length} violations`);
for (const error of violations) console.error(error);
if (violations.length) process.exitCode = 1;
