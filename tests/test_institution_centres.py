"""Consoles, offres et boîte client : preuves synthétiques, aucun établissement réel."""

import base64
import json
from copy import deepcopy
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from credit.institutions.models import BankDecisionRecord, ClientMessage, InstitutionAccount
from credit.web.application import create_web_app
from test_partners import portal as partner_portal  # noqa: F401
from test_partners import ready, confirm, post, headers


@pytest.fixture
def portal(request):
    return request.getfixturevalue("partner_portal")


def received(c):
    path, p, a, r, t = ready(c)
    t, _ = confirm(c, t)
    t = post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant").json()
    t = post(
        c,
        "/bank/transmissions/" + t["id"] + "/events",
        {
            "expected_revision": t["revision"],
            "action": "received",
            "reason": "Réception synthétique confirmée.",
        },
        "bank",
        "receipt-event",
    ).json()
    return path, p, r, t


def terms():
    return {
        "reference": "OFFRE-SYNTHETIQUE-2030",
        "product": "Crédit test amortissable",
        "principal": "120000",
        "currency": "XOF",
        "annual_nominal_rate": "0",
        "months": 3,
        "disbursement_date": "2030-01-01",
        "first_due_date": "2030-02-01",
        "fee_per_payment": "100",
        "upfront_fees": "200",
        "insurance_cost": "300",
        "insurance": "Assurance synthétique chiffrée séparément.",
        "collateral": "Aucune garantie pour cet essai synthétique.",
        "disbursement_conditions": "Acceptation de l’offre par le demandeur.",
        "payment_method": "Prélèvement fictif aux dates indiquées.",
        "early_repayment": "Sans frais selon ces conditions de test.",
        "late_payment": "Aucune pénalité pour cet exemple.",
        "validity_until": "2030-12-31",
        "signatory_name": "Responsable fictif",
        "signatory_function": "Responsable des engagements",
    }


def bank_key(c):
    ring = json.loads(c.ring.read_text())
    key = Ed25519PrivateKey.generate()
    path = c.ring.parent / "bank-key.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)
    ring["keys"].append(
        {
            "id": "bank-demo",
            "status": "active",
            "purpose": "demonstration",
            "issuer_ids": ["bank-one"],
            "private_key_path": str(path),
            "public_key_base64": base64.b64encode(
                key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
            ).decode(),
        }
    )
    c.ring.write_text(json.dumps(ring))


def body_for(c, t, mode="detached"):
    body = {
        "expected_revision": t["revision"],
        "decision": "approved",
        "public_reason": "Conditions examinées et accord d’offre synthétique.",
        "signature_mode": mode,
        "terms": terms(),
    }
    preview = post(c, "/bank/transmissions/" + t["id"] + "/decision-preview", body, "bank")
    assert preview.status_code == 200, preview.text
    assert preview.json()["terms"]["total_due"] == "120800.00"
    assert preview.json()["terms"]["total_credit_cost"] == "800.00"
    body["preview_sha256"] = preview.json()["terms_sha256"]
    return body


def test_signed_offer_pdf_client_inbox_and_immutable_history(portal):
    c = portal
    _, _, _, t = received(c)
    bank_key(c)
    original = body_for(c, t)
    r = post(
        c,
        "/bank/transmissions/" + t["id"] + "/decision",
        original,
        "bank",
        "decision-" + str(uuid4()),
    )
    assert r.status_code == 201, r.text
    agreement = r.json()
    assert agreement["verification"]["status"] == "valid"
    message = c.get("/inbox", headers=headers("applicant")).json()[0]
    assert message["decision_id"] == agreement["id"]
    pdf = c.get("/agreements/" + agreement["id"] + "/pdf", headers=headers("applicant"))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    import fitz

    text = "".join(page.get_text() for page in fitz.open(stream=pdf.content, filetype="pdf"))
    assert "120800.00" in text and "120000" in text and "NON SIGNÉ" not in text
    assert "DÉMONSTRATION" in text and "Attestation" in text
    preview = c.get("/agreements/" + agreement["id"] + "/preview", headers=headers("applicant"))
    assert preview.status_code == 200
    assert (
        c.get(
            "/agreements/" + agreement["id"] + "/pdf", headers=headers("other_applicant")
        ).status_code
        == 404
    )
    assert (
        c.get(
            "/bank/agreements/" + agreement["id"] + "/pdf", headers=headers("other_bank")
        ).status_code
        == 404
    )
    public = c.get("/public/bank-agreements/" + agreement["verification_url"].split("=")[-1]).json()
    assert public["status"] == "valid"
    assert set(public) == {"issuer", "id", "date", "status", "third_party_certification"}
    assert public["third_party_certification"] is False and "120000" not in json.dumps(public)
    revoked = post(
        c,
        "/bank/agreements/" + agreement["id"] + "/revoke",
        {"reason": "Annulation synthétique justifiée."},
        "bank",
    )
    assert revoked.status_code == 200
    assert (
        c.get("/agreements/" + agreement["id"] + "/pdf", headers=headers("applicant")).content
        == pdf.content
    )
    assert (
        c.get("/public/bank-agreements/" + agreement["verification_url"].split("=")[-1]).json()[
            "status"
        ]
        == "revoked"
    )
    assert len(c.get("/inbox", headers=headers("applicant")).json()) == 2


def test_refusal_idempotence_and_bank_isolation(portal):
    c = portal
    _, _, _, t = received(c)
    body = {
        "expected_revision": t["revision"],
        "decision": "refused",
        "public_reason": "Refus synthétique documenté pour ce dossier.",
    }
    url = "/bank/transmissions/" + t["id"] + "/decision"
    key = "refusal-" + str(uuid4())
    assert post(c, url, body, "other_bank", key).status_code == 404
    first = post(c, url, body, "bank", key)
    assert first.status_code == 201, first.text
    assert post(c, url, body, "bank", key).json()["id"] == first.json()["id"]
    assert (
        post(
            c,
            url,
            {**body, "public_reason": "Un autre motif ne peut remplacer le premier."},
            "bank",
            key,
        ).status_code
        == 409
    )
    assert post(c, url, body, "applicant", key).status_code == 403
    assert (
        c.get(
            "/agreements/" + first.json()["id"] + "/pdf", headers=headers("applicant")
        ).status_code
        == 404
    )
    assert c.get("/inbox", headers=headers("other_applicant")).json() == []
    with c.factory() as db:
        assert len(db.query(BankDecisionRecord).all()) == 1
        assert len(db.query(ClientMessage).all()) == 1


def test_missing_signature_preview_and_unsigned_explicit(portal):
    c = portal
    _, _, _, t = received(c)
    body = body_for(c, t)
    url = "/bank/transmissions/" + t["id"] + "/decision"
    assert post(c, url, body, "bank", "signed-" + str(uuid4())).status_code == 503
    assert c.get("/inbox", headers=headers("applicant")).json() == []
    changed = deepcopy(body)
    changed["terms"]["principal"] = "240000"
    assert post(c, url, changed, "bank", "changed-" + str(uuid4())).status_code == 409
    body["signature_mode"] = "unsigned"
    result = post(c, url, body, "bank", "unsigned-" + str(uuid4()))
    assert result.status_code == 201, result.text
    assert result.json()["verification"]["status"] == "unsigned"
    assert (
        "NON SIGNÉE"
        in c.get(
            "/agreements/" + result.json()["id"] + "/preview", headers=headers("applicant")
        ).text
    )


def test_pdf_failure_rolls_back_decision_and_tampering_is_detected(portal, monkeypatch):
    c = portal
    _, _, _, t = received(c)
    body = body_for(c, t, "unsigned")
    from credit.institutions import agreements

    renderer = agreements.render_isolated

    def fail(*args):
        raise RuntimeError("Synthetic PDF failure")

    monkeypatch.setattr(agreements, "render_isolated", fail)
    failed = post(
        c, "/bank/transmissions/" + t["id"] + "/decision", body, "bank", "failure-" + str(uuid4())
    )
    assert failed.status_code == 500
    assert "Synthetic PDF failure" not in failed.text
    assert c.get("/inbox", headers=headers("applicant")).json() == []
    monkeypatch.setattr(agreements, "render_isolated", renderer)
    result = post(
        c, "/bank/transmissions/" + t["id"] + "/decision", body, "bank", "retry-" + str(uuid4())
    ).json()
    with c.factory() as db:
        item = db.get(BankDecisionRecord, result["id"])
        item.payload = b"altered"
        item.sha256 = __import__("hashlib").sha256(b"altered").hexdigest()
        db.commit()
    assert (
        c.get("/agreements/" + result["id"] + "/pdf", headers=headers("applicant")).status_code
        == 409
    )


def test_admin_managed_accounts_activation_reset_and_deletion(portal, monkeypatch):
    c = portal
    _, p, _, _ = received(c)
    url = "/institution-admin/partners/" + p["id"] + "/accounts"
    data = {
        "username": "bank-agent@example.test",
        "professional_name": "Agent synthétique",
        "function": "Chargé des dossiers",
        "role": "bank_agent",
    }
    assert post(c, url, data, "applicant").status_code == 403
    assert post(c, url, {**data, "role": "administrator"}).status_code == 422
    result = post(c, url, data)
    assert result.status_code == 201, result.text
    account = result.json()
    assert "password" not in account
    assert c.get(url, headers=headers("admin")).json()[0]["username"] == data["username"]
    origin = "http://127.0.0.1:8000"
    monkeypatch.setenv("CREDIT_WEB_ORIGIN", origin)
    web = create_web_app(str(c.app.state.engine.url))
    password = "Synthetic-bank-access-2030!"
    try:
        with TestClient(web, base_url=origin, headers={"Origin": origin}) as browser:
            token = account["activation_url"].split("#")[-1]
            activation = {"token": token, "password": password, "password_confirmation": password}
            assert browser.post("/auth/activate", json=activation).status_code == 200
            assert browser.post("/auth/activate", json=activation).status_code == 400
            assert (
                browser.post(
                    "/auth/login", json={"username": data["username"], "password": password}
                ).status_code
                == 200
            )
            assert browser.get("/auth/session").json()["user"]["role"] == "bank_agent"
            assert len(browser.get("/api/bank/inbox").json()) == 1
            with c.factory() as db:
                revision = db.get(InstitutionAccount, account["id"]).revision
            reset = post(
                c,
                "/institution-admin/accounts/" + account["id"] + "/reset",
                {"expected_revision": revision},
            )
            assert reset.status_code == 200
            assert browser.get("/auth/session").status_code == 401
            removed = c.patch(
                "/institution-admin/accounts/" + account["id"],
                json={"expected_revision": reset.json()["revision"], "status": "deleted"},
                headers=headers("admin"),
            )
            assert removed.status_code == 200
            assert (
                browser.post(
                    "/auth/activate",
                    json={**activation, "token": reset.json()["activation_url"].split("#")[-1]},
                ).status_code
                == 400
            )
    finally:
        web.state.api.state.engine.dispose()


def test_metrics_permissions_and_analysis_scope(portal):
    c = portal
    _, _, _, t = received(c)
    result = c.get("/institution-admin/metrics", headers=headers("admin"))
    assert result.status_code == 200
    data = result.json()
    assert data["counters"]["cases"] == 1 and data["counters"]["transmissions"] == 1
    assert c.get("/institution-admin/metrics", headers=headers("applicant")).status_code == 403
    report = c.get("/bank/transmissions/" + t["id"] + "/analysis", headers=headers("bank"))
    assert report.status_code == 200 and len(report.json()["report"]["sections"]) > 1
    assert (
        c.get(
            "/bank/transmissions/" + t["id"] + "/analysis", headers=headers("other_bank")
        ).status_code
        == 404
    )
    assert (
        c.get(
            "/bank/transmissions/" + t["id"] + "/analysis", headers=headers("applicant")
        ).status_code
        == 403
    )


def test_rate_percent_zero_and_explicit_schedule_are_exact():
    from decimal import Decimal
    from pydantic import ValidationError
    from credit.institutions.contracts import AgreementTerms
    from credit.institutions.agreements import normalized_terms

    raw = terms()
    raw.pop("annual_nominal_rate")
    raw.update(
        annual_rate_percent="12",
        principal="100000",
        months=1,
        fee_per_payment="200",
        upfront_fees="300",
        insurance_cost="400",
    )
    result = normalized_terms(AgreementTerms.model_validate(raw))
    assert result["annual_nominal_rate"] == "0.12"
    assert (
        result["total_interest"] == "1000.00"
        and result["total_credit_cost"] == "1900.00"
        and result["total_due"] == "101900.00"
    )
    assert sum(Decimal(x["principal"]) for x in result["schedule"]) == Decimal("100000")
    explicit = terms()
    explicit.update(
        months=2,
        schedule=[
            {"date": "2030-02-01", "principal": "60000", "interest": "0", "fees": "100"},
            {"date": "2030-05-01", "principal": "60000", "interest": "0", "fees": "200"},
        ],
    )
    assert normalized_terms(AgreementTerms.model_validate(explicit))["total_due"] == "120800"
    explicit["schedule"][1]["principal"] = "59999.99"
    with pytest.raises(ValidationError):
        AgreementTerms.model_validate(explicit)
    with pytest.raises(ValidationError):
        AgreementTerms.model_validate({**terms(), "principal": 120000.0})


def test_archive_preserves_transmissions_and_blocks_new_bank_events(portal):
    c = portal
    _, p, _, t = received(c)
    archived = c.request(
        "DELETE",
        "/institution-admin/partners/" + p["id"],
        json={"expected_revision": p["version"]},
        headers=headers("admin"),
    )
    assert archived.status_code == 200
    assert c.get("/bank/transmissions/" + t["id"], headers=headers("bank")).status_code == 200
    assert (
        post(
            c,
            "/bank/transmissions/" + t["id"] + "/events",
            {
                "expected_revision": t["revision"],
                "action": "under_review",
                "reason": "Tentative après archivage de l’établissement.",
            },
            "bank",
            "archived-" + str(uuid4()),
        ).status_code
        == 409
    )
    assert post(c, "/partners/admin/banks/" + p["id"] + "/test").status_code == 409


def test_analysis_tampering_and_stale_account_versions_are_refused(portal):
    from credit.persistence import AssessmentRecord

    c = portal
    _, p, r, t = received(c)
    with c.factory() as db:
        item = db.get(AssessmentRecord, r["assessment_id"])
        data = deepcopy(item.data)
        data["result"]["summary"] = "Altération synthétique interdite."
        item.data = data
        db.commit()
    assert (
        c.get("/bank/transmissions/" + t["id"] + "/analysis", headers=headers("bank")).status_code
        == 409
    )
    result = post(
        c,
        "/institution-admin/partners/" + p["id"] + "/accounts",
        {
            "username": "revision.bank",
            "professional_name": "Test banque",
            "function": "Chargé de crédit",
            "role": "bank_agent",
        },
    ).json()
    response = c.patch(
        "/institution-admin/accounts/" + result["id"],
        json={"expected_revision": result["revision"] + 1, "role": "bank_manager"},
        headers=headers("admin"),
    )
    assert response.status_code == 409


def test_admin_review_queue_claims_are_scoped_versioned_and_audited(portal):
    from credit.persistence import CaseRecord
    from credit.partners.models import CaseGrant, PartnerEvent
    from sqlalchemy import select

    c = portal
    case_path, _, _, t = received(c)
    case_id = t["case_id"]
    with c.factory() as db:
        record = db.get(CaseRecord, case_id)
        # L'admin n'obtient pas une autorisation implicite par la lecture de la file.
        grant = db.get(CaseGrant, (case_id, "admin"))
        if grant:
            db.delete(grant)
        record.owner_id = "applicant"
        version = record.lock_version
        db.commit()
        version = record.lock_version
    assert c.get(case_path, headers=headers("admin")).status_code == 404
    queue = c.get("/institution-admin/review-cases", headers=headers("admin"))
    assert queue.status_code == 200
    row = next(x for x in queue.json()["items"] if x["id"] == case_id)
    assert row["kind"] == "individuals" and row["analysis_count"] >= 1
    assert "data" not in row and "payload" not in row
    assert c.get("/institution-admin/review-cases", headers=headers("applicant")).status_code == 403
    assert (
        c.get("/institution-admin/review-cases?limit=1000", headers=headers("admin")).status_code
        == 422
    )
    assert (
        post(
            c,
            "/institution-admin/review-cases/" + case_id + "/claim",
            {"expected_revision": version + 1},
        ).status_code
        == 409
    )
    claimed = post(
        c, "/institution-admin/review-cases/" + case_id + "/claim", {"expected_revision": version}
    )
    assert claimed.status_code == 200
    assert c.get(case_path, headers=headers("admin")).status_code == 200
    assert (
        post(
            c,
            "/institution-admin/review-cases/" + case_id + "/claim",
            {"expected_revision": version},
        ).status_code
        == 200
    )
    with c.factory() as db:
        events = db.scalars(
            select(PartnerEvent).where(PartnerEvent.action == "admin_review_claimed")
        ).all()
        assert len(events) == 1
        record = db.get(CaseRecord, case_id)
        record.institution_id = "other-institution"
        db.commit()
    assert not c.get("/institution-admin/review-cases", headers=headers("admin")).json()["items"]
    assert (
        post(
            c,
            "/institution-admin/review-cases/" + case_id + "/claim",
            {"expected_revision": version},
        ).status_code
        == 404
    )
