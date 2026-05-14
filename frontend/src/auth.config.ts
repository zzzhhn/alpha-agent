// frontend/src/auth.config.ts
//
// Edge-safe NextAuth.js v5 config. This is the subset of the config that
// is safe to run in the Edge runtime (middleware): callbacks, pages,
// session strategy. NO database adapter and NO providers here, because
// @auth/pg-adapter (pg) and the Nodemailer provider are Node.js-only and
// would crash the Edge middleware. The full config (auth.ts) spreads this
// and adds the adapter + providers for the Node route handler.
import type { NextAuthConfig } from "next-auth";

export const authConfig: NextAuthConfig = {
  providers: [],
  session: { strategy: "jwt" },
  callbacks: {
    jwt: async ({ token, user }) => {
      // user is only present on initial sign-in; persist its id into sub.
      if (user?.id) token.sub = String(user.id);
      return token;
    },
    session: async ({ session, token }) => {
      if (token.sub && session.user) {
        (session.user as { id?: string }).id = token.sub;
      }
      return session;
    },
  },
  pages: {
    signIn: "/signin",
    verifyRequest: "/signin/check-email",
    error: "/signin/error",
  },
};
