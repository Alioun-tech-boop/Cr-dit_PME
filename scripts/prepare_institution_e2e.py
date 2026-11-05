"""Jeu de démonstration des consoles, exclusivement dans output/frontend."""

import os
import json
import base64
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from scripts.prepare_partner_demo import prepare


def main():
    root = Path(os.environ["CREDIT_E2E_OUTPUT"]).resolve()
    allowed = Path(__file__).resolve().parents[1] / "output/frontend"
    if not root.is_relative_to(allowed.resolve()):
        raise RuntimeError("Démonstration non isolée")
    origin = os.environ["CREDIT_E2E_URL"]
    metadata = prepare(root, origin, test_password="Synthetic-browser-2026!")
    from credit.web.application import create_web_app

    app = create_web_app(os.environ["DATABASE_URL"])

    def client(user):
        c = TestClient(app, base_url=origin, headers={"Origin": origin})
        r = c.post("/auth/login", json={"username": user, "password": "Synthetic-browser-2026!"})
        if r.status_code != 200:
            raise RuntimeError("Connexion de fixture impossible")
        c.headers["X-CSRF-Token"] = c.get("/auth/csrf").json()["token"]
        return c

    def checked(r):
        if r.status_code >= 400:
            raise RuntimeError("Fixture refusée : " + str(r.status_code) + " " + r.text[:300])
        return r.json()

    def post(c, url, body=None):
        return checked(
            c.post("/api" + url, json=body or {}, headers={"Idempotency-Key": str(uuid4())})
        )

    analyst, manager, applicant = (
        client("demo-analyst"),
        client("demo-manager"),
        client("demo-applicant"),
    )
    try:
        for case in metadata["cases"]:
            path = "/" + case["core"] + "/" + case["id"]
            data = checked(analyst.get("/api" + path))
            assessment = post(analyst, path + "/financial-analyses")
            review = post(
                analyst,
                path + "/internal-reviews",
                {
                    "assessment_id": assessment["id"],
                    "expected_case_version": data["version"],
                    "source_ids": [],
                },
            )
            review = post(
                manager,
                "/internal-reviews/" + review["id"] + "/decisions",
                {
                    "expected_revision": review["revision"],
                    "decision": "approve",
                    "reason": "Revue synthétique complète avec limites reconnues.",
                    "public_reserves": "Démonstration uniquement, aucun engagement réel.",
                    "authorize_packet_preview": True,
                },
            )
            post(manager, "/internal-reviews/" + review["id"] + "/attestation")
            review = checked(applicant.get("/api/internal-reviews/" + review["id"]))
            transmission = post(
                applicant,
                path + "/banking/previews",
                {
                    "partner_id": metadata["partner_id"],
                    "review_id": review["id"],
                    "file_ids": [f["id"] for f in review["files"]],
                },
            )
            transmission = post(
                applicant,
                "/transmissions/" + transmission["id"] + "/confirm",
                {
                    "expected_revision": transmission["revision"],
                    "manifest_sha256": transmission["manifest_sha256"],
                    "attestation_id": transmission["attestation_id"],
                    "consent_version": "bank-sharing-fr-v1",
                    "accepted": True,
                    "authority_statement": "Demandeur synthétique confirmant un partage de démonstration.",
                },
            )
            transmission = post(applicant, "/transmissions/" + transmission["id"] + "/dispatch")
            case["transmission_id"] = transmission["id"]
    finally:
        for c in [analyst, manager, applicant]:
            c.close()
        app.state.api.state.engine.dispose()
    # Clé bancaire de démonstration distincte de celle de l’émetteur.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    key = Ed25519PrivateKey.generate()
    private = root / "bank-demo.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private.chmod(0o600)
    ring = json.loads((root / "keyring.json").read_text())
    ring["keys"].append(
        {
            "id": "bank-demo-key",
            "status": "active",
            "purpose": "demonstration",
            "issuer_ids": ["demo-bank-institution"],
            "private_key_path": str(private),
            "public_key_base64": base64.b64encode(
                key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
            ).decode(),
        }
    )
    (root / "keyring.json").write_text(json.dumps(ring))
    (root / "demo.json").write_text(json.dumps(metadata, indent=2))
    print("Dossiers synthétiques transmis et clé bancaire de démonstration préparés.")


if __name__ == "__main__":
    main()
