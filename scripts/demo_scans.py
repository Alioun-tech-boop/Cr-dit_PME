"""Parcours HTTP synthétique v0.2 avec identité locale, pages, OCR et revue humaine."""

import argparse
import hashlib
import json
from pathlib import Path

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--user", default="agent-scans")
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--verify-existing", action="store_true")
args = parser.parse_args()
credentials = Path(".local/auth") / (hashlib.sha256(args.user.encode()).hexdigest()[:16] + ".json")
headers = {"Authorization": "Bearer " + json.loads(credentials.read_text())["token"]}
output = Path("output/scans/api")
output.mkdir(parents=True, exist_ok=True)
state_path = output / "state.json"


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


with httpx.Client(base_url=args.base_url, headers=headers, timeout=120) as client:

    def get(path):
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    def post(path, **kwargs):
        response = client.post(path, **kwargs)
        response.raise_for_status()
        return response.json()

    if args.verify_existing:
        state = json.loads(state_path.read_text())
        for path, value in state["json"].items():
            assert get(path) == value, path
        for path, digest in state["originals"].items():
            response = client.get(path)
            response.raise_for_status()
            assert hashlib.sha256(response.content).hexdigest() == digest
        print(
            "Après redémarrage : dépôts, sources, géométrie, extractions et revues conservés à l’identique."
        )
    else:
        assert len(get("/documents/policies")["rules"]) == 132
        state = {"json": {}, "originals": {}}
        for kind, filename, doc_type, files in [
            (
                "individuals",
                "salarie",
                "payslip",
                [Path("examples/scans/salary.png"), Path("examples/scans/salary.jpg")],
            ),
            (
                "businesses",
                "pme_structuree",
                "bank_statement",
                [Path("modules/credit_pme_pdf/examples/pdf/bank_table.pdf")],
            ),
        ]:
            case = post("/" + kind, json=json.loads(Path(f"examples/{filename}.json").read_text()))
            case_path = f"/{kind}/" + case["id"]
            baseline = get(case_path)
            analysis = post(case_path + "/analyses")
            submission = post(
                case_path + "/submissions",
                json={
                    "document_type": doc_type,
                    "role": "demonstration_synthetique",
                    "period": "2026-10-01",
                },
            )
            path = case_path + "/submissions/" + submission["id"]
            for file in files:
                submission = post(
                    path + "/sources",
                    content=file.read_bytes(),
                    headers={"Content-Type": "application/octet-stream"},
                )
                page = submission["pages"][-1]
                state["originals"][path + "/sources/" + page["source_id"]] = hashlib.sha256(
                    file.read_bytes()
                ).hexdigest()
            if kind == "individuals":
                pages = list(reversed(submission["pages"]))
                edits = [
                    {"id": pages[0]["id"], "rotation": 90, "crop": [0, 0, 1, 1]},
                    {"id": pages[1]["id"], "rotation": 0, "crop": [0.02, 0.05, 0.95, 0.6]},
                ]
                response = client.put(
                    path + "/pages",
                    json={"expected_revision": submission["revision"], "pages": edits},
                )
                response.raise_for_status()
                submission = response.json()
                edits[0]["rotation"] = 0
                response = client.put(
                    path + "/pages",
                    json={"expected_revision": submission["revision"], "pages": edits},
                )
                response.raise_for_status()
            post(path + "/confirm")
            submission = post(path + "/process")
            assert submission["processing_status"] == "completed", submission.get(
                "processing_error"
            )
            run_path = path + "/runs/" + submission["latest_run_id"]
            run = get(run_path)
            if kind == "individuals":
                candidate = run["extraction"]["fields"]["net_income"]["candidates"][0]
                assert candidate["normalized"]["amount_as_printed"] == "280000"
                assert candidate["source"]["source_id"]
                post(
                    run_path + "/reviews",
                    json={
                        "decisions": {
                            "net_income": {
                                "value": {
                                    "amount": "280000",
                                    "currency": "XOF",
                                    "unit_multiplier": "1",
                                },
                                "evidence_ids": [candidate["evidence_id"]],
                                "reason": "Lecture humaine synthétique de la page et de la zone source.",
                            }
                        }
                    },
                )
                assert get(path)["review_status"] == "partially_reviewed"
            else:
                assert run["extraction"]["tables"][0]["rows"][1][3] == "280 000"
            assert get(case_path) == baseline
            assert post(case_path + "/analyses")["result"] == analysis["result"]
            assert get(path)["authenticity_status"] == "not_assessed"
            assert get(path)["ready_for_scoring"] is False
            state["json"][case_path] = baseline
            state["json"][path] = get(path)
            state["json"][run_path] = get(run_path)
            state["json"][path + "/events"] = get(path + "/events")
            page = get(path)["pages"][0]
            preview = client.get(run_path + "/pages/" + page["id"])
            preview.raise_for_status()
            (output / (kind + ".png")).write_bytes(preview.content)
            save(output / (kind + ".json"), get(run_path))
        save(state_path, state)
        print(
            "HTTP réel : 2 noyaux, JPEG/PNG/PDF, pages réordonnées/recadrées, OCR fra, revue et sources vérifiés ; aucun scoring alimenté."
        )
