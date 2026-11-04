"""Reproductions locales synthétiques ; aucune cible extérieure ni base existante."""

from copy import deepcopy
from decimal import localcontext
import hashlib
import json
import os
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from credit.persistence import Base
from credit.api import create_app
from credit.individuals.contracts import IndividualCase
from credit.businesses.contracts import BusinessCase
from credit.individuals.engine import analyze
from credit.businesses.engine import analyze as business_analyze
from credit.assessment.engines import IndividualAnalysisEngine


def main():
    findings = {}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        users = [
            {
                "id": "staff",
                "token_sha256": hashlib.sha256(b"synthetic-staff").hexdigest(),
                "reviewer": True,
                "case_ids": [],
            },
            {
                "id": "applicant",
                "token_sha256": hashlib.sha256(b"synthetic-applicant").hexdigest(),
                "case_ids": [],
            },
        ]
        auth = root / "auth.json"
        auth.write_text(json.dumps({"users": users}))
        os.environ["CREDIT_AUTH_FILE"] = str(auth)
        os.environ.pop("CREDIT_AUTH_JSON", None)
        app = create_app("sqlite:///" + str(root / "audit.db"))
        Base.metadata.create_all(app.state.engine)
        with TestClient(app, headers={"Authorization": "Bearer synthetic-staff"}) as client:
            raw = json.loads(Path("examples/assessments/individual_control.json").read_text())
            raw["record_details"] = {"internal_observations": "INTERNAL_SYNTHETIC_MARKER"}
            r = client.post("/individuals", json=raw)
            cid = r.json()["id"]
            path = "/individuals/" + cid
            users[1]["case_ids"] = [cid]
            auth.write_text(json.dumps({"users": users}))
            regular = {"Authorization": "Bearer synthetic-applicant"}
            case = client.get(path, headers=regular)
            findings["F-001_internal_fields_disclosed"] = "INTERNAL_SYNTHETIC_MARKER" in case.text
            analysis = client.post(path + "/assessments", json={"mode": "real"}).json()
            findings["F-001_internal_analysis_status"] = client.get(
                "/assessments/" + analysis["id"], headers=regular
            ).status_code
            forged = deepcopy(raw)
            forged["evidence"][0].update(
                status="verified",
                review_id="synthetic-forged-review",
                verification_method="self_attested",
            )
            findings["F-002_forged_verification_status"] = client.put(
                path, json=forged, headers=regular
            ).status_code
            stale = deepcopy(raw)
            stale["name"] = "Stale overwrite"
            findings["F-003_update_without_version_status"] = client.put(
                path, json=stale
            ).status_code
        app.state.engine.dispose()
    case = IndividualCase.model_validate(
        json.loads(Path("examples/assessments/individual_control.json").read_text())
    )
    raw = case.model_dump(mode="json")
    raw["analysis_details"]["expenses"].append(
        {
            "period": raw["periods"][0]["period"],
            "category": "health",
            "frequency": "future",
            "included_in_total": False,
            "amount": {"value": "10000", "state": "known", "evidence_ids": ["synthetic"]},
        }
    )
    case = IndividualCase.model_validate(raw)
    findings["F-004_legacy_margin"] = str(analyze(case).periods[0].margin_after_credit)
    findings["F-004_section_margin"] = str(
        IndividualAnalysisEngine().calculate(case).periods[0].margin_after_credit
    )
    biz = BusinessCase.model_validate_json(Path("examples/pme_structuree.json").read_text())
    findings["F-005_default_ratio"] = str(business_analyze(biz).periods[0].debt_service_coverage)
    with localcontext() as context:
        context.prec = 8
        findings["F-005_altered_context_ratio"] = str(
            business_analyze(biz).periods[0].debt_service_coverage
        )
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
