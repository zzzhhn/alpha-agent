# Bounded backend resources

This change reduces duplicate work at personal-project scale without adding a
service, modifying research history, or changing investment policy.

## Runtime behavior

- Node authentication and account actions share a process-local pg pool. The
  default is three connections, ten-second connection/queue wait and thirty-second
  idle eviction. `AUTH_DB_POOL_MAX` and `AUTH_DB_CONNECT_TIMEOUT_MS` can override
  positive integer defaults. Serverless instances still have separate pools.
- Idle connection errors are handled with pool counts only. No error messages,
  SQL parameters, connection strings or identities are logged.
- Do not send `statement_timeout` as a startup parameter to a pooled Neon URL.
  PgBouncer can reject it. Server-side query settings remain unchanged.
- Python API operations wait at most ten seconds for a connection. Queue exhaustion
  is a non-cacheable 503 with Retry-After. In-flight commands retain their existing
  timeout and explicit overrides. Mutating commands are not automatically retried.
  CLI/cron callers of the storage pool retain their original behavior.
- Shared response caches have LRU eviction, 128 entries and an estimated 8 MiB
  container budget per cache instance. Expired entries are swept on access/write;
  oversized results are served without retention. No background cleanup timer.
- The read-only turnover comparison coalesces identical public requests per
  strategy and event loop. Errors are not cached, cancellation releases ownership,
  and invalidation prevents stale loads from repopulating the cache. Private data,
  model calls and trading writes do not enter this mechanism.
- Recommendation/stock SQL transfers only the required JSON envelope fields.
  Nested observations (including long-horizon factor values), attribution flags
  and stock GEX remain available. Stored records are not modified.

## Measurement

Responses include Server-Timing for application time-to-headers, summed database
queue time and summed query time through the API adapter. Parallel query sums may
exceed request wall time. Startup initialization and statements on manually held
transaction connections are not fully attributed. Streaming duration is not
reported as time-to-headers. These values are not end-user p95 measurements.

Slow/error responses log route templates, method, status, durations and operation
count, never raw paths, query strings, request bodies or SQL. A timing header on
an edge-cached response describes its origin generation, not a new query.

## Scope and next gates

No database migration, forced vacuum, branch deletion, archived-payload migration,
paid compute change or pg_stat_statements installation is included. Use observed
latency and query plans to select the next step. Archive/retention changes need
explicit replay-preservation criteria before modifying historical evidence.

## References

- [node-postgres pool](https://node-postgres.com/apis/pool)
- [Neon connection errors](https://neon.com/docs/connect/connection-errors)
- [asyncpg pools](https://magicstack.github.io/asyncpg/current/api/index.html#connection-pools)
