// Mounts all NextAuth.js v5 endpoints: signin, callback, signout, session, csrf.
import { handlers } from "@/auth";

export const { GET, POST } = handlers;
