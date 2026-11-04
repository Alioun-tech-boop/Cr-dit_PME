"""Oracles chiffrés indépendants et scénarios d’abus locaux synthétiques."""

from copy import deepcopy
from datetime import date
from decimal import Decimal as D, localcontext
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
import fitz
import pytest
from pydantic import ValidationError

from credit.api import create_app
from credit.businesses.contracts import BusinessCase
from credit.businesses.engine import analyze as business_analyze
from credit.individuals.contracts import IndividualCase
from credit.individuals.engine import analyze
from credit.assessment.engines import IndividualAnalysisEngine
from credit.shared.contracts import Amount, Scenario
from credit.shared.schedule import monthly_schedule
from credit.shared.normalization import effective_case
from credit.security.files import antimalware
from credit.documents.isolation import Runner, WorkerError
from credit.documents.policy import configuration

CONTROL = Path("examples/assessments/individual_control.json")


def create(client):
    r = client.post("/individuals", json=json.loads(CONTROL.read_text()))
    assert r.status_code == 201, r.text
    return "/individuals/" + r.json()["id"]


def grant(registry, path, **changes):
    config = json.loads(registry.read_text())
    config["users"][1].update(case_ids=[path.split("/")[-1]], **changes)
    registry.write_text(json.dumps(config))
    return {"Authorization": "Bearer synthetic-b"}


def test_reference_individual_and_stress():
    case = IndividualCase.model_validate_json(CONTROL.read_text())
    assert analyze(case).periods[0].available_before_debt == D(200000)
    assert analyze(case).periods[0].margin_after_credit == D(70000)
    assert analyze(case, Scenario(revenue_drop=D(".20"))).periods[0].margin_after_credit == D(
        -30000
    )


def test_reference_business_independent(business):
    business["periods"] = business["periods"][:1]
    p = business["periods"][0]
    for key in ["taxes", "essential_investments", "household_withdrawals"]:
        p[key] = {"value": "0", "state": "known"}
    p.update(
        receipts={"value": "4000000", "state": "known"},
        operating_expenses={"value": "3000000", "state": "known"},
        requested_loan_disbursement={"value": "400000", "state": "known"},
        financed_uses={"value": "400000", "state": "known"},
    )
    for loan, capital in [
        (business["existing_loans"][0], "250000"),
        (business["requested_loan"], "400000"),
    ]:
        loan["principal"] = {"value": capital, "state": "known"}
        loan["schedule"] = [
            {
                "period": p["period"],
                "principal": {"value": capital, "state": "known"},
                "interest": {"value": "0", "state": "known"},
                "fees": {"value": "0", "state": "known"},
            }
        ]
    business["opening_cash"] = {"value": "0", "state": "known"}
    result = business_analyze(BusinessCase.model_validate(business))
    assert result.periods[0].cash_available_for_debt == D(1000000)
    assert result.periods[0].margin_after_debt == D(350000)
    assert result.periods[0].debt_service_coverage == D(20) / D(13)
    assert result.periods[0].closing_cash == D(350000)


@pytest.mark.parametrize("increment", [0, 1, 17, 10000, 70000, 100000])
def test_margin_monotonic_in_debt_and_income(increment):
    raw = json.loads(CONTROL.read_text())
    raw["requested_loan"]["amortization_method"] = "explicit"
    raw["requested_loan"]["principal"]["value"] = str(240000 + increment)
    raw["requested_loan"]["schedule"][0]["principal"]["value"] = str(80000 + increment)
    assert analyze(IndividualCase.model_validate(raw)).periods[0].margin_after_credit == D(
        70000 - increment
    )
    raw = json.loads(CONTROL.read_text())
    raw["periods"][0]["incomes"][0]["net"]["value"] = str(500000 - increment)
    assert analyze(IndividualCase.model_validate(raw)).periods[0].margin_after_credit == D(
        70000 - increment
    )


@pytest.mark.parametrize("months", [1, 3, 12, 60, 600])
@pytest.mark.parametrize("rate", ["0", ".12", ".50"])
def test_repaid_principal_property(months, rate):
    loan = monthly_schedule(D("100000.03"), D(rate), months, date(2026, 1, 31), D("17.13"))
    assert sum(p.principal.value for p in loan.schedule) == D("100000.03")
    assert all(p.principal.value >= 0 and p.interest.value >= 0 for p in loan.schedule)
    assert all(p.fees.value == D("17.13") for p in loan.schedule)


def test_extra_essential_costs_same_on_both_engines_and_idempotent():
    raw = json.loads(CONTROL.read_text())
    raw["analysis_details"]["expenses"].append(
        {
            "period": "2026-02-01",
            "category": "health",
            "frequency": "future",
            "included_in_total": False,
            "amount": {"value": "10000", "state": "known"},
        }
    )
    case = IndividualCase.model_validate(raw)
    before = case.model_dump_json()
    assert analyze(case).periods[0].margin_after_credit == D(60000)
    assert IndividualAnalysisEngine().calculate(case).periods[0].margin_after_credit == D(60000)
    normalized, _ = effective_case(case)
    twice, _ = effective_case(normalized)
    assert twice == normalized
    assert case.model_dump_json() == before


def test_precision_is_independent_of_calling_context(business):
    case = BusinessCase.model_validate(business)
    original = business_analyze(case).model_dump_json()
    with localcontext() as ctx:
        from decimal import Inexact

        ctx.prec = 8
        ctx.traps[Inexact] = True
        assert business_analyze(case).model_dump_json() == original
        assert Amount(value="12345678901234567890.11").value == D("12345678901234567890.11")
        assert sum(
            p.principal.value
            for p in monthly_schedule(D(100000), D(0), 3, date(2026, 1, 1)).schedule
        ) == D(100000)


def test_unknown_schedule_and_delayed_unknown_revenue_not_zero():
    raw = json.loads(CONTROL.read_text())
    raw["requested_loan"].update(
        principal={"value": None, "state": "unknown"}, schedule=[], amortization_method="explicit"
    )
    result = analyze(IndividualCase.model_validate(raw))
    assert result.status == "incomplete" and result.periods[0].margin_after_credit is None
    raw = json.loads(CONTROL.read_text())
    raw["periods"][0]["incomes"][0]["net"] = {"value": None, "state": "unknown"}
    result = analyze(
        IndividualCase.model_validate(raw),
        Scenario(delay_from=date(2026, 2, 1), delay_to=date(2026, 3, 1), delay_amount=D(10000)),
    )
    assert result.periods[1].net_retained_income is None


def test_extreme_amount_rates_and_sensitive_mass_assignment_rejected(client):
    path = create(client)
    for field, value in [
        ("role", "administrator"),
        ("institution_id", "other"),
        ("score", 100),
        ("decision", "approved"),
    ]:
        raw = json.loads(CONTROL.read_text())
        raw[field] = value
        response = client.post("/individuals", json=raw)
        assert response.status_code == 422
        assert "input" not in response.json()["detail"][0]
    with pytest.raises(ValidationError):
        Scenario(expense_increase="1e100")
    with pytest.raises(ValueError):
        monthly_schedule(D(100000), D("1e100"), 12, date(2026, 1, 1))
    assert client.get(path).status_code == 200


def test_applicant_cannot_leak_analyse_or_write_internal_fields(client, local_identities):
    path = create(client)
    r = client.get(path).json()
    raw = r["data"]
    raw["record_details"]["internal_observations"] = "SECRET_INTERNAL"
    assert client.put(path, json=raw, headers={"If-Match": str(r["version"])}).status_code == 200
    other = grant(local_identities, path)
    assert "SECRET_INTERNAL" not in client.get(path, headers=other).text
    analysis = client.post(path + "/assessments", json={"mode": "real"}).json()
    for endpoint in [
        "/assessments/" + analysis["id"],
        "/assessments/" + analysis["id"] + "/report",
        path + "/assessments",
        path + "/analyses",
    ]:
        assert client.get(endpoint, headers=other).status_code == 403
    assert client.post(path + "/analyses", headers=other).status_code == 403
    r = client.get(path, headers=other).json()
    raw = r["data"]
    raw["name"] = "Demande mise à jour"
    assert (
        client.put(path, json=raw, headers={**other, "If-Match": str(r["version"])}).status_code
        == 200
    )
    assert (
        client.get(path).json()["data"]["record_details"]["internal_observations"]
        == "SECRET_INTERNAL"
    )
    raw["record_details"]["internal_observations"] = "injected"
    assert (
        client.put(path, json=raw, headers={**other, "If-Match": str(r["version"] + 1)}).status_code
        == 403
    )


def test_forged_document_validation_and_classification_rejected(client):
    path = create(client)
    current = client.get(path).json()
    raw = deepcopy(current["data"])
    raw["evidence"][0].update(status="verified", review_id="forged")
    assert (
        client.put(path, json=raw, headers={"If-Match": str(current["version"])}).status_code == 422
    )
    raw = deepcopy(current["data"])
    raw["data_classification"] = "real"
    assert (
        client.put(path, json=raw, headers={"If-Match": str(current["version"])}).status_code == 409
    )


def test_stale_updates_and_idempotent_old_report(client):
    path = create(client)
    original = client.get(path).json()
    report = client.post(path + "/print/editions", json={"template_id": "identification"}).json()
    pdf = client.get("/print-editions/" + report["id"] + "/pdf").content
    assert client.put(path, json=original["data"]).status_code == 428
    changed = deepcopy(original["data"])
    changed["name"] = "Modification A"
    assert (
        client.put(path, json=changed, headers={"If-Match": str(original["version"])}).status_code
        == 200
    )
    changed["name"] = "Écrasement périmé"
    assert (
        client.put(path, json=changed, headers={"If-Match": str(original["version"])}).status_code
        == 409
    )
    assert client.get(path).json()["data"]["name"] == "Modification A"
    assert client.get("/print-editions/" + report["id"] + "/pdf").content == pdf
    assert client.post("/print-editions/" + report["id"] + "/process").status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("expires_at", "2020-01-01T00:00:00+00:00"),
        ("revoked_at", "2026-01-01T00:00:00Z"),
        ("disabled", True),
    ],
)
def test_revoked_expired_disabled_tokens(client, local_identities, field, value):
    registry = json.loads(local_identities.read_text())
    registry["users"][0][field] = value
    local_identities.write_text(json.dumps(registry))
    assert client.get("/documents/catalog").status_code == 401
    assert client.get("/health").status_code == 200


def test_limits_hosts_and_auth_failure_throttle(url, auth_headers, monkeypatch):
    monkeypatch.setenv("CREDIT_MAX_JSON_BYTES", "100")
    monkeypatch.setenv("CREDIT_RATE_AUTH_FAILURES", "2")
    app = create_app(url)
    with TestClient(app, headers=auth_headers) as client:
        assert (
            client.post(
                "/individuals", content=b" " * 101, headers={"content-type": "application/json"}
            ).status_code
            == 413
        )
        assert (
            client.get("/documents/catalog", headers={"Host": "untrusted.invalid"}).status_code
            == 400
        )
        for _ in range(2):
            assert (
                client.get(
                    "/documents/catalog", headers={"Authorization": "Bearer invalid"}
                ).status_code
                == 401
            )
        assert (
            client.get(
                "/documents/catalog", headers={"Authorization": "Bearer invalid"}
            ).status_code
            == 429
        )
    app.state.engine.dispose()


def test_internal_document_visibility_old_tasks_and_cross_institution(client, local_identities):
    path = create(client)
    sid = client.post(
        path + "/submissions",
        json={
            "document_type": "payslip",
            "role": "internal",
            "period": "2026-02-01",
            "visibility": "analyst",
        },
    ).json()["id"]
    other = grant(local_identities, path)
    assert client.get(path + "/submissions/" + sid, headers=other).status_code == 404
    assert client.get(path + "/submissions", headers=other).json() == []
    assert client.post(path + "/submissions/" + sid + "/cancel", headers=other).status_code == 404
    grant(local_identities, path, institution_id="foreign")
    assert client.get(path, headers=other).status_code == 404
    assert client.get(path + "/submissions/" + sid, headers=other).status_code == 404


def test_administrative_events_are_scoped_and_not_financial(client, local_identities):
    path = create(client)
    assert client.get("/security/events").status_code == 403
    registry = json.loads(local_identities.read_text())
    registry["users"][0]["role"] = "institution_manager"
    local_identities.write_text(json.dumps(registry))
    response = client.get("/security/events")
    assert response.status_code == 200 and response.json()
    assert "500000" not in response.text and "synthetic-a" not in response.text
    assert client.get("/security/events?limit=10000").status_code == 422
    assert client.get(path + "/assessments?limit=10000").status_code == 422


def test_production_fails_closed_without_security_configuration(monkeypatch):
    monkeypatch.setenv("CREDIT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        create_app("sqlite://")


def test_antimalware_unavailable_detected_and_failure(monkeypatch):
    monkeypatch.setattr("credit.security.files.shutil.which", lambda _: None)
    assert antimalware(b"synthetic")["status"] == "not_scanned"
    monkeypatch.setenv("CREDIT_ANTIMALWARE_REQUIRED", "true")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        antimalware(b"synthetic")
    assert exc.value.status_code == 503
    monkeypatch.setattr("credit.security.files.shutil.which", lambda _: "/usr/bin/clamscan")
    with patch(
        "credit.security.files.subprocess.run", return_value=subprocess.CompletedProcess([], 1)
    ):
        with pytest.raises(HTTPException) as exc:
            antimalware(b"EICAR synthetic marker")
        assert exc.value.status_code == 422


def test_synthetic_active_pdf_is_not_executed_and_not_marked_safe(client):
    path = create(client)
    sid = client.post(
        path + "/submissions",
        json={"document_type": "bank_statement", "role": "synthetic", "period": "2026-02-01"},
    ).json()["id"]
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((60, 80), "RELEVE BANCAIRE SYNTHETIQUE - aucun JavaScript execute")
    xref = pdf.get_new_xref()
    pdf.update_object(xref, '<< /S /JavaScript /JS (app.alert("SYNTHETIC_DO_NOT_EXECUTE")) >>')
    pdf.xref_set_key(pdf.pdf_catalog(), "OpenAction", f"{xref} 0 R")
    response = client.post(path + "/submissions/" + sid + "/sources", content=pdf.tobytes())
    assert response.status_code == 201, response.text
    assert "SYNTHETIC_DO_NOT_EXECUTE" not in response.text
    assert response.json()["security_checks"][0]["antimalware"]["status"] == "not_scanned"


def test_runner_cancellation_kills_only_owned_task():
    policy, _ = configuration()
    limits = deepcopy(policy["limits"])
    limits["timeout_seconds"] = 5
    runner = Runner(limits)
    observed = []

    def execute():
        try:
            runner.run("sleep_for_test", {"task_key": "synthetic-owned-job", "seconds": 4})
        except WorkerError as exc:
            observed.append(str(exc))

    thread = threading.Thread(target=execute)
    thread.start()
    deadline = time.monotonic() + 3
    while not runner.active and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not runner.cancel("other-task")
    assert runner.cancel("synthetic-owned-job")
    thread.join(timeout=3)
    assert not thread.is_alive() and observed == ["processing_cancelled"]


def test_atomic_auth_management_on_synthetic_registry(tmp_path):
    registry = tmp_path / "users.json"
    registry.write_text(
        json.dumps(
            {"users": [{"id": "synthetic", "token_sha256": hashlib.sha256(b"old").hexdigest()}]}
        )
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/manage_local_auth.py",
            "rotate",
            "--registry",
            str(registry),
            "--user",
            "synthetic",
        ],
        check=True,
        capture_output=True,
    )
    data = json.loads(registry.read_text())["users"][0]
    assert data["token_sha256"] != hashlib.sha256(b"old").hexdigest() and data["expires_at"]
    subprocess.run(
        [
            sys.executable,
            "scripts/manage_local_auth.py",
            "revoke",
            "--registry",
            str(registry),
            "--user",
            "synthetic",
        ],
        check=True,
        capture_output=True,
    )
    assert json.loads(registry.read_text())["users"][0]["revoked_at"]
    assert registry.stat().st_mode & 0o077 == 0
    assert "token_sha256" not in registry.with_suffix(".audit.jsonl").read_text()


def test_ocr_idempotence_and_stale_reviews(client, monkeypatch):
    path = create(client)
    sid = client.post(
        path + "/submissions",
        json={"document_type": "payslip", "role": "synthetic", "period": "2026-10-01"},
    ).json()["id"]
    sp = path + "/submissions/" + sid
    assert (
        client.post(
            sp + "/sources", content=Path("examples/scans/salary.png").read_bytes()
        ).status_code
        == 201
    )
    assert client.post(sp + "/confirm").status_code == 200
    first = client.post(sp + "/process").json()
    assert client.post(sp + "/process").json()["latest_run_id"] == first["latest_run_id"]
    run = sp + "/runs/" + first["latest_run_id"]
    extracted = client.get(run).json()["extraction"]
    evidence = extracted["fields"]["net_income"]["candidates"][0]["evidence_id"]
    decisions = {
        "net_income": {
            "value": {"amount": "280000", "currency": "XOF", "unit_multiplier": "1"},
            "evidence_ids": [evidence],
            "reason": "Transcription synthétique revue sur la page",
        }
    }
    old = client.post(run + "/reviews", json={"decisions": decisions}).json()
    assert client.post(run + "/reviews", json={"decisions": decisions}).status_code == 409
    updated = client.post(
        run + "/reviews", json={"decisions": decisions, "expected_review_revision": 1}
    )
    assert updated.status_code == 201, updated.text
    stale = client.post(
        path + "/assessments",
        json={
            "mode": "real",
            "validated_sources": [
                {
                    "review_id": old["id"],
                    "field": "net_income",
                    "target_path": "periods.0.incomes.0.net",
                    "expected_period": "2026-10-01",
                }
            ],
        },
    )
    assert stale.status_code == 422 and "périmée" in stale.text
    assert client.post(sp + "/reopen").status_code == 200
    assert (
        client.post(
            run + "/reviews", json={"decisions": decisions, "expected_review_revision": 2}
        ).status_code
        == 409
    )
    assert client.get(run).status_code == 200


def test_print_document_inventory_does_not_disclose_internal_piece(client, local_identities):
    path = create(client)
    sid = client.post(
        path + "/submissions",
        json={
            "document_type": "payslip",
            "role": "internal",
            "visibility": "analyst",
            "period": "2026-02-01",
        },
    ).json()["id"]
    other = grant(local_identities, path)
    preview = client.post(
        path + "/print/preview",
        json={"template_id": "documents", "audience": "applicant"},
        headers=other,
    )
    assert preview.status_code == 200
    assert sid not in preview.text


def test_errors_and_logs_do_not_disclose_financial_payload(client, monkeypatch, caplog):
    import logging

    path = create(client)

    def failure(*args, **kwargs):
        raise RuntimeError("FINANCIAL_PRIVATE_MARKER_500000")

    monkeypatch.setattr("credit.api.run_analysis", failure)
    with caplog.at_level(logging.INFO):
        response = client.post(path + "/analyses")
    assert response.status_code == 500
    assert "FINANCIAL_PRIVATE" not in response.text and "FINANCIAL_PRIVATE" not in caplog.text
    assert "Traceback" not in response.text


def test_chunked_body_and_host_confusion_do_not_bypass_security(url, auth_headers):
    app = create_app(url)
    with TestClient(app, headers=auth_headers) as client:

        def large():
            yield b"["
            for _ in range(25):
                yield b" " * 100000
            yield b"]"

        assert (
            client.post(
                "/individuals", content=large(), headers={"content-type": "application/json"}
            ).status_code
            == 413
        )
        assert (
            client.get("/documents/catalog", headers={"Host": "testserver/health#"}).status_code
            == 400
        )
        assert (
            client.get(
                "/documents/catalog",
                headers={"Host": "testserver/health#", "Authorization": "Bearer invalid"},
            ).status_code
            == 401
        )
    app.state.engine.dispose()


def test_idempotent_assessment_and_print_same_input_and_conflict(client):
    path = create(client)
    header = {"Idempotency-Key": "synthetic-retry-key"}
    first = client.post(path + "/assessments", json={"mode": "real"}, headers=header)
    second = client.post(path + "/assessments", json={"mode": "real"}, headers=header)
    assert first.status_code == 201 and first.json()["id"] == second.json()["id"]
    assert len(client.get(path + "/assessments").json()) == 1
    assert (
        client.post(
            path + "/assessments", json={"mode": "real", "stress_scenarios": []}, headers=header
        ).status_code
        == 409
    )
    body = {"template_id": "identification", "audience": "analyst"}
    first = client.post(path + "/print/editions", json=body, headers=header)
    second = client.post(path + "/print/editions", json=body, headers=header)
    assert first.status_code == 201 and first.json()["id"] == second.json()["id"]
    assert first.json()["pdf_sha256"] == second.json()["pdf_sha256"]
    original = client.get(path).json()
    raw = original["data"]
    raw["name"] = "Version après émission"
    assert (
        client.put(path, json=raw, headers={"If-Match": str(original["version"])}).status_code
        == 200
    )
    assert client.post(path + "/print/editions", json=body, headers=header).status_code == 409


def test_float_money_cannot_silently_lose_cents():
    from credit.shared.contracts import SignedAmount

    for cls in [Amount, SignedAmount]:
        with pytest.raises(ValidationError):
            cls(value=1234567890123456789.12)
        with pytest.raises(ValidationError):
            cls(value=True)
        assert cls(value="1234567890123456789.12").value == D("1234567890123456789.12")


def test_security_log_records_actor_and_date_without_token(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="credit.security"):
        assert client.get("/documents/catalog").status_code == 200
    entries = [json.loads(r.getMessage()) for r in caplog.records if r.name == "credit.security"]
    assert any(
        e["actor_id"] == "agent-a" and e["date"] and e["event"] == "authenticated" for e in entries
    )
    assert all("synthetic-a" not in json.dumps(e) for e in entries)


@pytest.mark.parametrize("value", [1.2, True, "not-a-number"])
def test_reviewed_transcription_still_requires_exact_business_decimal(value):
    from types import SimpleNamespace
    from credit.assessment.application import bind_reviewed_values
    from credit.persistence import ReviewRecord, DocumentRun, SubmissionRecord

    snapshot = json.loads(CONTROL.read_text())
    review = SimpleNamespace(
        id="review",
        run_id="run",
        data={
            "extraction": {"review_history": [{"field": "period", "value": "2026-02-01"}]},
            "decisions": {
                "net_income": {
                    "value": {"amount": value, "currency": "XOF", "unit_multiplier": "1"}
                }
            },
        },
    )
    run = SimpleNamespace(id="run", submission_id="sub", data={"revision": 1})
    sub = SimpleNamespace(
        case_id="case",
        case_kind="individuals",
        data={"period": "2026-02-01", "latest_run_id": "run", "revision": 1},
    )

    class Session:
        def get(self, cls, id):
            return {ReviewRecord: review, DocumentRun: run, SubmissionRecord: sub}[cls]

        def scalars(self, query):
            return SimpleNamespace(first=lambda: review)

    binding = SimpleNamespace(
        review_id="review",
        field="net_income",
        target_path="periods.0.incomes.0.net",
        expected_period=date(2026, 2, 1),
    )
    record = SimpleNamespace(id="case", kind="individuals")
    with pytest.raises(ValueError):
        bind_reviewed_values(Session(), record, snapshot, [binding])


def test_applicant_cannot_self_confirm_identity_or_verified_contribution(client, local_identities):
    path = create(client)
    other = grant(local_identities, path)
    case = client.get(path, headers=other).json()
    assert "identity" not in case["data"]["analysis_details"]
    raw = deepcopy(case["data"])
    raw["analysis_details"]["identity"] = {"subject_linked": False}
    assert (
        client.put(path, json=raw, headers={**other, "If-Match": str(case["version"])}).status_code
        == 403
    )
    raw = deepcopy(case["data"])
    raw["analysis_details"]["funding"]["verified_contribution"]["value"] = "999999"
    assert (
        client.put(path, json=raw, headers={**other, "If-Match": str(case["version"])}).status_code
        == 403
    )


def test_one_opaque_token_cannot_select_ambiguous_institutions(client, local_identities):
    config = json.loads(local_identities.read_text())
    config["users"][1]["token_sha256"] = config["users"][0]["token_sha256"]
    config["users"][1]["institution_id"] = "foreign"
    local_identities.write_text(json.dumps(config))
    assert client.get("/documents/catalog").status_code == 503
