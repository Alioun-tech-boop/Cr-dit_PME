import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


@pytest.fixture
def individual():
    return json.loads(Path("examples/salarie.json").read_text())


@pytest.fixture
def business():
    return json.loads(Path("examples/pme_structuree.json").read_text())


@pytest.fixture
def url(tmp_path, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'credit.db'}")
    # Une base PostgreSQL dédiée aux tests est exigée si TEST_DATABASE_URL est défini.
    import credit.config

    monkeypatch.setattr(credit.config, "DATABASE_URL", url)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield url
    command.downgrade(cfg, "base")


@pytest.fixture(autouse=True)
def local_identities(tmp_path, monkeypatch):
    import hashlib

    identities = {
        "users": [
            {
                "id": "agent-a",
                "token_sha256": hashlib.sha256(b"synthetic-a").hexdigest(),
                "reviewer": True,
                "native_exception": True,
                "case_ids": [],
            },
            {
                "id": "agent-b",
                "token_sha256": hashlib.sha256(b"synthetic-b").hexdigest(),
                "reviewer": False,
                "native_exception": False,
                "case_ids": [],
            },
        ]
    }
    path = tmp_path / "identities.json"
    path.write_text(json.dumps(identities))
    monkeypatch.delenv("CREDIT_AUTH_JSON", raising=False)
    monkeypatch.setenv("CREDIT_AUTH_FILE", str(path))
    monkeypatch.setenv("TESSDATA_PREFIX", "/workspace/.local/share/tessdata")
    return path


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer synthetic-a"}


@pytest.fixture
def client(url, auth_headers):
    from fastapi.testclient import TestClient
    from credit.api import create_app

    app = create_app(url)
    with TestClient(app, headers=auth_headers) as client:
        yield client
    app.state.engine.dispose()
