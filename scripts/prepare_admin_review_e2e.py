"""Revue manuelle réelle sur documents synthétiques, exclusivement output/frontend."""

import os
import json
from pathlib import Path
from fastapi.testclient import TestClient
from scripts.prepare_institution_e2e import main as prepare


def main():
    prepare()
    from credit.web.application import create_web_app
    from credit.partners.models import InstitutionPolicy

    root = Path(os.environ["CREDIT_E2E_OUTPUT"])
    origin = os.environ["CREDIT_E2E_URL"]
    app = create_web_app(os.environ["DATABASE_URL"])
    metadata = json.loads((root / "demo.json").read_text())
    with app.state.api.state.session_factory() as db:
        item = db.get(InstitutionPolicy, "demo-issuer")
        data = json.loads(json.dumps(item.data))
        data["policy"]["signatories"] = [
            *data["policy"]["signatories"],
            {
                "actor_id": "demo-admin",
                "name": "Administrateur synthétique",
                "function": "Responsable habilité de revue",
            },
        ]
        item.data = data
        db.commit()
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:

        def checked(r):
            if r.status_code >= 400:
                raise RuntimeError(
                    "Préparation revue refusée : " + str(r.status_code) + " " + r.text[:300]
                )
            return r.json()

        checked(
            client.post(
                "/auth/login",
                json={"username": "demo-analyst", "password": "Synthetic-browser-2026!"},
            )
        )
        client.headers["X-CSRF-Token"] = checked(client.get("/auth/csrf"))["token"]
        for case in metadata["cases"]:
            path = "/api/" + case["core"] + "/" + case["id"] + "/submissions"
            sub = checked(
                client.post(
                    path,
                    json={
                        "document_type": "bank_statement",
                        "role": "Contrôle synthétique des encaissements",
                        "period": "2026-10-01",
                    },
                )
            )
            path += "/" + sub["id"]
            checked(
                client.post(
                    path + "/sources",
                    content=Path(
                        "modules/credit_pme_pdf/examples/pdf/bank_statement.pdf"
                    ).read_bytes(),
                    headers={"Content-Type": "application/octet-stream"},
                )
            )
            checked(client.post(path + "/confirm"))
            sub = checked(client.post(path + "/process"))
            if not sub["latest_run_id"]:
                raise RuntimeError("Extraction synthétique absente")
            case["submission_id"] = sub["id"]
    (root / "demo.json").write_text(json.dumps(metadata))
    print("Pièces synthétiques extraites pour revue humaine des deux noyaux.")


if __name__ == "__main__":
    main()
