"""Bundle metadata stays cheap, versioned, and safe for public edge caching."""
import json
import os

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_agent.api.routes import data


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    parquet = tmp_path / "bundle.parquet"
    manifest = tmp_path / "research_dataset.json"
    pd.DataFrame([
        {"ticker": ticker, "date": day, "sector": sector}
        for day in ("2023-10-30", "2026-10-30")
        for ticker, sector in (("AAA", "Tech"), ("BBB", "Finance"), ("SPY", None))
    ]).to_parquet(parquet)
    manifest.write_text(json.dumps({"tickers": 3, "market_data_through": "2026-10-30"}))
    monkeypatch.setattr(data, "PARQUET_PATH", parquet)
    monkeypatch.setattr(data, "_MANIFEST_PATH", manifest)
    data._cached_bundle_metadata.cache_clear()
    app = FastAPI()
    app.include_router(data.router)
    with TestClient(app) as client:
        yield client, parquet, manifest
    data._cached_bundle_metadata.cache_clear()


def test_universe_and_sectors_share_versioned_bundle_cache(bundle, monkeypatch):
    client, parquet, manifest = bundle
    reads = []
    loader = data._read_bundle_metadata

    def counted():
        reads.append(True)
        return loader()

    monkeypatch.setattr(data, "_read_bundle_metadata", counted)
    for _ in range(2):
        response = client.get("/api/v1/data/universe")
        assert response.status_code == 200
        assert response.headers["cache-control"] == (
            "public, s-maxage=86400, stale-while-revalidate=604800"
        )
        info = response.json()["universes"][0]
        assert info["id"] == "SP500_subset"
        assert info["name"] == "S&P 500 historical members · 2 tickers · 2023-10-30→2026-10-30"
        assert info["tickers"] == ["AAA", "BBB"]
        assert info["ticker_count"] == 2
        assert info["sectors"] == ["Tech", "Finance"]
    sectors = client.get("/api/v1/data/sectors")
    assert sectors.json() == {"sectors": ["Finance", "Tech"], "panel_has_sector": True}
    assert sectors.headers["cache-control"] == response.headers["cache-control"]
    assert len(reads) == 1

    # Invalidate on either bundle or manifest version, even at equal file size.
    stat = parquet.stat()
    os.utime(parquet, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))
    assert client.get("/api/v1/data/universe").status_code == 200
    assert len(reads) == 2
    manifest.write_text(json.dumps({"tickers": 4, "market_data_through": "2026-11-02"}))
    updated = client.get("/api/v1/data/universe").json()["universes"][0]
    # Name counts tradable tickers from the bundle; the manifest supplies the end date.
    assert "2 tickers" in updated["name"] and updated["name"].endswith("2026-11-02")
    assert len(reads) == 3


def test_universe_missing_bundle_is_uncached_503(bundle):
    client, parquet, _ = bundle
    parquet.unlink()
    for endpoint in ("universe", "sectors"):
        response = client.get(f"/api/v1/data/{endpoint}")
        assert response.status_code == 503
        assert "cache-control" not in response.headers


def test_universe_legacy_bundle_without_sector_or_manifest(bundle):
    client, parquet, manifest = bundle
    frame = pd.read_parquet(parquet).drop(columns="sector")
    frame.to_parquet(parquet)
    manifest.unlink()
    info = client.get("/api/v1/data/universe").json()["universes"][0]
    assert info["sectors"] is None
    assert "2 tickers" in info["name"]
    assert client.get("/api/v1/data/sectors").json() == {
        "sectors": [], "panel_has_sector": False,
    }
