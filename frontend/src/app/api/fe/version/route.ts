import { NextResponse } from "next/server";

// Frontend-native deploy-version endpoint. Returns FE_VERSION — a hash of the
// FRONTEND source, baked at build time (see next.config.mjs), NOT the git SHA.
// A client loaded from an older deploy keeps its FE_VERSION baked in
// (NEXT_PUBLIC_BUILD_ID); when it polls here and sees a different value, a new
// frontend version is live → VersionWatcher prompts a refresh. Because the
// value is content-based, an unrelated backend/workflow/mining commit that
// rebuilds the frontend without changing it yields the SAME hash → no prompt.
//
// Must NOT be cached — always reflect the live deployment.
export const dynamic = "force-dynamic";

export function GET() {
  const version = process.env.FE_VERSION || "dev";
  return NextResponse.json(
    { version },
    { headers: { "Cache-Control": "no-store, max-age=0" } },
  );
}
