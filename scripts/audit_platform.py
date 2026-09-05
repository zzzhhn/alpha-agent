"""Read-only, bounded production inventory. Never triggers jobs or LLM calls.

Run from the repository root. An optional --env-file supplies DATABASE_URL;
only aggregate database statistics are written to the report, never secrets.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

READ_ROUTES = (
    "/api/_health", "/api/_health/routers", "/api/_health/signals",
    "/api/_health/cron", "/api/_health/dag", "/api/_health/data_sources",
    "/api/picks/lean?limit=5", "/api/stock/NVDA", "/api/stock/AAPL",
    "/api/evolution/ic_trend", "/api/evolution/weights", "/api/evolution/changes?limit=5",
    "/api/evolution/proposals", "/api/alerts/recent?limit=5",
    "/api/brain/runs?limit=5", "/api/v1/data/operands", "/api/v1/data/sectors",
    "/api/v1/data/universe", "/api/v1/data/coverage", "/api/v1/factors/library",
    "/api/l2/summary", "/api/user/me", "/api/paper/account", "/api/alerts/inbox",
    "/api/factor-lab/briefing", "/api/evolution/calibration",
)

DB_QUERIES = {
    "size": "SELECT pg_database_size(current_database()) AS database_bytes",
    "tables": """SELECT relname, n_live_tup, n_dead_tup, seq_scan, idx_scan,
        pg_total_relation_size(relid) AS total_bytes,
        pg_relation_size(relid) AS heap_bytes,
        pg_indexes_size(relid) AS index_bytes,
        last_autovacuum, last_autoanalyze
        FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC""",
    "indexes": """SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname='public' ORDER BY tablename, indexname""",
    "migrations": "SELECT version FROM schema_migrations ORDER BY version",
    "connections": """SELECT state, count(*) FROM pg_stat_activity
        WHERE datname=current_database() GROUP BY state""",
    "signal_coverage": """SELECT 'fast' AS source, count(*) AS rows,
        count(DISTINCT ticker) AS tickers, min(date), max(date) FROM daily_signals_fast
        UNION ALL SELECT 'slow', count(*), count(DISTINCT ticker), min(date), max(date)
        FROM daily_signals_slow""",
    "expired_cache": """SELECT count(*) AS rows,
        count(*) FILTER (WHERE expires_at <= now()) AS expired FROM llm_cache""",
    "log_counts": """SELECT 'error_log' AS source, count(*) AS rows, min(ts) AS oldest,
        max(ts) AS newest FROM error_log
        UNION ALL SELECT 'cron_runs',count(*),min(started_at),max(started_at) FROM cron_runs""",
}


async def audit(base: str, env_file: str | None) -> dict:
    result = {"observed_at": datetime.now(UTC).isoformat(), "base": base}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        schema = await client.get(base + "/api/openapi.json")
        schema.raise_for_status()
        paths = schema.json()["paths"]
        result["api_routes"] = {p: list(v.keys()) for p, v in paths.items()}
        sem = asyncio.Semaphore(2)

        async def probe(path: str) -> dict:
            async with sem:
                started = time.monotonic()
                try:
                    response = await client.get(base + path)
                    body = response.json() if "json" in response.headers.get("content-type", "") else {}
                    row = {"path": path, "status": response.status_code,
                           "seconds": round(time.monotonic() - started, 3),
                           "bytes": len(response.content), "keys": list(body) if isinstance(body, dict) else []}
                    if isinstance(body, dict) and "card" in body:
                        card = body["card"]
                        row["signals"] = [e["signal"] for e in card.get("breakdown", [])]
                        row["partial"] = card.get("partial")
                    if path.startswith("/api/_health"):
                        row["health"] = body
                    return row
                except Exception as exc:
                    return {"path": path, "error_type": type(exc).__name__,
                            "seconds": round(time.monotonic() - started, 3)}

        result["http"] = await asyncio.gather(*(probe(p) for p in READ_ROUTES
                                                  if p.split("?")[0] in paths or "/_health" in p
                                                  or p.startswith("/api/stock/")))
    if env_file:
        import asyncpg
        from dotenv import dotenv_values
        dsn = dotenv_values(env_file).get("DATABASE_URL")
        if not dsn:
            raise ValueError("DATABASE_URL missing in supplied env file")
        conn = await asyncpg.connect(dsn, timeout=15, command_timeout=20)
        try:
            result["database"] = {}
            for name, query in DB_QUERIES.items():
                async with conn.transaction(readonly=True):
                    started = time.monotonic()
                    rows = await conn.fetch(query)
                    result["database"][name] = {"seconds": round(time.monotonic() - started, 3),
                                               "rows": [dict(row) for row in rows]}
        finally:
            await conn.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="https://alpha-api.bobbyzhong.com")
    parser.add_argument("--env-file")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = asyncio.run(audit(args.base.rstrip("/"), args.env_file))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    print(json.dumps({"output": args.output, "routes": len(report["api_routes"]),
                      "http": [{k: v for k, v in r.items() if k != "health"} for r in report["http"]]},
                     ensure_ascii=False, indent=2))
