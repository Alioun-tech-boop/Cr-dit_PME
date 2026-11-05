"""Environnement exclusivement synthétique, isolé de la base utilisateur."""

import hashlib
import json
import os
import fitz
from PIL import Image
from pathlib import Path
from credit.persistence import Base, sessions, WebUser
from credit.web.application import PASSWORDS

root = Path(os.environ.get("CREDIT_E2E_OUTPUT", "output/frontend/e2e"))
allowed = Path(__file__).resolve().parents[1] / "output/frontend"
if not root.resolve().is_relative_to(allowed.resolve()):
    raise RuntimeError("Le répertoire E2E doit rester dans output/frontend")
expected_url = "sqlite:///" + str((root / "database.db").resolve())
if os.environ.get("DATABASE_URL") != expected_url:
    raise RuntimeError("Refus de préparer une base non isolée ; utiliser run_frontend_e2e")
root.mkdir(parents=True, exist_ok=True)
users = [
    {
        "id": x,
        "token_sha256": hashlib.sha256(("synthetic-" + x).encode()).hexdigest(),
        "role": "analyst" if x == "analyst" else "applicant",
        "institution_id": "other" if x == "outsider" else "synthetic-bank",
        "case_ids": [],
    }
    for x in ("applicant", "analyst", "outsider")
]
registry = root / "users.json"
registry.write_text(json.dumps({"users": users}))
registry.chmod(0o600)
engine, factory = sessions(os.environ["DATABASE_URL"])
Base.metadata.create_all(engine)
with factory() as db:
    for actor in users:
        user = db.get(WebUser, actor["id"])
        if not user:
            db.add(
                WebUser(
                    actor_id=actor["id"],
                    username=actor["id"],
                    password_hash=PASSWORDS.hash("Synthetic-browser-2026!"),
                    profile={},
                )
            )
    db.commit()
print("Comptes synthétiques et tables E2E prêts ; registre exclu de Git.")

# Images synthétiques pour le parcours multipage ; aucun document client.
pdf = fitz.open("modules/credit_pme_pdf/examples/pdf/payslip_scan.pdf")
pix = pdf[0].get_pixmap(matrix=fitz.Matrix(1, 1))
pix.save(str(root / "page.png"))
Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(root / "page.jpg")
pdf.close()
