from types import SimpleNamespace

import pytest

from credit.security import entrypoint


class FakeConnection:
    def __init__(self, role):
        self.role = role
        self.statements = []

    def execution_options(self, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        if "FROM pg_roles" in sql:
            return SimpleNamespace(one=lambda: self.role)
        return SimpleNamespace()


class FakeEngine:
    def __init__(self, role):
        self.connection = FakeConnection(role)
        self.disposed = False

    def connect(self):
        return self.connection

    def dispose(self):
        self.disposed = True


def test_render_migration_uses_guarded_role_and_advisory_lock(monkeypatch):
    engine = FakeEngine((False, False, False, False, True))
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(entrypoint, "create_engine", lambda *a, **k: engine)
    monkeypatch.setattr(entrypoint.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    entrypoint.migrate_production_database()

    assert len(calls) == 1
    assert calls[0][0][0] == [entrypoint.sys.executable, "-m", "alembic", "upgrade", "head"]
    sql = [statement for statement, _ in engine.connection.statements]
    assert any("pg_advisory_lock" in statement for statement in sql)
    assert any("pg_advisory_unlock" in statement for statement in sql)
    assert engine.disposed


def test_render_migration_refuses_role_without_schema_create(monkeypatch):
    engine = FakeEngine((False, False, False, False, False))
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(entrypoint, "create_engine", lambda *a, **k: engine)
    monkeypatch.setattr(entrypoint.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    with pytest.raises(RuntimeError, match="droit CREATE"):
        entrypoint.migrate_production_database()

    assert calls == []
    assert engine.disposed


def test_render_migration_refuses_privileged_role(monkeypatch):
    engine = FakeEngine((False, False, True, False, True))
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(entrypoint, "create_engine", lambda *a, **k: engine)

    with pytest.raises(RuntimeError, match="privilèges élevés"):
        entrypoint.migrate_production_database()

    assert engine.disposed
