"""The full local registry uses SQLAlchemy, an optional dependency on Vercel."""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from alpha_agent.auth.dependencies import require_admin

sqlalchemy = pytest.importorskip("sqlalchemy")


def test_factor_registry_write_contract():
    from alpha_agent.api.routes.factors_db import router

    writes = [r for r in router.routes if r.methods & {"DELETE", "POST", "PATCH", "PUT"}]
    assert writes
    assert all(require_admin in {dep.call for dep in r.dependant.dependencies} for r in writes)


def test_factor_detail_outside_latest_page(tmp_path, monkeypatch):
    from alpha_agent.api.routes import factors_db
    from sqlalchemy.orm import Session
    from alpha_agent.storage import factor_db

    engine = sqlalchemy.create_engine(f"sqlite:///{tmp_path / 'factors.sqlite'}")
    monkeypatch.setattr(factor_db, "get_engine", lambda: engine)
    factor_db.Base.metadata.create_all(engine)
    with Session(engine) as session:
        for i in range(201):
            session.add(factor_db.Factor(
                id=f"f{i}", name=f"factor {i}", ast_hash=str(i), expression="close",
                created_at=datetime(2026, 1, 1),
                updated_at=datetime(2026, 1, 1) + timedelta(minutes=i),
            ))
        session.commit()
    assert "f0" not in {row.id for row in factors_db.list_factors(limit=200)}
    assert factors_db.get_factor("f0").factor.name == "factor 0"
    with pytest.raises(HTTPException) as exc:
        factors_db.get_factor("missing")
    assert exc.value.status_code == 404
