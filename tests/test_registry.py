"""Tests for FactorRegistry: SQLite-backed factor storage with dedup."""

from __future__ import annotations

from pathlib import Path

import pytest

from alpha_agent.pipeline.registry import FactorRegistry


@pytest.fixture()
def registry(tmp_path: Path) -> FactorRegistry:
    return FactorRegistry(db_path=tmp_path / "test_factors.db")


def _sample_metrics() -> dict:
    return {"ic_mean": 0.05, "icir": 1.2, "sharpe": 0.8}


class TestAdd:
    def test_returns_positive_id(self, registry: FactorRegistry) -> None:
        row_id = registry.add("Rank($close)", "momentum", "test", _sample_metrics(), "abc123")
        assert row_id == 1

    def test_increments_id(self, registry: FactorRegistry) -> None:
        id1 = registry.add("$close", "h1", "r1", {}, "hash1")
        id2 = registry.add("$open", "h2", "r2", {}, "hash2")
        assert id2 == id1 + 1

    def test_duplicate_hash_returns_minus_one(self, registry: FactorRegistry) -> None:
        registry.add("$close", "h1", "r1", {}, "same_hash")
        assert registry.add("$volume", "h2", "r2", {}, "same_hash") == -1

    def test_duplicate_does_not_insert(self, registry: FactorRegistry) -> None:
        registry.add("$close", "h1", "r1", {}, "same_hash")
        registry.add("$volume", "h2", "r2", {}, "same_hash")
        assert registry.count() == 1


class TestExists:
    def test_false_when_empty(self, registry: FactorRegistry) -> None:
        assert registry.exists("nonexistent") is False

    def test_true_after_add(self, registry: FactorRegistry) -> None:
        registry.add("$close", "h1", "r1", {}, "my_hash")
        assert registry.exists("my_hash") is True

    def test_false_for_different_hash(self, registry: FactorRegistry) -> None:
        registry.add("$close", "h1", "r1", {}, "hash_a")
        assert registry.exists("hash_b") is False


class TestListAll:
    def test_empty_returns_empty(self, registry: FactorRegistry) -> None:
        assert registry.list_all() == []

    def test_returns_all_records(self, registry: FactorRegistry) -> None:
        registry.add("$close", "h1", "r1", {}, "hash1")
        registry.add("$open", "h2", "r2", {}, "hash2")
        assert len(registry.list_all()) == 2

    def test_preserves_order(self, registry: FactorRegistry) -> None:
        registry.add("expr_a", "h1", "r1", {}, "hash1")
        registry.add("expr_b", "h2", "r2", {}, "hash2")
        records = registry.list_all()
        assert records[0].expression == "expr_a"
        assert records[1].expression == "expr_b"

    def test_metrics_round_trip(self, registry: FactorRegistry) -> None:
        metrics = {"ic_mean": 0.05, "nested": {"a": 1}}
        registry.add("$close", "h1", "r1", metrics, "hash1")
        assert registry.list_all()[0].metrics == metrics


class TestGetById:
    def test_returns_record(self, registry: FactorRegistry) -> None:
        row_id = registry.add("$close", "h1", "r1", _sample_metrics(), "hash1")
        record = registry.get_by_id(row_id)
        assert record is not None
        assert record.expression == "$close"
        assert record.tree_hash == "hash1"

    def test_none_for_missing(self, registry: FactorRegistry) -> None:
        assert registry.get_by_id(999) is None

    def test_metrics_deserialized(self, registry: FactorRegistry) -> None:
        metrics = {"ic_mean": 0.07, "icir": 1.5}
        row_id = registry.add("$volume", "h1", "r1", metrics, "hash1")
        record = registry.get_by_id(row_id)
        assert record is not None
        assert record.metrics == metrics


class TestCount:
    def test_empty(self, registry: FactorRegistry) -> None:
        assert registry.count() == 0

    def test_after_adds(self, registry: FactorRegistry) -> None:
        for i in range(3):
            registry.add(f"e{i}", f"h{i}", f"r{i}", {}, f"hash{i}")
        assert registry.count() == 3

    def test_dedup_not_incremented(self, registry: FactorRegistry) -> None:
        registry.add("e1", "h1", "r1", {}, "same")
        registry.add("e2", "h2", "r2", {}, "same")
        assert registry.count() == 1


class TestFactorRecordImmutability:
    def test_record_is_frozen(self, registry: FactorRegistry) -> None:
        registry.add("$close", "h1", "r1", {}, "hash1")
        record = registry.list_all()[0]
        with pytest.raises((AttributeError, TypeError)):
            record.expression = "mutated"  # type: ignore[misc]

    def test_created_at_is_iso(self, registry: FactorRegistry) -> None:
        registry.add("$close", "h1", "r1", {}, "hash1")
        record = registry.list_all()[0]
        assert "T" in record.created_at
