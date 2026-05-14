// frontend/src/middleware.ts
//
// Edge middleware: (1) page-redirect gating for protected routes, and
// (2) for /api/* requests, re-mints the NextAuth session into a
// short-lived HS256 JWT and injects it as Authorization: Bearer so the
// FastAPI backend (which verifies HS256 with the shared NEXTAUTH_SECRET)
// can authenticate the caller. NextAuth's own session cookie is a JWE,
// which the backend cannot verify directly; re-minting bridges that.
import NextAuth from "next-auth";
import { NextResponse } from "next/server";
import { SignJWT } from "jose";
import { authConfig } from "@/auth.config";

const { auth } = NextAuth(authConfig);

const PROTECTED_PREFIXES = ["/settings", "/alpha"];

export default auth(async (req) => {
  const { pathname } = req.nextUrl;

  // /api/* (except NextAuth's own /api/auth/*): inject a Bearer token the
  // FastAPI backend can verify. No session -> no header -> backend 401s,
  // and the api client redirects the user to /signin.
  if (pathname.startsWith("/api/") && !pathname.startsWith("/api/auth")) {
    const userId = (req.auth?.user as { id?: string } | undefined)?.id;
    if (userId) {
      const secret = process.env.NEXTAUTH_SECRET;
      if (secret) {
        const jws = await new SignJWT({ sub: String(userId) })
          .setProtectedHeader({ alg: "HS256" })
          .setIssuedAt()
          .setExpirationTime("5m")
          .sign(new TextEncoder().encode(secret));
        const headers = new Headers(req.headers);
        headers.set("Authorization", `Bearer ${jws}`);
        return NextResponse.next({ request: { headers } });
      }
    }
    return NextResponse.next();
  }

  // Page routes: redirect unauthenticated visitors away from protected
  // prefixes with a callbackUrl bounce-back.
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
