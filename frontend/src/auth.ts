// frontend/src/auth.ts
//
// Full NextAuth.js v5 config for the Node runtime (route handler, server
// components). Spreads the edge-safe authConfig and adds the Node-only
// pieces: the Postgres adapter and the Nodemailer (Resend SMTP) provider.
// The middleware uses auth.config.ts directly so pg/nodemailer never
// reach the Edge bundle.
import NextAuth from "next-auth";
import Nodemailer from "next-auth/providers/nodemailer";
import PostgresAdapter from "@auth/pg-adapter";
import { Pool } from "pg";
import { authConfig } from "./auth.config";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
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
});
