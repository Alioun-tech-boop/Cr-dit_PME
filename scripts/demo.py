"""Soumet les quatre exemples à une API locale déjà démarrée."""

import json
import hashlib
import os
from pathlib import Path

import httpx

credentials = Path(
    os.getenv(
        "CREDIT_CREDENTIALS_FILE",
        ".local/auth/" + hashlib.sha256(b"agent-scans").hexdigest()[:16] + ".json",
    )
)
headers = {"Authorization": "Bearer " + json.loads(credentials.read_text())["token"]}

with httpx.Client(headers=headers, base_url="http://127.0.0.1:8000", timeout=30) as client:
    for kind, name in [
        ("individuals", "salarie"),
        ("individuals", "independant"),
        ("businesses", "pme_structuree"),
        ("businesses", "petite_activite"),
    ]:
        response = client.post(
            f"/{kind}", json=json.loads(Path(f"examples/{name}.json").read_text())
        )
        response.raise_for_status()
        case_id = response.json()["id"]
        response = client.post(f"/{kind}/{case_id}/analyses")
        response.raise_for_status()
        analysis = response.json()
        print(
            name,
            "dossier=",
            case_id,
            "analyse=",
            analysis["id"],
            "statut=",
            analysis["result"]["status"],
        )
        response = client.post(
            f"/{kind}/{case_id}/scenarios",
            json={
                "name": "Illustration libre : baisse de 20 %, hausse de 10 %",
                "revenue_drop": "0.20",
                "expense_increase": "0.10",
            },
        )
        response.raise_for_status()
        print("scénario=", response.json()["id"])
