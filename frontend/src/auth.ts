// frontend/src/auth.ts
//
// NextAuth.js v5 config. Email magic-link provider via Resend SMTP,
// Postgres adapter (raw SQL, no ORM), JWT session strategy. The jwt
// callback stamps the DB user id into token.sub so the FastAPI backend
// can read it from the same NEXTAUTH_SECRET-signed token.
import NextAuth from "next-auth";
import Nodemailer from "next-auth/providers/nodemailer";
import PostgresAdapter from "@auth/pg-adapter";
import { Pool } from "pg";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PostgresAdapter(pool),
  providers: [
    Nodemailer({
      server: {
        host: "smtp.resend.com",
        port: 465,
        auth: { user: "resend", pass: process.env.RESEND_API_KEY! },
      },
      from: process.env.EMAIL_FROM!,
      maxAge: 24 * 60 * 60, // magic links valid 24h
    }),
  ],
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
});
