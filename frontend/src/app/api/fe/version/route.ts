import { NextResponse } from "next/server";

// Frontend-native deploy-version endpoint. Returns the commit SHA of the
// deployment currently serving requests (VERCEL_GIT_COMMIT_SHA, a runtime
// system env on Vercel). A client loaded from an older deploy keeps the SHA
// baked into its bundle (NEXT_PUBLIC_BUILD_ID); when it polls here and sees a
// different SHA, a new deploy is live → VersionWatcher prompts a refresh.
//
// Must NOT be cached — always reflect the live deployment.
export const dynamic = "force-dynamic";

export function GET() {
  const version = process.env.VERCEL_GIT_COMMIT_SHA || "dev";
  return NextResponse.json(
    { version },
    { headers: { "Cache-Control": "no-store, max-age=0" } },
  );
}
