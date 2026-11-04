"""Démonstration HTTP synthétique et contrôle de conservation des rapports."""

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
output = Path("output/assessments/api")
output.mkdir(parents=True, exist_ok=True)
state_path = output / "state.json"
with httpx.Client(base_url=args.base_url, headers=headers, timeout=120) as client:

    def request(method, path, **kwargs):
        r = client.request(method, path, **kwargs)
        r.raise_for_status()
        return r

    if args.verify_existing:
        state = json.loads(state_path.read_text())
        for path, expected in state.items():
            assert request("GET", path).json() == expected, path
        print("Rapports et dossiers conservés à l’identique après redémarrage :", len(state))
    else:
        state = {}
        for name in [
            "individual_control",
            "individual_incomplete",
            "business_profitable_cash_tension",
            "business_seasonal",
        ]:
            kind = "individuals" if name.startswith("individual") else "businesses"
            payload = json.loads(Path(f"examples/assessments/{name}.json").read_text())
            case = request("POST", "/" + kind, json=payload).json()
            path = f"/{kind}/" + case["id"]
            state[path] = request("GET", path).json()
            analysis = request(
                "POST",
                path + "/assessments",
                json={"mode": "demonstration", "policy_id": kind + "-illustrative-v1"},
            ).json()
            aid = analysis["id"]
            state["/assessments/" + aid] = analysis
            assert len(analysis["result"]["sections"]) == (7 if kind == "individuals" else 9)
            assert analysis["result"]["scoring"]["combined_score"] is None
            (output / (name + ".json")).write_text(
                json.dumps(analysis, ensure_ascii=False, indent=2) + "\n"
            )
            (output / (name + ".md")).write_text(request("GET", f"/assessments/{aid}/report").text)
            if name == "individual_control":
                assert (
                    analysis["result"]["financial_calculations"]["periods"][0][
                        "margin_after_credit"
                    ]
                    == "70000.00"
                )
                for spec in [
                    {"kind": "stress", "scenario": {"revenue_drop": "0.20"}},
                    {"kind": "lower_amount", "principal": "192000"},
                    {"kind": "extend_term", "months": 12},
                ]:
                    simulated = request(
                        "POST", f"/assessments/{aid}/simulations", json={"specification": spec}
                    ).json()
                    state["/assessments/" + simulated["id"]] = simulated
                    if spec["kind"] == "stress":
                        assert (
                            simulated["result"]["financial_calculations"]["periods"][0][
                                "margin_after_credit"
                            ]
                            == "-30000.00"
                        )
                assert request("GET", path).json() == state[path]
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        state_path.chmod(0o600)
        print("4 dossiers, 4 rapports et 3 simulations vérifiés ; sources originales inchangées.")
