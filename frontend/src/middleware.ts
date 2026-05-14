// Protected-route gate. /picks /stock /alerts stay public (spec B-tier);
// only /settings requires a session. Unauthenticated access redirects to
// /signin?callbackUrl=<original> so the user bounces straight back after
// the magic-link round-trip.
import { auth } from "@/auth";
import { NextResponse } from "next/server";

const PROTECTED_PREFIXES = ["/settings"];

export default auth((req) => {
  const { pathname } = req.nextUrl;
  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  if (isProtected && !req.auth) {
    const signinUrl = new URL("/signin", req.nextUrl.origin);
    signinUrl.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(signinUrl);
  }
  return NextResponse.next();
});

export const config = {
  // Run on app pages, skip Next internals + static assets + the auth API
  // itself (NextAuth handles its own routes).
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/auth).*)"],
};
