"""Créer explicitement une démonstration locale isolée, sans modifier la base utilisateur."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
from datetime import datetime, timedelta, timezone


def prepare(root, origin, test_password=None):
    project = Path(__file__).resolve().parents[1]
    root = root.resolve()
    if not any(
        root.is_relative_to(p)
        for p in [
            (project / ".local/partner-demo").resolve(),
            (project / "output/frontend").resolve(),
        ]
    ):
        raise RuntimeError(
            "La démonstration doit rester dans .local/partner-demo/ ou output/frontend/."
        )
    if os.getenv("CREDIT_ENV") == "production":
        raise RuntimeError("Démonstration interdite en production")
    if (root / "users.json").exists() or (root / "database.db").exists():
        raise RuntimeError(
            "Répertoire déjà préparé : conserver ses données et choisir un nouveau répertoire."
        )
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=True)
    env = {
        "DATABASE_URL": "sqlite:///" + str(root / "database.db"),
        "CREDIT_AUTH_FILE": str(root / "users.json"),
        "CREDIT_PARTNER_KEYRING_FILE": str(root / "keyring.json"),
        "CREDIT_PARTNER_ALLOW_DEMO": "true",
        "CREDIT_WEB_ORIGIN": origin,
        "CREDIT_ENV": "local",
        "CREDIT_ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
    }
    os.environ.update(env)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    key = Ed25519PrivateKey.generate()
    private = root / "demo-key.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private.chmod(0o600)
    public = base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    ring = {
        "keys": [
            {
                "id": "partner-demo-key",
                "status": "active",
                "purpose": "demonstration",
                "issuer_ids": ["demo-issuer"],
                "private_key_path": str(private),
                "public_key_base64": public,
            }
        ]
    }
    (root / "keyring.json").write_text(json.dumps(ring, indent=2))
    (root / "keyring.json").chmod(0o600)
    (root / "public-keyring.json").write_text(
        json.dumps(
            {"keys": [{k: v for k, v in ring["keys"][0].items() if k != "private_key_path"}]},
            indent=2,
        )
    )
    specs = {
        "demo-admin": ("administrator", "demo-issuer"),
        "demo-analyst": ("analyst", "demo-issuer"),
        "demo-manager": ("institution_manager", "demo-issuer"),
        "demo-applicant": ("applicant", "demo-issuer"),
        "demo-bank": ("bank_manager", "demo-bank-institution"),
        "demo-bank-other": ("bank_agent", "demo-bank-other-institution"),
    }
    tokens = {id: secrets.token_urlsafe(32) for id in specs}
    passwords = {id: test_password or secrets.token_urlsafe(18) for id in specs}
    users = [
        {
            "id": id,
            "role": role,
            "institution_id": inst,
            "case_ids": [],
            "token_sha256": hashlib.sha256(tokens[id].encode()).hexdigest(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        }
        for id, (role, inst) in specs.items()
    ]
    (root / "users.json").write_text(json.dumps({"users": users}))
    (root / "users.json").chmod(0o600)
    (root / "accounts.private.json").write_text(
        json.dumps(
            {
                "origin": origin,
                "users": {id: {"username": id, "password": passwords[id]} for id in specs},
            },
            indent=2,
        )
    )
    (root / "accounts.private.json").chmod(0o600)
    # La configuration est fixée avant import ; migrations appliquées uniquement à la base isolée.
    import credit.config

    credit.config.DATABASE_URL = env["DATABASE_URL"]
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(project / "alembic.ini")), "head")
    from credit.web.application import create_web_app, PASSWORDS
    from credit.persistence import WebUser

    app = create_web_app(env["DATABASE_URL"])
    factory = app.state.session_factory
    with factory() as session:
        for id in specs:
            session.add(
                WebUser(
                    actor_id=id,
                    username=id,
                    password_hash=PASSWORDS.hash(passwords[id]),
                    profile={"display_name": id + " — synthétique"},
                )
            )
        session.commit()
    from fastapi.testclient import TestClient

    def headers(id):
        return {"Authorization": "Bearer " + tokens[id]}

    def checked(response):
        if response.status_code >= 400:
            raise RuntimeError(
                "Initialisation de démonstration échouée, HTTP "
                + str(response.status_code)
                + ": "
                + response.text
            )
        return response.json()

    with TestClient(app) as client:
        policy = json.loads(
            (project / "examples/partners/institution-policy.demo.json").read_text()
        )
        checked(
            client.put("/api/partners/admin/policy", json=policy, headers=headers("demo-admin"))
        )
        bank = json.loads((project / "examples/partners/bank.demo.json").read_text())
        partner = checked(
            client.post("/api/partners/admin/banks", json=bank, headers=headers("demo-admin"))
        )
        tested = checked(
            client.post(
                "/api/partners/admin/banks/" + partner["id"] + "/test",
                headers=headers("demo-admin"),
            )
        )
        partner = checked(
            client.post(
                "/api/partners/admin/banks/" + partner["id"] + "/activate",
                headers=headers("demo-admin"),
                json={
                    "expected_version": tested["version"],
                    "agreement_reference": "ACCORD FICTIF DÉMONSTRATION",
                    "representative_verification_reference": "REPRÉSENTANTS SYNTHÉTIQUES UNIQUEMENT",
                    "data_sharing_reference": "PARTAGE LOCAL FICTIF",
                    "legal_review_reference": "DÉMONSTRATION SANS VALIDATION JURIDIQUE",
                },
            )
        )
        cases = []
        for core, name in [
            ("individuals", "individual_control"),
            ("businesses", "business_profitable_cash_tension"),
        ]:
            raw = json.loads((project / "examples/assessments" / (name + ".json")).read_text())
            case = checked(client.post("/api/" + core, json=raw, headers=headers("demo-admin")))
            base = "/api/" + core + "/" + case["id"]
            checked(
                client.post(
                    base + "/banking/assign-applicant",
                    json={"actor_id": "demo-applicant", "expected_case_version": case["version"]},
                    headers=headers("demo-admin"),
                )
            )
            checked(client.post(base + "/banking/review-access", headers=headers("demo-applicant")))
            cases.append({"core": core, "id": case["id"], "name": raw["name"]})
    metadata = {"cases": cases, "partner_id": partner["id"], "origin": origin, "environment": env}
    (root / "demo.json").write_text(json.dumps(metadata, indent=2))
    # Fichier sourceable : ne contient que des chemins privés et de la configuration locale.
    import shlex

    (root / "env.sh").write_text(
        "\n".join("export " + key + "=" + shlex.quote(value) for key, value in env.items()) + "\n"
    )
    print("Démonstration synthétique préparée :", root)
    print("Configuration :", root / "env.sh")
    print("Comptes privés (ne pas versionner ni publier) :", root / "accounts.private.json")
    print("Aucune banque réelle, clé temporaire au démarrage ou transmission externe.")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".local/partner-demo/session-1"))
    parser.add_argument("--origin", default="http://127.0.0.1:8006")
    args = parser.parse_args()
    prepare(args.directory, args.origin)


if __name__ == "__main__":
    main()
