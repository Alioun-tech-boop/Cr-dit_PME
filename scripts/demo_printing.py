"""Parcours HTTP d’édition, PDF, publication contrôlée et versions conservées."""

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
secret = Path(".local/auth") / (hashlib.sha256(args.user.encode()).hexdigest()[:16] + ".json")
headers = {"Authorization": "Bearer " + json.loads(secret.read_text())["token"]}
root = Path("output/printing/api")
root.mkdir(parents=True, exist_ok=True)
state_path = root / "state.json"
with httpx.Client(base_url=args.base_url, headers=headers, timeout=120) as client:

    def call(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    if args.verify_existing:
        state = json.loads(state_path.read_text())
        for path, digest in state["pdfs"].items():
            assert hashlib.sha256(call("GET", path).content).hexdigest() == digest
        for path, expected in state["metadata"].items():
            assert call("GET", path).json() == expected
        print(
            "Éditions, empreintes et métadonnées conservées après redémarrage :", len(state["pdfs"])
        )
    else:
        state = {"pdfs": {}, "metadata": {}}
        for core, name in [
            ("individuals", "individual_complete"),
            ("individuals", "individual_missing"),
            ("individuals", "individual_long"),
            ("businesses", "business_tables"),
        ]:
            data = json.loads(Path("examples/printing", name + ".json").read_text())
            case = call("POST", "/" + core, json=data).json()
            path = f"/{core}/" + case["id"]
            catalog = call("GET", path + "/print/templates").json()
            assert len(catalog) == (11 if core == "individuals" else 14)
            baseline = call("GET", path).json()
            report = call(
                "POST",
                path + "/assessments",
                json={"mode": "demonstration", "policy_id": core + "-illustrative-v1"},
            ).json()
            specs = [
                ("complete_file", None),
                ("analysis_summary", report["id"]),
                ("analysis_report", report["id"]),
                ("improvement_plan", report["id"]),
            ]
            if name == "individual_complete":
                sim = call(
                    "POST",
                    "/assessments/" + report["id"] + "/simulations",
                    json={"specification": {"kind": "lower_amount", "principal": "192000"}},
                ).json()
                specs.append(("simulation_report", sim["id"]))
            for template, assessment in specs:
                body = {"template_id": template, "audience": "analyst", "assessment_id": assessment}
                preflight = call("POST", path + "/print/preflight", json=body).json()
                assert "missing_information" in preflight
                preview = call("POST", path + "/print/preview", json=body)
                assert "default-src" in preview.headers["content-security-policy"]
                edition = call("POST", path + "/print/editions", json=body).json()
                assert edition["status"] == "completed", edition
                eid = edition["id"]
                epath = "/print-editions/" + eid
                pdf = call("GET", epath + "/pdf").content
                assert hashlib.sha256(pdf).hexdigest() == edition["pdf_sha256"]
                (root / (name + "-" + template + ".pdf")).write_bytes(pdf)
                (root / (name + "-" + template + ".html")).write_text(
                    call("GET", epath + "/preview").text
                )
                state["pdfs"][epath + "/pdf"] = edition["pdf_sha256"]
                state["metadata"][epath] = edition
            assert call("GET", path).json() == baseline
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        state_path.chmod(0o600)
        print("4 dossiers, 17 éditions réelles et leurs empreintes vérifiés ; dossiers inchangés.")
