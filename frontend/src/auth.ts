// frontend/src/auth.ts
//
// NextAuth.js v5 config (Node route-handler context). Phase 4b: two login
// methods, email+password via the Credentials provider, and Google OAuth.
// The Nodemailer magic-link provider is REMOVED (magic-link login is gone;
// Resend stays only as the SMTP transport the password-reset Server Action
// calls directly, not via a NextAuth provider).
//
// auth.config.ts and middleware.ts are NOT modified by Phase 4b. The
// Credentials authorize() callback and the Google OAuth callback each
// return a user object whose id flows into token.sub via the existing
// jwt callback in auth.config.ts. The middleware decrypts the same session
// JWE and re-mints the HS256 JWS exactly as before.
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import PostgresAdapter from "@auth/pg-adapter";
import { Pool } from "pg";
import { z } from "zod";
import { authConfig } from "./auth.config";
import { verifyPassword } from "./lib/auth/password";

// Reused by BOTH the pg-adapter (linkAccount / getUserByAccount for Google)
// and the Credentials authorize() callback's user lookup.
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

// authorize() input contract. Parsing here means a malformed submission
// returns null (generic failure) instead of throwing.
const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  adapter: PostgresAdapter(pool),
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      // Runs only in the Node /api/auth/[...nextauth] route handler, never
      // in middleware/edge. Returns null on ANY failure, no message that
      // distinguishes "unknown email" from "wrong password" (no user
      // enumeration). NextAuth surfaces a generic CredentialsSignin error.
      authorize: async (raw) => {
        const parsed = credentialsSchema.safeParse(raw);
        if (!parsed.success) return null;
        const { email, password } = parsed.data;

        const result = await pool.query(
          `SELECT id, email, name, password_hash
             FROM users
            WHERE email = $1`,
          [email],
        );
        const row = result.rows[0];
        // No such user, or a Google-only user with no password set.
        if (!row || !row.password_hash) return null;

        const ok = await verifyPassword(password, row.password_hash);
        if (!ok) return null;

        // The id flows into token.sub via auth.config.ts's jwt callback.
        return {
          id: String(row.id),
          email: row.email as string,
          name: (row.name as string | null) ?? null,
        };
      },
    }),
    // allowDangerousEmailAccountLinking: a Google sign-in proves email
    // ownership, so auto-linking to an existing same-email password account
    // is acceptable (and the no-linking alternative, orphaned duplicate
    // accounts, is strictly worse with open, unverified registration).
    // AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET are auto-detected from env by
    // Auth.js v5, so Google needs no explicit args here.
    Google({ allowDangerousEmailAccountLinking: true }),
  ],
});
