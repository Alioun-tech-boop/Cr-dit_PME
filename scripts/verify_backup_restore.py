"""Sauvegarde/restauration réelle sur DEUX bases synthétiques créées par ce script."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config

DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
container = subprocess.run(
    DOCKER + ["compose", "ps", "-q", "db"], check=True, capture_output=True, text=True
).stdout.strip()
if not container:
    raise SystemExit("Service PostgreSQL local indisponible")
suffix = uuid4().hex[:12]
source = "audit_source_" + suffix
target = "audit_restore_" + suffix
runtime_role = "audit_app_" + suffix
root = Path("output/security/backup")
root.mkdir(parents=True, exist_ok=True)
os.umask(0o077)


def sql(database, statement):
    return subprocess.run(
        DOCKER
        + [
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "credit",
            "-d",
            database,
        ],
        input=statement.encode(),
        check=True,
        capture_output=True,
    ).stdout


def url(database):
    # Identifiants exclusivement locaux du Compose de démonstration.
    return "postgresql+psycopg://credit:credit_local@127.0.0.1:5432/" + database


created_databases = []
role_created = False
try:
    for database in [source, target]:
        assert re.fullmatch(r"audit_(?:source|restore)_[a-f0-9]{12}", database)
        sql("postgres", f"CREATE DATABASE {database};")
        created_databases.append(database)
    import credit.config

    credit.config.DATABASE_URL = url(source)
    command.upgrade(Config("alembic.ini"), "head")
    with tempfile.TemporaryDirectory() as directory:
        auth = Path(directory) / "users.json"
        auth.write_text(
            json.dumps(
                {
                    "users": [
                        {
                            "id": "backup-synthetic",
                            "token_sha256": hashlib.sha256(b"backup-synthetic").hexdigest(),
                            "reviewer": True,
                            "case_ids": [],
                        }
                    ]
                }
            )
        )
        os.environ["CREDIT_AUTH_FILE"] = str(auth)
        os.environ.pop("CREDIT_AUTH_JSON", None)
        from credit.api import create_app

        app = create_app(url(source))
        headers = {"Authorization": "Bearer backup-synthetic"}
        with TestClient(app, headers=headers) as client:
            case = client.post(
                "/individuals",
                json=json.loads(Path("examples/assessments/individual_control.json").read_text()),
            ).json()
            cid = case["id"]
            path = "/individuals/" + cid
            analysis = client.post(path + "/assessments", json={"mode": "real"}).json()
            edition = client.post(
                path + "/print/editions", json={"template_id": "identification"}
            ).json()
            assert edition["status"] == "completed", edition
            original = client.get("/print-editions/" + edition["id"] + "/pdf").content
            submitted = client.post(
                path + "/submissions",
                json={
                    "document_type": "payslip",
                    "role": "backup_synthetic",
                    "period": "2026-10-01",
                },
            ).json()
            scan_path = path + "/submissions/" + submitted["id"]
            source_payload = Path("examples/scans/salary.png").read_bytes()
            uploaded = client.post(scan_path + "/sources", content=source_payload)
            assert uploaded.status_code == 201, uploaded.text
            source_path = scan_path + "/sources/" + uploaded.json()["pages"][0]["source_id"]
            assert client.get(source_path).content == source_payload
        app.state.engine.dispose()
        dump = subprocess.run(
            DOCKER
            + [
                "exec",
                container,
                "pg_dump",
                "-U",
                "credit",
                "-d",
                source,
                "--format=custom",
                "--no-owner",
                "--no-acl",
            ],
            check=True,
            capture_output=True,
        ).stdout
        file = root / "synthetic.dump"
        file.write_bytes(dump)
        file.chmod(0o600)
        subprocess.run(
            DOCKER
            + [
                "exec",
                "-i",
                container,
                "pg_restore",
                "-U",
                "credit",
                "-d",
                target,
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
            ],
            input=dump,
            check=True,
            capture_output=True,
        )
        sql("postgres", f"CREATE ROLE {runtime_role} NOLOGIN;")
        role_created = True
        grants = (
            Path("ops/runtime_grants.sql")
            .read_text()
            .replace(':"app_role"', '"' + runtime_role + '"')
        )
        sql(target, grants)
        sql(target, f"SET ROLE {runtime_role}; SELECT count(*) FROM cases;")
        denied = [
            "CREATE TABLE forbidden_audit_write (id int);",
            "UPDATE analyses SET engine_version=engine_version;",
            "DELETE FROM security_events;",
            "SELECT * FROM pg_authid;",
        ]
        for statement in denied:
            try:
                sql(target, f"SET ROLE {runtime_role}; " + statement)
            except subprocess.CalledProcessError as exc:
                assert b"permission denied" in exc.stderr
            else:
                raise AssertionError("Le rôle applicatif a obtenu un privilège interdit")
        assert sql(source, "SELECT count(*) FROM security_events;") == sql(
            target, "SELECT count(*) FROM security_events;"
        )
        restored = create_app(url(target))
        with TestClient(restored, headers=headers) as client:
            assert client.get(path).json()["data"] == case["data"]
            assert (
                client.get("/assessments/" + analysis["id"]).json()["input_sha256"]
                == analysis["input_sha256"]
            )
            restored_pdf = client.get("/print-editions/" + edition["id"] + "/pdf").content
            assert restored_pdf == original
            assert client.get(source_path).content == source_payload
        restored.state.engine.dispose()
        report = {
            "status": "passed",
            "source": source,
            "target": target,
            "dump_sha256": hashlib.sha256(dump).hexdigest(),
            "pdf_sha256": hashlib.sha256(original).hexdigest(),
            "source_sha256": hashlib.sha256(source_payload).hexdigest(),
            "objects": ["case", "assessment_snapshot", "pdf_edition", "security_history"],
            "synthetic_only": True,
            "least_privilege_checks": [
                "read_cases_allowed",
                "no_schema_create",
                "no_history_update",
                "no_audit_delete",
                "no_pg_authid",
            ],
        }
        (root / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
finally:
    # Jamais de suppression d’une base préexistante : seulement les deux noms aléatoires ci-dessus.
    for database in created_databases:
        assert re.fullmatch(r"audit_(?:source|restore)_[a-f0-9]{12}", database)
        sql("postgres", f"DROP DATABASE IF EXISTS {database} WITH (FORCE);")

    if role_created:
        sql("postgres", f"DROP ROLE IF EXISTS {runtime_role};")
