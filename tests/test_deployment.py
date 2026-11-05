"""Contrats de démarrage et passerelle de déploiement, sans secrets."""
import os
from pathlib import Path
import subprocess
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from credit.security.entrypoint import listen_port


def test_render_port(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    assert listen_port() == 10000
    monkeypatch.delenv("PORT")
    assert listen_port() == 8000
    monkeypatch.setenv("PORT", "0")
    with pytest.raises(ValueError):
        listen_port()


def test_release_migration_head():
    assert ScriptDirectory.from_config(Config("alembic.ini")).get_current_head() == "0009"


def test_netlify_same_origin_proxy():
    path = Path("frontend/dist/_redirects")
    previous = path.read_bytes() if path.exists() else None
    try:
        env = dict(os.environ, CREDIT_BACKEND_ORIGIN="https://credit-pme-test.onrender.com")
        command = ["node", "scripts/build_netlify_routes.mjs"]
        assert subprocess.run(command, env=env, capture_output=True).returncode == 0
        rules = path.read_text()
        assert "/api/* https://credit-pme-test.onrender.com/api/:splat 200!" in rules
        assert "/auth/* https://credit-pme-test.onrender.com/auth/:splat 200!" in rules
        for invalid in ["http://credit-pme-test.onrender.com", "https://evil.test", "https://x.onrender.com/path", "https://user:password@x.onrender.com"]:
            env["CREDIT_BACKEND_ORIGIN"] = invalid
            assert subprocess.run(command, env=env, capture_output=True).returncode != 0
    finally:
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(previous)


def test_hosted_secret_copy_is_private(monkeypatch, tmp_path):
    from credit.security.entrypoint import prepare_private_registry
    source = tmp_path / "mounted.json"
    source.write_text('{"users": []}')
    source.chmod(0o644)
    monkeypatch.setenv("CREDIT_AUTH_SOURCE_FILE", str(source))
    monkeypatch.setenv("CREDIT_AUTH_FILE", "unused")
    prepare_private_registry()
    destination = Path(os.environ["CREDIT_AUTH_FILE"])
    try:
        assert destination.read_bytes() == source.read_bytes()
        assert destination.stat().st_mode & 0o777 == 0o600
        assert destination.parent.stat().st_mode & 0o777 == 0o700
        assert source.stat().st_mode & 0o777 == 0o644
    finally:
        destination.unlink()
        destination.parent.rmdir()
