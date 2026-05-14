// frontend/src/app/(auth)/reset-password/actions.ts
"use server";
//
// Step 2 of self-serve password reset. Takes {email, code, newPassword}:
// zod-validate -> look up the newest unused unexpired password_reset_codes
// row for the email -> verifyPassword(code, row.code_hash) -> on match,
// UPDATE users.password_hash + flip used=true. Distinct errors for
// wrong / expired / used so the user knows whether to re-request.
import { Pool } from "pg";
import { z } from "zod";
import { hashPassword, verifyPassword } from "@/lib/auth/password";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

const resetSchema = z.object({
  email: z.string().email(),
  code: z.string().regex(/^\d{6}$/),
  newPassword: z.string().min(8).max(32),
});

export type ResetError =
  | "invalid"
  | "wrong_code"
  | "expired_code"
  | "used_code"
  | "server_error";

export type ResetResult = { ok: true } | { ok: false; error: ResetError };

interface CodeRow {
  id: number;
  code_hash: string;
  expires_at: string;
  used: boolean;
}

export async function resetPasswordAction(
  formData: FormData,
): Promise<ResetResult> {
  const parsed = resetSchema.safeParse({
    email: String(formData.get("email") ?? ""),
    code: String(formData.get("code") ?? ""),
    newPassword: String(formData.get("newPassword") ?? ""),
  });
  if (!parsed.success) return { ok: false, error: "invalid" };
  const { email, code, newPassword } = parsed.data;

  try {
    // Newest unused unexpired code row for this email.
    const fresh = await pool.query(
      `SELECT id, code_hash, expires_at, used
         FROM password_reset_codes
        WHERE email = $1 AND used = false AND expires_at > now()
        ORDER BY created_at DESC
        LIMIT 1`,
      [email],
    );
    const freshRow = fresh.rows[0] as CodeRow | undefined;

    if (!freshRow) {
      // No fresh row. Distinguish "expired/used code that DID exist" from
      // "no code at all / wrong email" by a second lookup ignoring the
      // freshness filters.
      const any = await pool.query(
        `SELECT id, code_hash, expires_at, used
           FROM password_reset_codes
          WHERE email = $1
          ORDER BY created_at DESC
          LIMIT 1`,
        [email],
      );
      const anyRow = any.rows[0] as CodeRow | undefined;
      if (anyRow && (await verifyPassword(code, anyRow.code_hash))) {
        if (anyRow.used) return { ok: false, error: "used_code" };
        return { ok: false, error: "expired_code" };
      }
      return { ok: false, error: "wrong_code" };
    }

    // A fresh row exists, the supplied code must verify against its hash.
    const codeOk = await verifyPassword(code, freshRow.code_hash);
    if (!codeOk) return { ok: false, error: "wrong_code" };

    // Match. Hash the new password, update the user, single-use the code.
    const newHash = await hashPassword(newPassword);
    await pool.query(`UPDATE users SET password_hash = $1 WHERE email = $2`, [
      newHash,
      email,
    ]);
    await pool.query(
      `UPDATE password_reset_codes SET used = true WHERE id = $1`,
      [freshRow.id],
    );
    return { ok: true };
  } catch {
    return { ok: false, error: "server_error" };
  }
}
