// frontend/src/app/(auth)/forgot-password/actions.ts
"use server";
//
// Step 1 of self-serve password reset. Rate-limit -> zod -> generate a
// random 6-digit code -> store the HASHED code (15-min TTL) -> email the
// PLAINTEXT code via Resend SMTP. ALWAYS returns the same ok:true response
// regardless of whether the email belongs to a real user (no enumeration).
import { randomInt } from "crypto";
import { Pool } from "pg";
import { z } from "zod";
import nodemailer from "nodemailer";
import { hashPassword } from "@/lib/auth/password";
import { checkRateLimit } from "@/lib/auth/rate-limit";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

const forgotSchema = z.object({ email: z.string().email() });

// Resend SMTP transport. nodemailer is already an installed dependency.
const mailer = nodemailer.createTransport({
  host: "smtp.resend.com",
  port: 465,
  auth: { user: "resend", pass: process.env.RESEND_API_KEY! },
});

const CODE_TTL_MINUTES = 15;

export type ForgotError = "invalid" | "rate_limited";
export type ForgotResult = { ok: true } | { ok: false; error: ForgotError };

/** Generate a zero-padded random 6-digit code (000000-999999 range). */
function generateCode(): string {
  return String(randomInt(0, 1_000_000)).padStart(6, "0");
}

export async function forgotPasswordAction(
  formData: FormData,
): Promise<ForgotResult> {
  const emailRaw = String(formData.get("email") ?? "");

  const rate = await checkRateLimit("reset_request", emailRaw || "unknown", pool);
  if (!rate.allowed) return { ok: false, error: "rate_limited" };

  const parsed = forgotSchema.safeParse({ email: emailRaw });
  if (!parsed.success) return { ok: false, error: "invalid" };
  const { email } = parsed.data;

  // Look up the user but DO NOT branch the response on it: the row
  // insert + email send happen either way so the response is identical.
  // A non-existent email still gets a code row; harmless, never consumed.
  await pool.query(`SELECT id FROM users WHERE email = $1`, [email]);

  const code = generateCode();
  const codeHash = await hashPassword(code);
  const expiresAt = new Date(Date.now() + CODE_TTL_MINUTES * 60_000);

  await pool.query(
    `INSERT INTO password_reset_codes (email, code_hash, expires_at)
       VALUES ($1, $2, $3)`,
    [email, codeHash, expiresAt.toISOString()],
  );

  // Send the PLAINTEXT code. A delivery failure must not change the
  // response (still ok:true). The user is told to check their email.
  try {
    await mailer.sendMail({
      from: process.env.EMAIL_FROM!,
      to: email,
      subject: "Alpha Agent password reset code",
      text:
        `Your Alpha Agent password reset code is ${code}.\n` +
        `It expires in ${CODE_TTL_MINUTES} minutes. ` +
        `If you did not request this, you can ignore this email.`,
    });
  } catch {
    // Swallow: the response stays identical whether mail sent or not.
  }

  return { ok: true };
}
