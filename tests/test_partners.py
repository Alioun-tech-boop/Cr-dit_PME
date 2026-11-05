import base64
import hashlib
import json
import time
import hmac
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from credit.api import create_app
from credit.partners import signing
from credit.partners.models import Attestation, PacketFile, Outbox
from credit.persistence import now


def headers(user):
    return {"Authorization": "Bearer partner-" + user}


@pytest.fixture
def portal(url, local_identities, monkeypatch, tmp_path):
    roles = {
        "admin": ("administrator", "issuer"),
        "analyst": ("analyst", "issuer"),
        "manager": ("institution_manager", "issuer"),
        "manager2": ("institution_manager", "issuer"),
        "applicant": ("applicant", "issuer"),
        "other_applicant": ("applicant", "issuer"),
        "bank": ("bank_manager", "bank-one"),
        "other_bank": ("bank_manager", "bank-two"),
    }
    users = [
        {
            "id": id,
            "role": role,
            "institution_id": inst,
            "token_sha256": hashlib.sha256(("partner-" + id).encode()).hexdigest(),
            "case_ids": [],
        }
        for id, (role, inst) in roles.items()
    ]
    local_identities.write_text(json.dumps({"users": users}))
    monkeypatch.setenv("CREDIT_PARTNER_ALLOW_DEMO", "true")
    monkeypatch.setenv("CREDIT_ENV", "local")
    monkeypatch.setenv("CREDIT_RATE_REQUESTS", "10000")
    monkeypatch.setenv("CREDIT_RATE_ACTOR", "10000")
    monkeypatch.setenv("CREDIT_RATE_JOBS", "10000")
    key = Ed25519PrivateKey.generate()
    private = tmp_path / "sign.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private.chmod(0o600)
    ring = tmp_path / "keyring.json"
    ring.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "id": "demo-key",
                        "status": "active",
                        "purpose": "demonstration",
                        "issuer_ids": ["issuer"],
                        "private_key_path": str(private),
                        "public_key_base64": base64.b64encode(
                            key.public_key().public_bytes(
                                serialization.Encoding.Raw, serialization.PublicFormat.Raw
                            )
                        ).decode(),
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("CREDIT_PARTNER_KEYRING_FILE", str(ring))
    with TestClient(create_app(url)) as c:
        c.factory = c.app.state.session_factory
        c.ring = ring
        yield c


def post(c, path, body=None, user="admin", key=None):
    h = headers(user)
    if key:
        h["Idempotency-Key"] = key
    return c.post(path, json=body or {}, headers=h)


def setup(c, core="individuals", approvals=1, mode="portal", failures=0):
    p = {
        "issuer_name": "Institution fictive Crédit PME",
        "issuer_identity_statement": "Institution entièrement synthétique pour les essais locaux.",
        "scope": "Atteste uniquement la revue et la validation internes de cette version, sans engagement bancaire.",
        "demonstration": True,
        "signatories": [
            {
                "actor_id": id,
                "name": "Responsable " + id,
                "function": "Responsable des engagements synthétiques",
            }
            for id in ["manager", "manager2"]
        ],
        "reviewers": ["analyst"],
        "required_approvals": approvals,
        "allow_incomplete_with_reserves": True,
        "allow_deficits_with_reserves": True,
        "require_approved_financial_policy": False,
        "require_business_authority_evidence": False,
        "approved_reference": "Politique fictive approuvée pour démonstration",
        "legal_review_reference": "Vérification juridique fictive, aucun statut revendiqué",
    }
    r = c.put("/partners/admin/policy", json=p, headers=headers("admin"))
    assert r.status_code == 200, r.text
    cfg = {
        "bank_institution_id": "bank-one",
        "name": "Banque FICTIVE de démonstration",
        "presentation": "Banque inexistante, uniquement pour tester le parcours local.",
        "activity_scope": "Financements synthétiques au Burkina Faso",
        "cores": ["individuals", "businesses"],
        "profiles": ["employee", "structured_accounts"],
        "products": ["demo-monthly"],
        "demonstration": True,
        "information_updated_on": "2026-11-05",
        "processing_notice": "Étude fictive locale, aucune communication réelle ni promesse de financement.",
        "reception_mode": mode,
        "demo_failures": failures,
        "webhook_secret_env": "CREDIT_PARTNER_WEBHOOK_TEST",
    }
    r = post(c, "/partners/admin/banks", cfg)
    assert r.status_code == 201, r.text
    partner = r.json()
    r = post(c, "/partners/admin/banks/" + partner["id"] + "/test")
    assert r.status_code == 200, r.text
    ver = r.json()["version"]
    r = post(
        c,
        "/partners/admin/banks/" + partner["id"] + "/activate",
        {
            "expected_version": ver,
            "agreement_reference": "Accord fictif",
            "representative_verification_reference": "Représentants fictifs contrôlés",
            "data_sharing_reference": "Accord partage synthétique",
            "legal_review_reference": "Revue juridique de démonstration",
        },
    )
    assert r.status_code == 200, r.text
    partner = r.json()
    name = "individual_control" if core == "individuals" else "business_profitable_cash_tension"
    raw = json.loads(Path("examples/assessments/" + name + ".json").read_text())
    raw.setdefault("record_details", {})["internal_observations"] = (
        "NE_JAMAIS_TRANSMETTRE_CETTE_NOTE_INTERNE"
    )
    r = post(c, "/" + core, raw)
    assert r.status_code == 201, r.text
    path = "/" + core + "/" + r.json()["id"]
    r = post(
        c, path + "/banking/assign-applicant", {"actor_id": "applicant", "expected_case_version": 1}
    )
    assert r.status_code == 200, r.text
    version = r.json()["version"]
    r = post(c, path + "/banking/review-access", user="applicant")
    assert r.status_code == 200, r.text
    r = post(c, path + "/financial-analyses", user="analyst")
    assert r.status_code == 201, r.text
    analysis = r.json()
    r = post(
        c,
        path + "/internal-reviews",
        {"assessment_id": analysis["id"], "expected_case_version": version},
        "analyst",
        "review-1",
    )
    assert r.status_code == 201, r.text
    return path, partner, analysis, r.json()


def approve(c, review, user="manager"):
    r = post(
        c,
        "/internal-reviews/" + review["id"] + "/decisions",
        {
            "decision": "approve",
            "expected_revision": review["revision"],
            "reason": "Revue synthétique effectuée, limites examinées.",
            "public_reserves": "Données synthétiques ; informations incomplètes et limites à examiner par la banque.",
            "authorize_packet_preview": True,
        },
        user,
    )
    assert r.status_code == 200, r.text
    return r.json()


def issue(c, review):
    r = post(c, "/internal-reviews/" + review["id"] + "/attestation", user="manager")
    assert r.status_code == 201, r.text
    r = c.get("/internal-reviews/" + review["id"], headers=headers("applicant"))
    assert r.status_code == 200, r.text
    return r.json()


def prepare(c, path, partner, review, key="preview-1"):
    required = {
        "identification",
        "credit_request",
        "lender_report",
        "analysis_summary",
        "attestation",
    }
    body = {
        "partner_id": partner["id"],
        "review_id": review["id"],
        "file_ids": [f["id"] for f in review["files"] if f["category"] in required],
    }
    r = post(c, path + "/banking/previews", body, "applicant", key)
    assert r.status_code == 201, r.text
    return r.json(), body


def confirm(c, t):
    body = {
        "expected_revision": t["revision"],
        "manifest_sha256": t["manifest_sha256"],
        "attestation_id": t["attestation_id"],
        "consent_version": "bank-sharing-fr-v1",
        "accepted": True,
        "authority_statement": "Je suis le demandeur ou représentant déclaré habilité pour cette demande.",
    }
    r = post(c, "/transmissions/" + t["id"] + "/confirm", body, "applicant")
    assert r.status_code == 200, r.text
    return r.json(), body


@pytest.mark.parametrize("core", ["individuals", "businesses"])
def test_complete_portal_path_and_privacy(portal, core):
    c = portal
    path, p, a, r = setup(c, core)
    assert (
        c.get(
            "/internal-reviews/" + r["id"] + "/files/" + r["files"][0]["id"],
            headers=headers("applicant"),
        ).status_code
        == 403
    )
    # Une analyse terminée sans approbation ne permet pas de préparer l'envoi.
    res = post(
        c,
        path + "/banking/previews",
        {"partner_id": p["id"], "review_id": r["id"], "file_ids": [r["files"][0]["id"]]},
        "applicant",
        "before",
    )
    assert res.status_code == 409
    r = approve(c, r)
    assert r["state"] == "approved"
    r = issue(c, r)
    assert r["attestation"]["state"] == "valid"
    data = c.get(
        "/public/attestations/" + r["attestation"]["verification_url"].split("=")[-1]
    ).json()
    assert set(data) == {"issuer", "attestation_id", "date", "status"}
    assert "applicant" not in json.dumps(data) and "principal" not in json.dumps(data)
    t, preview = prepare(c, path, p, r)
    assert t["state"] == "ready"
    assert c.get("/bank/inbox", headers=headers("bank")).json() == []
    assert (
        c.get("/transmissions/" + t["id"] + "/events", headers=headers("applicant")).status_code
        == 200
    )
    assert (
        c.get(
            "/transmissions/" + t["id"] + "/events", headers=headers("other_applicant")
        ).status_code
        == 404
    )
    t, body = confirm(c, t)
    same = post(c, "/transmissions/" + t["id"] + "/confirm", body, "applicant")
    assert same.status_code == 200
    with c.factory() as s:
        assert len(s.query(Outbox).all()) == 1
    res = post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant")
    assert res.status_code == 200, res.text
    t = res.json()
    assert t["state"] == "transmitted" and t["decision"] is None
    inbox = c.get("/bank/inbox", headers=headers("bank"))
    assert len(inbox.json()) == 1
    assert c.get("/bank/inbox", headers=headers("other_bank")).json() == []
    assert c.get("/bank/transmissions/" + t["id"], headers=headers("other_bank")).status_code == 404
    assert c.get("/bank/transmissions/" + t["id"] + "/verify", headers=headers("bank")).json()[
        "valid"
    ]
    r = post(
        c,
        "/bank/transmissions/" + t["id"] + "/events",
        {
            "expected_revision": t["revision"],
            "action": "received",
            "reason": "Réception métier explicite de la version transmise.",
        },
        "bank",
        "received-1",
    )
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["state"] == "received"
    assert (
        post(
            c,
            "/bank/transmissions/" + t["id"] + "/events",
            {
                "expected_revision": t["revision"],
                "action": "additional_information",
                "reason": "Veuillez compléter les justificatifs.",
                "requested_information": ["Justificatif synthétique actualisé"],
            },
            "bank",
            "request-1",
        ).status_code
        == 200
    )
    archive = c.get("/bank/transmissions/" + t["id"] + "/archive", headers=headers("bank"))
    assert archive.status_code == 200, archive.text
    import zipfile
    import io
    import fitz

    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        names = z.namelist()
        assert "signature.json" in names and "sharing-manifest.json" in names
        for name in names:
            if name.endswith(".pdf"):
                with fitz.open(stream=z.read(name), filetype="pdf") as doc:
                    assert "NE_JAMAIS_TRANSMETTRE_CETTE_NOTE_INTERNE" not in "".join(
                        p.get_text() for p in doc
                    )
    assert c.get("/assessments/" + a["id"], headers=headers("analyst")).json() == a
    assert (
        c.get(
            "/bank/transmissions/" + t["id"] + "/archive", headers=headers("other_bank")
        ).status_code
        == 404
    )
    assert c.get("/individuals", headers=headers("bank")).status_code == 403


def ready(c, **options):
    path, p, a, r = setup(c, **options)
    r = approve(c, r)
    r = issue(c, r)
    t, b = prepare(c, path, p, r)
    return path, p, a, r, t


def test_roles_dual_validation_and_missing_signing_configuration(portal, monkeypatch):
    c = portal
    path, p, a, r = setup(c, approvals=2)
    body = {
        "decision": "approve",
        "expected_revision": r["revision"],
        "reason": "Motif explicite de test",
        "public_reserves": "Réserves de démonstration",
    }
    for who in ["applicant", "analyst", "other_applicant"]:
        assert post(c, "/internal-reviews/" + r["id"] + "/decisions", body, who).status_code in {
            403,
            404,
        }
    bad = {**body, "expected_revision": 999}
    assert post(c, "/internal-reviews/" + r["id"] + "/decisions", bad, "manager").status_code == 409
    r = approve(c, r)
    assert r["state"] == "second_validation"
    assert (
        post(c, "/internal-reviews/" + r["id"] + "/attestation", user="manager").status_code == 409
    )
    assert (
        post(
            c,
            "/internal-reviews/" + r["id"] + "/decisions",
            {**body, "expected_revision": r["revision"]},
            "manager",
        ).status_code
        == 409
    )
    r = approve(c, r, "manager2")
    assert r["state"] == "approved"
    monkeypatch.delenv("CREDIT_PARTNER_KEYRING_FILE")
    assert (
        post(c, "/internal-reviews/" + r["id"] + "/attestation", user="manager").status_code == 503
    )
    monkeypatch.setenv("CREDIT_ENV", "production")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        signing.signing_key("issuer", False)
    assert error.value.status_code == 503


def test_case_modification_requires_new_analysis_and_keeps_old_files(portal):
    c = portal
    path, p, a, r, t = ready(c)
    f = r["files"][0]
    before = c.get(
        "/internal-reviews/" + r["id"] + "/files/" + f["id"], headers=headers("applicant")
    ).content
    payload = c.get(path, headers=headers("admin")).json()
    payload["data"]["name"] = "Nom synthétique modifié"
    changed = c.put(
        path,
        json=payload["data"],
        headers={**headers("admin"), "If-Match": str(payload["version"])},
    )
    assert changed.status_code == 200, changed.text
    state = c.get(path + "/banking", headers=headers("applicant")).json()
    assert state["internal_state"] == "superseded" and not state["partners"]
    public = c.get("/public/attestations/" + r["attestation"]["verification_url"].split("=")[-1])
    assert public.json()["status"] == "replaced"
    assert (
        c.get(
            "/internal-reviews/" + r["id"] + "/files/" + f["id"], headers=headers("applicant")
        ).content
        == before
    )
    assert c.get("/assessments/" + a["id"], headers=headers("analyst")).json() == a
    assert (
        post(c, "/internal-reviews/" + r["id"] + "/attestation", user="manager").status_code == 409
    )
    assert (
        post(
            c,
            path + "/internal-reviews",
            {"assessment_id": a["id"], "expected_case_version": changed.json()["version"]},
            "analyst",
            "stale-analysis",
        ).status_code
        == 409
    )
    body = {
        "expected_revision": t["revision"],
        "manifest_sha256": t["manifest_sha256"],
        "attestation_id": t["attestation_id"],
        "consent_version": "bank-sharing-fr-v1",
        "accepted": True,
        "authority_statement": "Demandeur synthétique habilité",
    }
    assert post(c, "/transmissions/" + t["id"] + "/confirm", body, "applicant").status_code == 409


def test_confirmation_integrity_wrong_bank_and_no_automatic_sharing(portal):
    c = portal
    path, p, a, r, t = ready(c)
    assert c.get("/transmissions/" + t["id"], headers=headers("other_applicant")).status_code == 404
    assert c.get("/bank/transmissions/" + t["id"], headers=headers("bank")).status_code == 404
    body = {
        "expected_revision": t["revision"],
        "manifest_sha256": "0" * 64,
        "attestation_id": t["attestation_id"],
        "consent_version": "bank-sharing-fr-v1",
        "accepted": True,
        "authority_statement": "Demandeur synthétique habilité",
    }
    assert post(c, "/transmissions/" + t["id"] + "/confirm", body, "applicant").status_code == 409
    body["manifest_sha256"] = t["manifest_sha256"]
    body["accepted"] = False
    assert post(c, "/transmissions/" + t["id"] + "/confirm", body, "applicant").status_code == 422
    t, _ = confirm(c, t)
    post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant")
    f = t["manifest"]["files"][0]
    with c.factory() as s:
        file = s.get(PacketFile, f["id"])
        original = file.payload
        file.payload = original + b" altered"
        s.commit()
    assert (
        c.get("/bank/transmissions/" + t["id"] + "/verify", headers=headers("bank")).json()["valid"]
        is False
    )
    assert (
        c.get("/bank/transmissions/" + t["id"] + "/archive", headers=headers("bank")).status_code
        == 409
    )
    assert (
        c.get(
            "/bank/transmissions/" + t["id"] + "/files/" + f["id"], headers=headers("bank")
        ).status_code
        == 409
    )
    with c.factory() as s:
        file = s.get(PacketFile, f["id"])
        file.payload = original
        s.commit()
    assert c.get("/bank/transmissions/" + t["id"] + "/verify", headers=headers("bank")).json()[
        "valid"
    ]
    with c.factory() as s:
        att = s.get(Attestation, r["attestation"]["id"])
        data = deepcopy(att.data)
        data["envelope"]["core"]["applicant_name"] = "Altération"
        att.data = data
        s.commit()
    assert (
        c.get("/bank/transmissions/" + t["id"] + "/verify", headers=headers("bank")).json()["valid"]
        is False
    )


def test_retry_idempotence_and_distinct_receipt(portal, monkeypatch):
    c = portal
    path, p, a, r, t = ready(c, mode="api_demo", failures=1)
    t, body = confirm(c, t)
    response = post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant")
    assert response.json()["state"] == "pending"
    assert c.get("/bank/inbox", headers=headers("bank")).json() == []
    with c.factory() as s:
        job = s.query(Outbox).filter_by(transmission_id=t["id"]).one()
        assert job.attempts == 1
        job.due_at = now() - timedelta(seconds=1)
        s.commit()
    sent = post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant").json()
    assert sent["state"] == "transmitted" and sent["decision"] is None
    again = post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant").json()
    assert again["external_id"] == sent["external_id"]
    with c.factory() as s:
        job = s.query(Outbox).filter_by(transmission_id=t["id"]).one()
        assert job.attempts == 2 and len(job.data["attempts"]) == 2
    assert c.get("/bank/transmissions/" + t["id"] + "/verify", headers=headers("bank")).json()[
        "valid"
    ]


@pytest.mark.parametrize("stage", ["before", "after"])
def test_withdraw_before_and_after_delivery(portal, stage):
    c = portal
    path, p, a, r, t = ready(c)
    t, _ = confirm(c, t)
    if stage == "after":
        post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant")
    response = post(
        c,
        "/transmissions/" + t["id"] + "/withdraw",
        {"reason": "Retrait explicitement demandé pour essai."},
        "applicant",
    )
    assert response.status_code == 200
    assert response.json()["state"] == ("withdrawn" if stage == "after" else "cancelled")
    assert (
        post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant").json()["state"]
        == response.json()["state"]
    )
    inbox = c.get("/bank/inbox", headers=headers("bank")).json()
    assert len(inbox) == (1 if stage == "after" else 0)
    if stage == "after":
        assert (
            c.get(
                "/bank/transmissions/" + t["id"] + "/archive", headers=headers("bank")
            ).status_code
            == 200
        )


def test_expiry_revocation_and_key_rotation(portal, monkeypatch):
    from credit.partners import service

    c = portal
    path, p, a, r, t = ready(c)
    token = r["attestation"]["verification_url"].split("=")[-1]
    real_now = now()
    monkeypatch.setattr(service, "now", lambda: real_now + timedelta(days=31))
    assert c.get("/public/attestations/" + token).json()["status"] == "expired"
    monkeypatch.setattr(service, "now", now)
    ring = json.loads(c.ring.read_text())
    ring["keys"][0]["status"] = "retired"
    c.ring.write_text(json.dumps(ring))
    assert c.get("/public/attestations/" + token).json()["status"] == "valid"
    ring["keys"][0]["status"] = "revoked"
    c.ring.write_text(json.dumps(ring))
    assert c.get("/public/attestations/" + token).json()["status"] == "revoked"
    ring["keys"][0]["status"] = "retired"
    c.ring.write_text(json.dumps(ring))
    assert (
        post(
            c,
            "/attestations/" + r["attestation"]["id"] + "/revoke",
            {"reason": "Révocation synthétique autorisée."},
            "manager",
        ).status_code
        == 200
    )
    assert c.get("/public/attestations/" + token).json()["status"] == "revoked"


def test_webhook_hmac_replay_and_out_of_order(portal, monkeypatch):
    c = portal
    path, p, a, r, t = ready(c)
    t, _ = confirm(c, t)
    t = post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant").json()
    monkeypatch.setenv("CREDIT_PARTNER_WEBHOOK_TEST", "synthetic-webhook-secret-not-real")
    body = {
        "event_id": "received",
        "transmission_id": t["id"],
        "sequence": 2,
        "event": {
            "expected_revision": t["revision"],
            "action": "received",
            "reason": "Réception bancaire synthétique contrôlée",
        },
    }
    # Signer le contrat normalisé, y compris les valeurs par défaut documentées.
    from credit.partners.contracts import Webhook

    def send(value, signature=True, stamp=None):
        body = Webhook.model_validate(value).model_dump(mode="json")
        ts = str(stamp or int(time.time()))
        sig = (
            hmac.new(
                b"synthetic-webhook-secret-not-real",
                ts.encode() + b"." + signing.canonical(body),
                hashlib.sha256,
            ).hexdigest()
            if signature
            else "bad"
        )
        return c.post(
            "/bank/webhooks/" + p["id"],
            json=body,
            headers={**headers("bank"), "X-Timestamp": ts, "X-Signature": sig},
        )

    assert send(body, False).status_code == 401
    assert send(body, True, int(time.time()) - 1000).status_code == 401
    result = send(body)
    assert result.status_code == 200, result.text
    same = send(body)
    assert same.status_code == 200 and same.json()["event_id"] == result.json()["event_id"]
    late = deepcopy(body)
    late["event_id"] = "older"
    late["sequence"] = 1
    ignored = send(late)
    assert ignored.status_code == 200 and ignored.json()["result"] == "ignored_out_of_order"
    assert ignored.json()["transmission"]["state"] == "received"
    wrong = deepcopy(body)
    wrong["event"]["reason"] = "Contenu contradictoire réutilisant cet identifiant"
    assert send(wrong).status_code == 409


def test_inactive_partner_and_render_failure_block_incomplete_packet(portal, monkeypatch):
    c = portal
    path, p, a, r = setup(c)
    current = approve(c, r)
    current = issue(c, current)
    status = post(
        c,
        "/partners/admin/banks/" + p["id"] + "/status",
        {
            "status": "suspended",
            "reason": "Suspension synthétique contrôlée",
            "expected_version": p["version"],
        },
    )
    assert status.status_code == 200, status.text
    response = post(
        c,
        path + "/banking/previews",
        {
            "partner_id": p["id"],
            "review_id": current["id"],
            "file_ids": [f["id"] for f in current["files"]],
        },
        "applicant",
        "disabled",
    )
    assert response.status_code == 409
    monkeypatch.setattr(
        "credit.partners.packets.render_isolated",
        lambda model: (_ for _ in ()).throw(ValueError("synthetic_failure")),
    )
    before = len(c.get(path + "/banking", headers=headers("applicant")).json()["reviews"])
    response = post(
        c,
        path + "/internal-reviews",
        {"assessment_id": a["id"], "expected_case_version": current["case_version"]},
        "analyst",
        "failed-generation",
    )
    assert response.status_code == 422
    assert len(c.get(path + "/banking", headers=headers("applicant")).json()["reviews"]) == before


def test_bank_complements_and_formal_offer_are_explicit(portal):
    c = portal
    path, p, a, r, t = ready(c)
    t, _ = confirm(c, t)
    t = post(c, "/transmissions/" + t["id"] + "/dispatch", user="applicant").json()
    prefix = "/bank/transmissions/" + t["id"]
    owner = "/transmissions/" + t["id"]
    t = post(
        c,
        prefix + "/events",
        {
            "expected_revision": t["revision"],
            "action": "received",
            "reason": "Prise en charge métier confirmée.",
        },
        "bank",
        "receipt",
    ).json()
    t = post(
        c,
        prefix + "/events",
        {
            "expected_revision": t["revision"],
            "action": "additional_information",
            "reason": "Pièce actualisée nécessaire.",
            "requested_information": ["Document synthétique actualisé"],
        },
        "bank",
        "more",
    ).json()
    original = Path("modules/credit_pme_pdf/examples/pdf/credit_application.pdf").read_bytes()
    bad = c.post(
        owner + "/attachments",
        content=b"not a PDF",
        headers={**headers("applicant"), "Content-Type": "application/pdf"},
    )
    assert bad.status_code == 422, bad.text
    assert (
        c.post(
            owner + "/attachments",
            content=b"x" * 5_000_001,
            headers={**headers("applicant"), "Content-Type": "application/pdf"},
        ).status_code
        == 413
    )
    f = c.post(
        owner + "/attachments",
        content=original,
        headers={**headers("applicant"), "Content-Type": "image/png"},
    )
    assert f.status_code == 201, f.text
    id = f.json()["id"]
    assert f.json()["inspection"]["authenticity_status"] == "not_assessed"
    same = c.post(
        owner + "/attachments",
        content=original,
        headers={**headers("applicant"), "Content-Type": "application/pdf"},
    )
    assert same.json()["id"] == id
    assert c.get(prefix + "/attachments/" + id, headers=headers("bank")).status_code == 404
    body = {
        "expected_revision": t["revision"],
        "reason": "Complément synthétique demandé par la banque",
        "attachment_ids": [id],
        "accepted": True,
    }
    result = post(c, owner + "/supplements", body, "applicant", "supplement-1")
    assert result.status_code == 201, result.text
    assert c.get(prefix + "/attachments/" + id, headers=headers("bank")).content == original
    assert (
        c.get(
            "/bank/transmissions/" + t["id"] + "/attachments/" + id, headers=headers("other_bank")
        ).status_code
        == 404
    )
    assert post(c, owner + "/supplements", body, "applicant", "supplement-1").status_code == 201
    t = result.json()
    uploaded = c.post(
        prefix + "/attachments",
        content=original,
        headers={**headers("bank"), "Content-Type": "application/pdf"},
    )
    assert uploaded.status_code == 201, uploaded.text
    bank_file = uploaded.json()["id"]
    assert (
        c.get(owner + "/attachments/" + bank_file, headers=headers("applicant")).status_code == 404
    )
    decision = {
        "expected_revision": t["revision"],
        "action": "decision",
        "reason": "Offre formelle synthétique attachée pour démonstration.",
        "decision": "formal_offer",
        "external_reference": "DEMO-OFFRE-001",
        "attachment_ids": [bank_file],
    }
    result = post(c, prefix + "/events", decision, "bank", "formal-offer")
    assert result.status_code == 200, result.text
    assert result.json()["decision"]["kind"] == "formal_offer"
    assert (
        c.get(owner + "/attachments/" + bank_file, headers=headers("applicant")).content == original
    )
    assert c.get("/assessments/" + a["id"], headers=headers("analyst")).json() == a
    backwards = {
        **decision,
        "expected_revision": result.json()["revision"],
        "decision": "conditional_offer",
    }
    assert post(c, prefix + "/events", backwards, "bank", "older-offer").status_code == 409


def test_document_change_invalidates_approval_and_does_not_touch_packet(portal):
    from credit.persistence import SubmissionRecord

    c = portal
    path, p, a, r, t = ready(c)
    old = r["files"][0]
    pdf = c.get(
        "/internal-reviews/" + r["id"] + "/files/" + old["id"], headers=headers("applicant")
    ).content
    # Même règle pour une nouvelle pièce ou une modification de pièce existante.
    with c.factory() as s:
        s.add(
            SubmissionRecord(
                case_id=path.split("/")[-1],
                case_kind="individuals",
                data={"document_type": "identity_card", "deposit_status": "draft"},
            )
        )
        s.commit()
    response = c.get(path + "/banking", headers=headers("applicant"))
    assert response.status_code == 200, response.text
    assert response.json()["internal_state"] == "superseded"
    assert response.json()["reviews"][0]["attestation"]["state"] == "replaced"
    assert (
        c.get(
            "/internal-reviews/" + r["id"] + "/files/" + old["id"], headers=headers("applicant")
        ).content
        == pdf
    )


def test_review_version_idempotency_and_production_partner_gates(portal):
    c = portal
    path, p, a, r = setup(c)
    current = c.get(path, headers=headers("admin")).json()
    stale = post(
        c,
        path + "/internal-reviews",
        {"assessment_id": a["id"], "expected_case_version": current["version"] - 1},
        "analyst",
        "old-version",
    )
    assert stale.status_code == 409
    repeat = post(
        c,
        path + "/internal-reviews",
        {"assessment_id": a["id"], "expected_case_version": current["version"]},
        "analyst",
        "review-1",
    )
    assert repeat.status_code == 201 and repeat.json()["id"] == r["id"]
    other = post(
        c,
        path + "/internal-reviews",
        {
            "assessment_id": a["id"],
            "expected_case_version": current["version"],
            "source_ids": ["fake"],
        },
        "analyst",
        "review-1",
    )
    assert other.status_code == 409
    # Le schéma du partenaire refuse toute destination URL arbitraire et tout statut imposé.
    from credit.partners.contracts import PartnerInput
    from pydantic import ValidationError

    cfg = c.app.state.session_factory
    with cfg() as s:
        config = s.get(
            __import__("credit.partners.models", fromlist=["Partner"]).Partner, p["id"]
        ).data["configuration"]
    assert post(c, "/partners/admin/banks", config, "applicant").status_code == 403
    with pytest.raises(ValidationError):
        PartnerInput.model_validate({**config, "url": "http://127.0.0.1/private"})
    with pytest.raises(ValidationError):
        PartnerInput.model_validate({**config, "status": "active"})


def test_postgres_concurrent_delivery_is_claimed_once(portal, url):
    if not url.startswith("postgresql"):
        pytest.skip("Vérification des verrous PostgreSQL uniquement")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from credit.partners.delivery import dispatch

    c = portal
    path, p, a, r, t = ready(c)
    t, _ = confirm(c, t)
    barrier = Barrier(2)

    def execute():
        with c.factory() as session:
            barrier.wait(timeout=5)
            result = dispatch(session, t["id"])
            return result.state

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(pool.map(lambda _: execute(), range(2)))
    with c.factory() as session:
        row = session.query(Outbox).filter_by(transmission_id=t["id"]).one()
        assert row.state == "completed" and row.attempts == 1
        assert len(row.data["attempts"]) == 1
    assert "transmitted" in states


def test_postgres_changed_case_during_delivery_does_not_publish(portal, url, monkeypatch):
    if not url.startswith("postgresql"):
        pytest.skip("Vérification des transactions PostgreSQL uniquement")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from credit.partners.delivery import dispatch
    from credit.partners.connectors import CONNECTORS, PortalConnector
    from credit.persistence import CaseRecord

    c = portal
    path, p, a, r, t = ready(c)
    t, _ = confirm(c, t)
    entered, proceed = Event(), Event()
    original = PortalConnector()

    class Delayed:
        def deliver(self, request, **kwargs):
            entered.set()
            assert proceed.wait(timeout=10)
            return original.deliver(request, **kwargs)

    monkeypatch.setitem(CONNECTORS, "portal", Delayed())

    def execute():
        with c.factory() as session:
            return dispatch(session, t["id"]).state

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute)
        assert entered.wait(timeout=5)
        with c.factory() as session:
            case = session.get(CaseRecord, path.split("/")[-1])
            case.payload = {**case.payload, "name": "Cas synthétique changé pendant traitement"}
            session.commit()
        proceed.set()
        state = future.result(timeout=15)
    assert state != "transmitted"
    assert c.get("/bank/inbox", headers=headers("bank")).json() == []


def test_outbox_worker_command_processes_confirmed_request(portal, url):
    import os
    import subprocess
    import sys

    c = portal
    path, p, a, r, t = ready(c)
    t, _ = confirm(c, t)
    process = subprocess.run(
        [sys.executable, "-m", "scripts.partner_worker", "--once"],
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr.decode()
    status = c.get("/transmissions/" + t["id"], headers=headers("applicant")).json()
    assert status["state"] == "transmitted" and status["decision"] is None
    assert len(c.get("/bank/inbox", headers=headers("bank")).json()) == 1
