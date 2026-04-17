"""storage layer: persistence backends.

Planned contents (W2+):
    factor_registry.py  - SQLite-backed factor store (migrated from pipeline/)
    ohlcv_cache.py      - Parquet-backed OHLCV cache
    query_engine.py     - DuckDB layer for ad-hoc SQL over Parquet
"""
