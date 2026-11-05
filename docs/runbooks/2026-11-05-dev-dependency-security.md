# Development dependency security follow-up

## Scope and current audit

This follows PR #72 without changing application code, production dependency
versions, environment variables, database records, or BYOK credentials.

The previous report recorded 24 development dependency findings. On 2026-11-05,
the unchanged PR #72 lockfile returned 12 affected packages (10 moderate, 2 high)
from the current npm advisory service. These counts include dependency-chain
propagation and are not counts of distinct exploitable application bugs.
After the updates below, the full audit and production-only audit both report
zero findings. No advisory exclusions, forced audit fixes, or downgraded packages
are used.

## Bounded changes

| Chain | Change | Compatibility boundary |
| --- | --- | --- |
| Vitest / mocker | 4.1.6 to 4.1.12 | Same release series; do not move to Vitest 5 |
| Vite | 8.2.2 to 8.3.6 | Same major, used by the test tooling, not the Next production server |
| TypeScript ESLint packages | 8.58.1 to 8.72.1 | Same major; ESLint stays at 8.57.1 and Next config stays at 15.5.28 |
| brace-expansion | 1.1.18 to 1.1.21; 5.0.9 to 5.0.12 | Retain each consumer's existing major API |
| postcss-selector-parser | 6.0.10 / 6.1.4 to 6.1.5 | Same major; narrowly override Typography's exact old pin |
| minimatch inside typescript-estree | 10.2.5 to 11.0.1 | The only major exception, scoped to this one consumer |

The Vite/Vitest updates also refresh their matching internal packages and
Rolldown platform bindings. The lockfile comparison shows no production package
version changes. Next.js, React, NextAuth and BYOK code remain unchanged.

### Why the minimatch exception is safe for this caller

The published fix is in 11.0.1; the current typescript-estree release still requests
v10. Its only runtime use is the named `minimatch(filePath, pattern, { dot: true })`
function in the project-service allowlist. It does not use the `makeRe`, AST or
other APIs removed in v11. The override is scoped to typescript-estree: ESLint and
its plugins retain minimatch v3's callable export and `makeRe` API.

`npm run check:toolchain` exercises that named matcher, ESLint's legacy matcher,
and real Tailwind Typography CSS generation. It runs before every production
build, including Vercel previews. Remove the scoped override when the upstream
parser supports a patched minimatch version directly, after the same checks pass.

## Verification and release

- Clean `npm ci` installs the committed lockfile without peer-dependency errors.
- Full `npm audit` and `npm audit --omit=dev`: zero findings.
- Existing frontend suite: 33 files, 185 tests passed with one worker.
- Next.js 15.5.28 production build, lint/type checks, and all 23 static pages
  passed. Design-system checks report zero violations. The existing
  RecentRunsTable hook and jose Edge compression warnings are unchanged.
- Toolchain checks cover dotfiles, braces, nonmatching paths, legacy matcher API,
  and generated prose heading/body styles.
- Preview and production health, and before/after authenticated
  BYOK metadata comparison are release gates. Their final receipts belong in the
  pull request; do not infer deployment from this document alone.
- No saved-key mutation, model connection test, paid inference, bot, mining,
  research or trade run is needed for this dependency-only patch.

ESLint 8 and some of its transitive packages still emit end-of-support/deprecation
notices. Those notices are distinct from today's vulnerability audit. Migrating
to a new lint configuration format is deliberately not bundled into this patch.
Vite also emits a future native-config-loader notice for the existing Vitest
configuration; the current test runner works without suppressing that notice.

## Upstream evidence

- [Vitest mock registration fix](https://github.com/vitest-dev/vitest/security/advisories/GHSA-qxg6-89mg-rqv8)
- [Vite middleware fix](https://github.com/vitejs/vite/security/advisories/GHSA-9jrq-w75r-8gcw)
- [minimatch advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249)
- [minimatch 11 API changes](https://github.com/isaacs/minimatch/blob/v11.0.1/changelog.md)
- [Selector parser fix](https://github.com/postcss/postcss-selector-parser/security/advisories/GHSA-rj75-hqrm-r3gf)
