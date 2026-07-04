import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

// CONTENT-based frontend version. Previously this was VERCEL_GIT_COMMIT_SHA,
// which changes on EVERY repo commit — so backend/workflow/mining commits (which
// don't touch the frontend) still triggered a frontend rebuild with a new SHA,
// and VersionWatcher nagged "page updated, refresh" even though the bundle was
// byte-identical. Hashing the actual frontend source means the version only
// changes when the FRONTEND changes; a rebuild from an unrelated commit yields
// the same hash → no spurious refresh prompt.
function hashFrontendSource() {
  const roots = ["src", "package.json", "next.config.mjs", "api-types.gen.ts"];
  const h = createHash("sha256");
  const walk = (p) => {
    let st;
    try {
      st = statSync(p);
    } catch {
      return; // missing path (e.g. api-types.gen.ts locally) — skip
    }
    if (st.isDirectory()) {
      for (const name of readdirSync(p).sort()) walk(join(p, name));
    } else {
      h.update(p);
      h.update(readFileSync(p));
    }
  };
  for (const r of roots) walk(r);
  return h.digest("hex").slice(0, 16);
}

// "dev" locally (no VERCEL env) so localhost never prompts; a stable content
// hash on Vercel. Both the baked client id and the runtime /api/fe/version read
// this same value, so they only diverge when the frontend content differs.
const FE_VERSION = process.env.VERCEL ? hashFrontendSource() : "dev";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Bake the frontend content hash into the client bundle so VersionWatcher can
  // compare the loaded version against the live one (/api/fe/version) and prompt
  // a refresh only when the FRONTEND actually shipped a new version.
  env: {
    NEXT_PUBLIC_BUILD_ID: FE_VERSION,
    FE_VERSION,
  },

  // Rewrite API calls to the AutoDL FastAPI backend
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:6008";
    return [
      {
        // Exclude /api/auth/* and /api/fe/* from this rewrite. /api/auth/* is
        // NextAuth's own routes; /api/fe/* is frontend-native API (e.g.
        // /api/fe/version for the deploy-version check). Both are handled by
        // Next route handlers under src/app/api/. All other /api/* paths proxy
        // to the FastAPI backend as before.
        source: "/api/:path((?!auth/|fe/).*)",
        destination: `${apiUrl}/api/:path`,
      },
      {
        source: "/ws/:path*",
        destination: `${apiUrl}/ws/:path*`,
      },
    ];
  },

  // Route / to the primary research dashboard. Config-level redirect emits
  // a proper HTTP 308 with Location header (vs. App-Router redirect() which
  // in some deploy modes returned a 307 without Location and landed clients
  // on the error boundary).
  async redirects() {
    return [
      {
        source: "/",
        destination: "/data",
        permanent: true,
      },
      // Module consolidation (2026-06-20): /factor-lab merged into /evolution
      // (both surfaced methodology proposals); /signal merged into /report
      // (report already renders signal's components). Preserve deep links.
      {
        source: "/factor-lab",
        destination: "/evolution",
        permanent: true,
      },
      {
        source: "/signal",
        destination: "/report",
        permanent: true,
      },
    ];
  },

  // Output standalone for smaller deployments
  output: "standalone",
};

export default nextConfig;
