// frontend/src/middleware.ts
//
// Protected-route gate. Runs on the Edge runtime, so it builds its auth
// instance from the edge-safe auth.config.ts (NO pg adapter, NO
// nodemailer). /picks /stock /alerts stay public; /settings and /alpha
// require a session. Unauthenticated access redirects to
// /signin?callbackUrl=<original>.
import NextAuth from "next-auth";
import { NextResponse } from "next/server";
import { authConfig } from "@/auth.config";

const { auth } = NextAuth(authConfig);

const PROTECTED_PREFIXES = ["/settings", "/alpha"];

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
