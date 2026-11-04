from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from credit.api import create_app

ROOT = Path("examples/assessments")


def create(client, name="individual_control", core="individuals"):
    response = client.post("/" + core, json=json.loads((ROOT / (name + ".json")).read_text()))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def request(core="individuals"):
    return {"mode": "demonstration", "policy_id": core + "-illustrative-v1"}


@pytest.mark.parametrize(
    "core,name,count",
    [
        ("individuals", "individual_control", 7),
        ("businesses", "business_profitable_cash_tension", 9),
    ],
)
def test_assessment_api_persistence_history_and_acl(
    client, url, auth_headers, monkeypatch, core, name, count
):
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "true")
    case_id = create(client, name, core)
    path = f"/{core}/{case_id}"
    original = client.get(path).json()
    response = client.post(path + "/assessments", json=request(core))
    assert response.status_code == 201, response.text
    data = response.json()
    assert len(data["result"]["sections"]) == count
    assert data["result"]["scoring"]["combined_score"] is None
    assert data["input_sha256"] and data["report_sha256"] and data["policy_snapshot"]
    assert data["evidence_snapshot"]
    assessment = "/assessments/" + data["id"]
    assert client.get(assessment).json() == data
    before = client.get(assessment).json()
    changed = deepcopy(original["data"])
    changed["name"] = "Dossier modifié après analyse"
    assert (
        client.put(
            path, json=changed, headers={"If-Match": str(client.get(path).json()["version"])}
        ).status_code
        == 200
    )
    assert client.get(assessment).json() == before
    assert client.get(path + "/assessments").json()[0]["id"] == data["id"]
    text = client.get(assessment + "/report")
    assert text.status_code == 200 and "Décision du prêteur" in text.text
    b = {"Authorization": "Bearer synthetic-b"}
    assert client.get(assessment, headers=b).status_code == 404
    assert client.get(assessment + "/report", headers=b).status_code == 404
    assert client.get(path + "/assessments", headers=b).status_code == 404
    app = create_app(url)
    with TestClient(app, headers=auth_headers) as restarted:
        assert restarted.get(assessment).json() == before
    app.state.engine.dispose()


def test_demo_interlocks_and_real_no_policy(client, monkeypatch):
    case_id = create(client)
    path = f"/individuals/{case_id}/assessments"
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "false")
    assert client.post(path, json=request()).status_code == 403
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "true")
    assert client.post(path, json={**request(), "mode": "real"}).status_code == 422
    response = client.post(path, json={"mode": "real"})
    assert response.status_code == 201
    assert response.json()["result"]["scoring"]["criteria_score"] is None
    raw = client.get(f"/individuals/{case_id}").json()["data"]
    raw["data_classification"] = "real"
    # La classification est immuable ; créer un vrai dossier plutôt que réétiqueter le dossier synthétique.
    assert (
        client.put(
            f"/individuals/{case_id}",
            json=raw,
            headers={"If-Match": str(client.get(f"/individuals/{case_id}").json()["version"])},
        ).status_code
        == 409
    )
    real_id = client.post("/individuals", json=raw).json()["id"]
    assert client.post(f"/individuals/{real_id}/assessments", json=request()).status_code == 422
    assert client.post(path, json={**request(), "model_score": 99}).status_code == 422


def test_simulations_immutable_linked_and_chiffrées(client, monkeypatch):
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "true")
    case_id = create(client)
    path = f"/individuals/{case_id}"
    original = client.get(path).json()
    parent = client.post(path + "/assessments", json=request()).json()
    historical = client.get("/assessments/" + parent["id"]).json()
    response = client.post(
        "/assessments/" + parent["id"] + "/simulations",
        json={"specification": {"kind": "lower_amount", "principal": "192000"}},
    )
    assert response.status_code == 201, response.text
    alternative = response.json()
    assert alternative["parent_id"] == parent["id"]
    assert alternative["result"]["comparisons"][0]["minimum_margin_after"] == "86000.00"
    assert alternative["input_snapshot"]["requested_loan"]["principal"]["value"] == "192000"
    assert client.get(path).json() == original
    assert client.get("/assessments/" + parent["id"]).json() == historical
    response = client.post(
        "/assessments/" + parent["id"] + "/simulations",
        json={
            "specification": {
                "kind": "stress",
                "scenario": {"name": "Contrôle -20%", "revenue_drop": "0.20"},
            }
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["result"]["comparisons"][0]["minimum_margin_before"] == "70000.00"
    assert data["result"]["comparisons"][0]["minimum_margin_after"] == "-30000.00"
    assert data["result"]["scoring"]["mandatory_review"]
    assert data["result"]["scoring"]["combined_score"] is None
    assert (
        client.post(
            "/assessments/" + parent["id"] + "/simulations",
            headers={"Authorization": "Bearer synthetic-b"},
            json={"specification": {"kind": "lower_amount", "principal": "192000"}},
        ).status_code
        == 404
    )


def test_full_term_projection_requirement_and_cost(client, monkeypatch):
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "true")
    case_id = create(client)
    parent = client.post(f"/individuals/{case_id}/assessments", json=request()).json()
    response = client.post(
        "/assessments/" + parent["id"] + "/simulations",
        json={"specification": {"kind": "extend_term", "months": 12}},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["result"]["status"] == "needs_explicit_projections"
    assert result["result"]["financial_comparison"] is None
    assert result["result"]["terms"]["after"]["total_repayment"] == "240000.00"
    assert client.get("/assessments/" + result["id"]).status_code == 200
    assert "Simulation incomplète" in client.get("/assessments/" + result["id"] + "/report").text
    assert (
        client.post(
            "/assessments/" + parent["id"] + "/simulations",
            json={"specification": {"kind": "extend_term", "months": 37}},
        ).status_code
        == 422
    )


def test_document_review_explicit_binding_not_first_candidate(client, monkeypatch):
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "true")
    raw = json.loads((ROOT / "individual_control.json").read_text())
    # Déplacer le dossier vers les périodes du spécimen d'octobre, sans changer les montants.
    months = {
        f"2026-{i:02d}-01": day
        for i, day in zip(
            range(2, 8),
            ["2026-10-01", "2026-11-01", "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01"],
        )
    }
    for period in raw["periods"]:
        period["period"] = months[period["period"]]
    for loan in raw["existing_loans"] + [raw["requested_loan"]]:
        for payment in loan["schedule"]:
            payment["due_date"] = months[payment["period"]]
            payment["period"] = months[payment["period"]]
    for expense in raw["analysis_details"]["expenses"]:
        expense["period"] = months[expense["period"]]
    raw["analysis_details"]["as_of"] = "2026-11-04"
    case_id = client.post("/individuals", json=raw).json()["id"]
    case_path = f"/individuals/{case_id}"
    before = client.get(case_path).json()
    doc = client.post(
        case_path + "/submissions",
        json={"document_type": "payslip", "role": "revenu", "period": "2026-10-01"},
    ).json()
    path = case_path + "/submissions/" + doc["id"]
    assert (
        client.post(
            path + "/sources", content=Path("examples/scans/salary.png").read_bytes()
        ).status_code
        == 201
    )
    assert client.post(path + "/confirm").status_code == 200
    processed = client.post(path + "/process").json()
    run_path = path + "/runs/" + processed["latest_run_id"]
    result = client.get(run_path).json()["extraction"]
    net = result["fields"]["net_income"]["candidates"][0]
    period = result["fields"]["period"]["candidates"][0]
    reviewed = client.post(
        run_path + "/reviews",
        json={
            "decisions": {
                "net_income": {
                    "value": {"amount": "280000", "currency": "XOF", "unit_multiplier": "1"},
                    "evidence_ids": [net["evidence_id"]],
                    "reason": "Montant contrôlé sur le spécimen synthétique.",
                },
                "period": {
                    "value": "2026-10-01",
                    "evidence_ids": [period["evidence_id"]],
                    "reason": "Mois d’octobre contrôlé sur la zone source.",
                },
            }
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    review_id = reviewed.json()["id"]
    binding = {
        "review_id": review_id,
        "field": "net_income",
        "target_path": "periods.0.incomes.0.net",
        "expected_period": "2026-10-01",
    }
    response = client.post(
        case_path + "/assessments", json={**request(), "validated_sources": [binding]}
    )
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["input_snapshot"]["periods"][0]["incomes"][0]["net"]["value"] == "280000"
    assert report["human_validations"][0]["reviewer"] == "agent-a"
    assert report["evidence_snapshot"][-1]["source_locations"]
    assert client.get(case_path).json() == before
    assert (
        client.post(
            case_path + "/assessments",
            json={**request(), "validated_sources": [{**binding, "expected_period": "2026-11-01"}]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            case_path + "/assessments", json={**request(), "validated_sources": [binding, binding]}
        ).status_code
        == 422
    )
    # L'extraction et la revue n'ont pas alimenté le dossier : sans binding, la valeur reste déclarée 500000.
    unbound = client.post(case_path + "/assessments", json=request()).json()
    assert unbound["input_snapshot"]["periods"][0]["incomes"][0]["net"]["value"] == "500000"

    # Édition liée à l’analyse : transcription revue, preuve et auteur sont conservés.
    import fitz

    edition = client.post(
        case_path + "/print/editions",
        json={
            "template_id": "income_expenses",
            "audience": "analyst",
            "assessment_id": report["id"],
        },
    ).json()
    assert edition["status"] == "completed"
    printed = client.get("/print-editions/" + edition["id"] + "/pdf").content
    with fitz.open(stream=printed, filetype="pdf") as pdf:
        printed_text = "\n".join(page.get_text() for page in pdf)
    assert "280 000,00" in printed_text.replace("\u202f", " ")
    assert review_id in printed_text
    assert "agent-a" in printed_text
    assert client.get(case_path).json() == before


def test_simulation_chain_keeps_active_stress(client, monkeypatch):
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "true")
    case_id = create(client)
    parent = client.post(f"/individuals/{case_id}/assessments", json=request()).json()
    stressed = client.post(
        "/assessments/" + parent["id"] + "/simulations",
        json={"specification": {"kind": "stress", "scenario": {"revenue_drop": "0.20"}}},
    ).json()
    lower = client.post(
        "/assessments/" + stressed["id"] + "/simulations",
        json={"specification": {"kind": "lower_amount", "principal": "192000"}},
    )
    assert lower.status_code == 201, lower.text
    comparison = lower.json()["result"]["comparisons"][0]
    assert comparison["minimum_margin_before"] == "-30000.00"
    assert comparison["minimum_margin_after"] == "-14000.00"
    assert lower.json()["options"]["_active_scenario"]["revenue_drop"] == "0.20"
