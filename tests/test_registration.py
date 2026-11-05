"""Inscription réelle, normalisation, habilitations fixes et absence d’énumération."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from credit.persistence import WebUser, WebRegistration
from credit.web.application import create_web_app, PASSWORDS
from credit.web.registration import normalize_identifier

ORIGIN = "http://testserver"
PASSWORD = "Synthetic-registration-2026!"


@pytest.fixture
def signup(url, monkeypatch):
    monkeypatch.setenv("CREDIT_SIGNUP_INSTITUTION_ID", "institution-configured")
    monkeypatch.setenv("CREDIT_WEB_ORIGIN", ORIGIN)
    monkeypatch.setenv("CREDIT_RATE_REQUESTS", "10000")
    app = create_web_app(url)
    with TestClient(app, headers={"Origin": ORIGIN}) as client:
        yield app, client, url
    app.state.api.state.engine.dispose()


def register(client, identifier="user@example.test", channel="email", password=PASSWORD, **extra):
    return client.post(
        "/auth/register",
        json={
            "channel": channel,
            "identifier": identifier,
            "password": password,
            "password_confirmation": password,
            **extra,
        },
    )


def connect(client, identifier, password=PASSWORD):
    return client.post("/auth/login", json={"username": identifier, "password": password})


@pytest.mark.parametrize(
    "channel,identifier,login,canonical",
    [
        ("email", "User@EXAMPLE.test", "user@example.test", "user@example.test"),
        ("phone", "70 00 00 01", "+22670000001", "+22670000001"),
    ],
)
def test_real_account_persists_and_has_only_applicant_permissions(
    signup, channel, identifier, login, canonical
):
    app, client, url = signup
    response = register(client, identifier, channel)
    assert response.status_code == 202
    assert response.json()["contact_status"] == "not_verified"
    assert "set-cookie" not in response.headers
    with app.state.session_factory() as db:
        user = db.scalar(select(WebUser).where(WebUser.username == canonical))
        assert (
            user
            and user.password_hash != PASSWORD
            and PASSWORDS.verify(user.password_hash, PASSWORD)
        )
        registration = db.get(WebRegistration, user.actor_id)
        assert registration.institution_id == "institution-configured"
        assert registration.contact_status == "not_verified"
    assert connect(client, login).status_code == 200
    actor = client.get("/auth/session").json()["user"]
    assert actor["role"] == "applicant" and actor["institution_id"] == "institution-configured"
    assert client.get("/api/journeys").status_code == 200
    restarted = create_web_app(url)
    try:
        with TestClient(restarted, headers={"Origin": ORIGIN}) as new_client:
            assert connect(new_client, login).status_code == 200
    finally:
        restarted.state.api.state.engine.dispose()


def test_duplicate_response_identical_and_existing_password_unchanged(signup):
    app, c, _ = signup
    first = register(c)
    duplicate = register(c, password="Another-synthetic-password-2026!")
    assert first.status_code == duplicate.status_code == 202 and first.json() == duplicate.json()
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(WebUser)) == 1
        assert db.scalar(select(func.count()).select_from(WebRegistration)) == 1
    assert connect(c, "user@example.test", "Another-synthetic-password-2026!").status_code == 401
    assert connect(c, "user@example.test").status_code == 200


def test_two_registered_accounts_are_isolated_and_cannot_analyze(signup):
    app, first, _ = signup
    assert register(first, "first@example.test").status_code == 202
    assert connect(first, "first@example.test").status_code == 200
    csrf = first.get("/auth/csrf").json()["token"]
    payload = json.loads(Path("examples/salarie.json").read_text())
    payload["data_classification"] = "real"  # Données synthétiques, parcours demandeur réel testé.
    response = first.post("/api/individuals", json=payload, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 201, response.text
    case = response.json()["id"]
    assert (
        first.post(
            f"/api/individuals/{case}/financial-analyses",
            json={},
            headers={"X-CSRF-Token": csrf, "X-Role": "administrator"},
        ).status_code
        == 403
    )
    with TestClient(app, headers={"Origin": ORIGIN}) as second:
        assert register(second, "second@example.test").status_code == 202
        assert connect(second, "second@example.test").status_code == 200
        assert second.get("/api/individuals").json() == []
        assert second.get("/api/individuals/" + case).status_code == 404
    assert (
        first.patch(
            "/auth/profile",
            json={"display_name": "Test", "email": "", "telephone": "", "role": "administrator"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "extra",
    [{"role": "administrator"}, {"institution_id": "other"}, {"contact_status": "verified"}],
)
def test_privileged_fields_rejected(signup, extra):
    _, client, _ = signup
    assert register(client, **extra).status_code == 422


def test_disabled_registration_origin_and_invalid_identifiers(signup, monkeypatch):
    _, c, _ = signup
    assert register(c, "not-an-email").status_code == 422
    assert register(c, "bad-phone", "phone").status_code == 422
    assert register(c, password="short").status_code == 422
    c.headers["Origin"] = "https://foreign.invalid"
    assert register(c).status_code == 403
    c.headers["Origin"] = ORIGIN
    monkeypatch.delenv("CREDIT_SIGNUP_INSTITUTION_ID")
    assert register(c).status_code == 503


def test_rate_limit_and_disabled_account(signup):
    app, c, _ = signup
    for _ in range(5):
        assert register(c).status_code == 202
    assert register(c).status_code == 429
    assert connect(c, "user@example.test").status_code == 200
    with app.state.session_factory() as db:
        user = db.scalar(select(WebUser).where(WebUser.username == "user@example.test"))
        user.enabled = 0
        db.commit()
    assert c.get("/auth/session").status_code == 401


def test_phone_normalization_and_no_implicit_foreign_country():
    assert normalize_identifier("phone", "70 00 00 01") == "+22670000001"
    assert normalize_identifier("phone", "+225 07 00 00 00 01") == "+2250700000001"
    with pytest.raises(ValueError):
        normalize_identifier("phone", "0700000001")
