// frontend/src/lib/auth/password.ts
//
// Node-only bcryptjs wrapper. The single place the app hashes or verifies
// a secret (user passwords AND 6-digit reset codes). bcryptjs is pure JS
// (not native bcrypt/argon2) per the spec's edge-runtime-safety decision.
//
// IMPORT-GRAPH RULE: this module is Node-only. It must NEVER be imported by
// auth.config.ts or middleware.ts (both edge-reachable). It is imported only
// by the Credentials authorize() callback in auth.ts (Node route handler)
// and by the "use server" Server Actions.
import bcrypt from "bcryptjs";

// Cost factor 12: the spec's chosen work factor for both passwords and codes.
const BCRYPT_COST = 12;

/** Hash a plaintext secret (password or reset code) with bcryptjs cost 12. */
export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, BCRYPT_COST);
}

/** Verify a plaintext secret against a bcryptjs hash. Returns false on mismatch
 *  (never throws on a wrong password, a thrown error would be a different
 *  signal the caller must not have to distinguish). */
export async function verifyPassword(
  plain: string,
  hash: string,
): Promise<boolean> {
  return bcrypt.compare(plain, hash);
}
