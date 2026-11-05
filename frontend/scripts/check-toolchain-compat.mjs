// Exercise the two narrowly scoped security overrides through their consumers.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import typography from "@tailwindcss/typography";

const require = createRequire(import.meta.url);
const parserRequire = createRequire(require.resolve("@typescript-eslint/typescript-estree"));
const { minimatch } = parserRequire("minimatch");

// typescript-estree only uses the named matcher with { dot: true } for
// allowDefaultProject. It does not use the makeRe/AST APIs removed in v11.
for (const [file, pattern, expected] of [
  ["config.ts", "*.ts", true],
  [".config.ts", "*.ts", true],
  ["src/component.tsx", "src/*.{ts,tsx}", true],
  ["src/deep/component.tsx", "src/*.tsx", false],
  ["config.js", "*.ts", false],
]) {
  assert.equal(minimatch(file, pattern, { dot: true }), expected);
}

// Do not accidentally replace ESLint's older callable API with the v11 API.
const eslintRequire = createRequire(require.resolve("eslint"));
const legacyMatcher = eslintRequire("minimatch");
assert.equal(legacyMatcher("component.tsx", "*.tsx"), true);
assert.equal(legacyMatcher.makeRe("*.tsx").test("component.tsx"), true);

// Typography pins an old selector parser. Its patched v6 override must still
// generate the existing prose styles instead of silently dropping the plugin.
const { css } = await postcss([
  tailwindcss({
    content: [{ raw: '<article class="prose"><h2>Research</h2><p>Evidence</p></article>', extension: "html" }],
    plugins: [typography],
  }),
]).process("@tailwind components;", { from: undefined });
assert.ok(css.includes(".prose"));
assert.ok(css.includes(":where(h2)"));
assert.ok(css.includes(":where(p)"));
assert.ok(css.includes("--tw-prose-body"));

console.log("Toolchain compatibility: parser matching, legacy ESLint API and typography CSS passed.");
