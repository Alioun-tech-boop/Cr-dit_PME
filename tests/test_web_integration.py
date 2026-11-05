"""Parcours réels sur base isolée : cookies, CSRF, brouillons, publications et objets."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from credit.persistence import Base, WebUser, WebSession, CaseRecord
from credit.web.application import PASSWORDS, create_web_app

ORIGIN = "http://testserver"
PASSWORD = "Synthétique-test-2026!"


@pytest.fixture
def web(url, monkeypatch):
    users = [
        {
            "id": x,
            "token_sha256": hashlib.sha256(x.encode()).hexdigest(),
            "role": "analyst" if x == "analyst" else "applicant",
            "institution_id": "other" if x == "outsider" else "bank",
            "case_ids": [],
        }
        for x in ("applicant", "analyst", "neighbour", "outsider")
    ]
    monkeypatch.setenv("CREDIT_AUTH_JSON", json.dumps({"users": users}))
    monkeypatch.delenv("CREDIT_AUTH_FILE", raising=False)
    monkeypatch.setenv("CREDIT_WEB_ORIGIN", ORIGIN)
    monkeypatch.setenv("CREDIT_RATE_REQUESTS", "10000")
    monkeypatch.setenv("CREDIT_RATE_ACTOR", "10000")
    app = create_web_app(url)
    Base.metadata.create_all(app.state.api.state.engine)
    with app.state.session_factory() as db:
        for user in users:
            db.add(
                WebUser(
                    actor_id=user["id"],
                    username=user["id"],
                    password_hash=PASSWORDS.hash(PASSWORD),
                    profile={},
                )
            )
        db.commit()
    yield app, users
    app.state.api.state.engine.dispose()


def login(app, username="applicant"):
    c = TestClient(app, headers={"Origin": ORIGIN})
    r = c.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert "HttpOnly" in r.headers["set-cookie"] and "SameSite=lax" in r.headers["set-cookie"]
    assert "token" not in r.json() and "password" not in r.text
    c.headers["X-CSRF-Token"] = c.get("/auth/csrf").json()["token"]
    return c


def payload(core):
    name = "individual_control" if core == "individuals" else "business_seasonal"
    data = json.loads(Path(f"examples/assessments/{name}.json").read_text())
    data["data_classification"] = "real"
    data.get("analysis_details", {}).pop("identity", None)
    data["analysis_details"]["funding"]["verified_contribution"] = None
    data.get("record_details", {}).pop("internal_observations", None)
    return data


@pytest.mark.parametrize("core", ["individuals", "businesses"])
def test_journey_case_resume_conflicts_and_isolation(web, core):
    app, _ = web
    c = login(app)
    body = {
        "kind": core,
        "draft": {"core": core, "form": {"name": "Nom synthétique"}, "periods": []},
    }
    headers = {"Idempotency-Key": "draft-synthetic-key-123"}
    r = c.post("/api/journeys", json=body, headers=headers)
    assert r.status_code == 201, r.text
    draft = r.json()
    assert c.post("/api/journeys", json=body, headers=headers).json()["id"] == draft["id"]
    assert c.get("/api/journeys").json()[0]["draft"]["form"]["name"] == "Nom synthétique"
    url = "/api/journeys/" + draft["id"]
    assert c.put(url, json=body).status_code == 428
    updated = c.put(
        url,
        json={**body, "draft": {**body["draft"], "step": 2}},
        headers={"If-Match": str(draft["version"])},
    )
    assert updated.status_code == 200
    assert c.put(url, json=body, headers={"If-Match": str(draft["version"])}).status_code == 409
    version = updated.json()["version"]
    result = c.post(
        url + "/case", json={"payload": payload(core)}, headers={"If-Match": str(version)}
    )
    assert result.status_code == 200, result.text
    case = result.json()
    # Même POST après réponse perdue : aucune deuxième création.
    assert (
        c.post(
            url + "/case", json={"payload": payload(core)}, headers={"If-Match": str(version)}
        ).json()["id"]
        == case["id"]
    )
    assert len(c.get("/api/" + core).json()) == 1
    c2 = login(app)
    assert c2.get(url).json()["case_id"] == case["id"]
    for username in ("neighbour", "outsider"):
        stranger = login(app, username)
        assert stranger.get(url).status_code == 404
        assert stranger.get("/api/" + core + "/" + case["id"]).status_code == 404
        assert (
            stranger.get("/api/" + core + "/" + case["id"] + "/published-assessment").status_code
            == 404
        )
        assert stranger.get("/api/" + core).json() == []
    assert c.post("/api/" + core + "/" + case["id"] + "/assessments", json={}).status_code == 403


def test_csrf_login_logout_profile_revocation_and_expiration(web):
    app, users = web
    c = TestClient(app)
    assert (
        c.post("/auth/login", json={"username": "applicant", "password": PASSWORD}).status_code
        == 403
    )
    c = login(app)
    assert (
        c.patch(
            "/auth/profile",
            json={"display_name": "François", "email": "x@example.test", "telephone": "+226 00"},
        ).status_code
        == 200
    )
    assert c.get("/auth/session").json()["user"]["display_name"] == "François"
    assert c.patch("/auth/profile", json={"role": "administrator"}).status_code == 422
    assert (
        c.patch(
            "/auth/profile", json={"display_name": "", "email": "invalid", "telephone": ""}
        ).status_code
        == 422
    )
    token = c.headers.pop("X-CSRF-Token")
    assert c.post("/auth/logout").status_code == 403
    assert c.post("/api/journeys", json={}).status_code == 403
    c.headers["X-CSRF-Token"] = token
    c.headers["Origin"] = "https://evil.invalid"
    assert c.post("/auth/logout").status_code == 403
    c.headers["Origin"] = ORIGIN
    old = c.cookies.get("credit_session")
    assert c.post("/auth/logout").status_code == 204
    c.cookies.set("credit_session", old)
    assert c.get("/auth/session").status_code == 401
    c = login(app)
    with app.state.session_factory() as db:
        item = db.scalar(select(WebSession).where(WebSession.actor_id == "applicant"))
        item.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert c.get("/auth/session").status_code == 401
    assert c.get("/api/journeys").status_code == 401


@pytest.mark.parametrize("core", ["individuals", "businesses"])
def test_analysis_publication_and_private_reports(web, core):
    app, users = web
    owner = login(app)
    case = owner.post("/api/" + core, json=payload(core)).json()
    case_id = case["id"]
    original_periods = case["data"]["periods"]
    # Attribution administrative explicite dans le registre serveur, jamais via le navigateur.
    users[1]["case_ids"] = [case_id]
    import os

    os.environ["CREDIT_AUTH_JSON"] = json.dumps({"users": users})
    analyst = login(app, "analyst")
    result = analyst.post("/api/" + core + "/" + case_id + "/assessments", json={"mode": "real"})
    assert result.status_code == 201, result.text
    report = result.json()
    assert len(report["result"]["sections"]) == (7 if core == "individuals" else 9)
    assert report["result"]["scoring"]["combined_score"] is None
    assert report["result"]["scoring"]["model_status"] == "not_available"
    owner = login(app)
    endpoint = "/api/" + core + "/" + case_id + "/published-assessment"
    assert owner.get(endpoint).status_code == 404
    assert analyst.get(endpoint).json()["audience"] == "analyst"
    p = analyst.post(
        "/api/assessments/" + report["id"] + "/print-publication",
        json={
            "financial_results": True,
            "suggestions": True,
            "justification": "Communication synthétique autorisée",
        },
    )
    assert p.status_code == 201, p.text
    published = owner.get(endpoint).json()
    assert published["audience"] == "applicant"
    assert (
        not {"scoring", "sections", "sources", "policy_snapshot", "human_validations"}
        & published["report"].keys()
    )
    assert all(s["recipient"] == "demandeur" for s in published["report"]["suggestions"])
    simulation = analyst.post(
        "/api/assessments/" + report["id"] + "/simulations",
        json={"specification": {"kind": "stress", "scenario": {"revenue_drop": "0.20"}}},
    )
    assert simulation.status_code == 201, simulation.text
    assert owner.get("/api/" + core + "/" + case_id).json()["data"]["periods"] == original_periods
    edition = owner.post(
        "/api/" + core + "/" + case_id + "/print/editions",
        json={
            "template_id": "analysis_report",
            "audience": "applicant",
            "assessment_id": report["id"],
        },
    )
    assert edition.status_code == 201, edition.text
    edition = edition.json()
    assert edition["status"] == "completed", edition
    pdf = owner.get("/api/print-editions/" + edition["id"] + "/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    outsider = login(app, "outsider")
    assert outsider.get("/api/print-editions/" + edition["id"] + "/pdf").status_code == 404
    assert outsider.post("/api/print-editions/" + edition["id"] + "/process").status_code == 404
    with app.state.session_factory() as db:
        assert db.get(CaseRecord, case_id).payload["periods"] == original_periods


def test_document_idempotency_revision_and_private_images(web):
    app, _ = web
    owner = login(app)
    case = owner.post("/api/individuals", json=payload("individuals")).json()
    base = "/api/individuals/" + case["id"] + "/submissions"
    body = {
        "document_type": "bank_statement",
        "role": "Compte synthétique",
        "period": "2026-02-01",
        "visibility": "applicant",
    }
    headers = {"Idempotency-Key": "document-operation-0001"}
    sub = owner.post(base, json=body, headers=headers)
    assert sub.status_code == 201, sub.text
    sub = sub.json()
    assert owner.post(base, json=body, headers=headers).json()["id"] == sub["id"]
    assert owner.post(base, json={**body, "role": "différent"}, headers=headers).status_code == 409
    file = Path("modules/credit_pme_pdf/examples/pdf/bank_table.pdf").read_bytes()
    source = base + "/" + sub["id"] + "/sources"
    h = {"Idempotency-Key": "upload-operation-000001", "If-Match": "1"}
    received = owner.post(source, content=file, headers=h)
    assert received.status_code == 201, received.text
    received = received.json()
    replay = owner.post(source, content=file, headers=h)
    assert replay.status_code == 201
    assert replay.json()["pages"] == received["pages"]
    assert replay.json()["revision"] == received["revision"]
    assert owner.post(source, content=file + b"\n", headers=h).status_code == 409
    assert owner.post(source, content=file, headers={"If-Match": "1"}).status_code == 409
    url = base + "/" + sub["id"]
    page = received["pages"][0]
    image = url + "/pages/" + page["id"] + "/image?original=true"
    assert owner.get(image).status_code == 200
    for username in ("neighbour", "outsider"):
        stranger = login(app, username)
        assert stranger.get(image).status_code == 404
        assert stranger.post(url + "/process").status_code == 404
    assert owner.post(url + "/confirm", headers={"If-Match": "1"}).status_code == 409
    assert owner.post(url + "/withdraw").status_code == 428
    removed = owner.post(url + "/withdraw", headers={"If-Match": str(received["revision"])})
    assert removed.status_code == 200
    assert removed.json()["deposit_status"] == "withdrawn"
    assert owner.get(base).json() == []
    # La trace et l'original sont conservés, aucun effacement physique silencieux.
    assert owner.get(image).status_code == 200


def test_same_origin_frontend_and_legacy_bearer(web):
    app, _ = web
    c = TestClient(app)
    assert c.get("/").status_code == 200
    assert "credit-api.js" in c.get("/").text
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/api/health").json() == {"status": "ok"}
    assert c.get("/individuals").status_code == 401
    assert c.get("/individuals", headers={"Authorization": "Bearer applicant"}).status_code == 200
    logged_in = login(app)
    # Pas de CSRF contournable via les anciennes routes : cookies reconnus uniquement sous /api.
    assert logged_in.post("/individuals", json=payload("individuals")).status_code == 401


def test_provisioning_cli_persists_password_and_revokes_sessions(web, monkeypatch):
    from scripts import provision_web_user as cli
    from credit.persistence import SecurityEvent

    app, _ = web
    previous = login(app, "neighbour")
    replacement = "New-synthetic-password-2026!"
    entered = iter([replacement, replacement])
    monkeypatch.setattr(
        "sys.argv", ["provision", "--actor-id", "neighbour", "--username", "updated-login"]
    )
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(entered))
    monkeypatch.setattr(
        cli, "sessions", lambda: (app.state.api.state.engine, app.state.session_factory)
    )
    cli.main()
    assert previous.get("/auth/session").status_code == 401
    current = TestClient(app, headers={"Origin": ORIGIN})
    response = current.post(
        "/auth/login", json={"username": "updated-login", "password": replacement}
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "applicant"
    assert response.json()["user"]["institution_id"] == "bank"
    with app.state.session_factory() as db:
        user = db.get(WebUser, "neighbour")
        assert user.password_hash != replacement
        assert PASSWORDS.verify(user.password_hash, replacement)
        event = db.scalar(
            select(SecurityEvent).where(SecurityEvent.event == "web_account_provisioned")
        )
        assert event.resource_id == "neighbour" and event.actor_id.startswith("os:")
