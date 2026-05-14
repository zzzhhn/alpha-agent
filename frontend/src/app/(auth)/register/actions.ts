// frontend/src/app/(auth)/register/actions.ts
"use server";
//
// Open registration: rate-limit -> zod validate -> duplicate-email check ->
// bcryptjs hash -> INSERT into users. Returns a structured result; the
// /register client page calls signIn("credentials", ...) on ok:true (the
// cleaner NextAuth v5 split: signIn belongs in a client component).
//
// This is the project's first "use server" file; D1 and D2 follow the same
// shape (a module-level pg Pool, zod parse, structured result return, no
// thrown errors crossing the action boundary).
import { Pool } from "pg";
import { z } from "zod";
import { hashPassword } from "@/lib/auth/password";
import { checkRateLimit } from "@/lib/auth/rate-limit";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

// password 8-32 chars; confirmPassword must match. The .refine runs after
// the field checks so a short password reports "invalid" without a confusing
// double error.
const registerSchema = z
  .object({
    email: z.string().email(),
    password: z.string().min(8).max(32),
    confirmPassword: z.string(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    path: ["confirmPassword"],
  });

export type RegisterError =
  | "invalid"
  | "rate_limited"
  | "email_taken"
  | "server_error";

export type RegisterResult =
  | { ok: true; email: string }
  | { ok: false; error: RegisterError };

export async function registerAction(formData: FormData): Promise<RegisterResult> {
  // Rate-limit FIRST so a flood is cheap to reject (keyed on email here:
  // no reliable client IP inside a Server Action without extra plumbing;
  // email keying still caps per-target abuse and pairs with zod limits).
  const emailRaw = String(formData.get("email") ?? "");
  const rate = await checkRateLimit("register", emailRaw || "unknown", pool);
  if (!rate.allowed) return { ok: false, error: "rate_limited" };

  const parsed = registerSchema.safeParse({
    email: emailRaw,
    password: String(formData.get("password") ?? ""),
    confirmPassword: String(formData.get("confirmPassword") ?? ""),
  });
  if (!parsed.success) return { ok: false, error: "invalid" };
  const { email, password } = parsed.data;

  try {
    const existing = await pool.query(`SELECT id FROM users WHERE email = $1`, [
      email,
    ]);
    if (existing.rows.length > 0) {
      return { ok: false, error: "email_taken" };
    }

    // Hash BEFORE the INSERT: the INSERT params carry a bcrypt hash, never
    // the plaintext.
    const passwordHash = await hashPassword(password);
    await pool.query(
      `INSERT INTO users (email, name, password_hash, created_at)
         VALUES ($1, $2, $3, now())`,
      [email, null, passwordHash],
    );
    return { ok: true, email };
  } catch {
    // Never let a DB error leak as a thrown exception across the action
    // boundary: return a generic structured error the page can render.
    return { ok: false, error: "server_error" };
  }
}
