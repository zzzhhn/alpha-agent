// Node runtime only. Never import from middleware or client components.
import { Pool } from "pg";

const runtime = globalThis as typeof globalThis & { alphaAuthPool?: Pool };

function positiveInt(name: string, fallback: number): number {
  const value = Number(process.env[name]);
  return Number.isSafeInteger(value) && value > 0 ? value : fallback;
}

/** Reuse across auth/action modules in ONE process, not across serverless instances. */
export function getAuthPool(): Pool {
  if (!runtime.alphaAuthPool) {
    const pool = new Pool({
      connectionString: process.env.DATABASE_URL,
      max: positiveInt("AUTH_DB_POOL_MAX", 3),
      connectionTimeoutMillis: positiveInt("AUTH_DB_CONNECT_TIMEOUT_MS", 10_000),
      idleTimeoutMillis: 30_000,
      // Preserve server query settings: PgBouncer may reject statement_timeout
      // in startup packets. A client timeout alone is not SQL cancellation.
    });
    pool.on("error", () => {
      // Do not log messages, SQL, parameters or connection strings.
      console.error("auth_db_idle_connection_error", {
        total: pool.totalCount, idle: pool.idleCount, waiting: pool.waitingCount,
      });
    });
    runtime.alphaAuthPool = pool;
  }
  return runtime.alphaAuthPool;
}
