"""Inscription de demandeurs : périmètre serveur, coordonnées déclarées, aucun rôle choisi."""

import os
import re
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from credit.auth import Actor, authenticate
from credit.persistence import WebRegistration, WebUser, SecurityEvent
from credit.security.runtime import audit


def normalize_identifier(channel, raw):
    value = raw.strip()
    if channel == "email":
        value = value.lower()
        if (
            not value.isascii()
            or not re.fullmatch(
                r"[^\s@<>]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value
            )
            or len(value) > 100
        ):
            raise ValueError("Adresse e-mail invalide")
        if ".." in value:
            raise ValueError("Adresse e-mail invalide")
    else:
        if not re.fullmatch(r"[+0-9 ().-]+", value):
            raise ValueError("Numéro de téléphone invalide")
        value = re.sub(r"[ ().-]", "", value)
        if re.fullmatch(r"\d{8}", value):
            value = "+226" + value
        if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
            raise ValueError(
                "Utilisez un numéro burkinabè à 8 chiffres ou le format international +indicatif"
            )
    return value


def login_candidates(raw):
    value = raw.strip().lower()
    try:
        channel = "email" if "@" in value else "phone"
        canonical = normalize_identifier(channel, value)
    except ValueError:
        canonical = value
    return [value] if value == canonical else [value, canonical]


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["email", "phone"]
    identifier: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    password_confirmation: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def check(self):
        self.identifier = normalize_identifier(self.channel, self.identifier)
        if self.password != self.password_confirmation:
            raise ValueError("Les mots de passe doivent correspondre")
        return self


def resolve_browser_actor(user, db, request):
    from credit.institutions.accounts import managed_actor

    managed = managed_actor(user, db)
    if managed is not None:
        return managed
    registration = db.get(WebRegistration, user.actor_id)
    if registration is None:
        return authenticate(request, configured_actor_id=user.actor_id)
    # Ni le profil modifiable, ni un champ reçu du navigateur ne détermine ces droits.
    return Actor(id=user.actor_id, institution_id=registration.institution_id, role="applicant")


def register_routes(app, factory, csrf, limiter, passwords, password_slots):
    @app.post("/auth/register", status_code=202)
    def register(body: Registration, request: Request):
        csrf(request)
        tenant = os.getenv("CREDIT_SIGNUP_INSTITUTION_ID", "")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", tenant):
            raise HTTPException(503, "La création de compte n’est pas encore activée.")
        from credit.web.application import digest

        limiter.check(("registration", request.client.host if request.client else "local"), 5, 3600)
        limiter.check(("registration_contact", digest(body.identifier)), 5, 3600)
        if not password_slots.acquire(blocking=False):
            raise HTTPException(429, "Création de compte occupée ; réessayez plus tard")
        try:
            hashed = passwords.hash(body.password)
        finally:
            password_slots.release()
        with factory() as db:
            existing = db.scalar(
                select(WebUser.actor_id).where(WebUser.username == body.identifier)
            )
            if existing is None:
                actor_id = str(uuid4())
                try:
                    db.add(
                        WebUser(
                            actor_id=actor_id,
                            username=body.identifier,
                            password_hash=hashed,
                            profile={
                                "display_name": "",
                                "email": body.identifier if body.channel == "email" else "",
                                "telephone": body.identifier if body.channel == "phone" else "",
                            },
                        )
                    )
                    db.flush()
                    db.add(
                        WebRegistration(
                            actor_id=actor_id,
                            institution_id=tenant,
                            identifier=body.identifier,
                            channel=body.channel,
                            contact_status="not_verified",
                        )
                    )
                    db.add(
                        SecurityEvent(
                            actor_id=actor_id,
                            institution_id=tenant,
                            event="web_registration",
                            outcome="created",
                            request_id=str(uuid4()),
                            resource_id=actor_id,
                        )
                    )
                    db.commit()
                except IntegrityError:
                    db.rollback()  # Même réponse si une création concurrente a gagné.
        audit("web_registration", outcome="accepted")
        # Réponse et coût de hachage identiques : pas d’énumération ni de remplacement d’un compte.
        return {
            "status": "accepted",
            "contact_status": "not_verified",
            "message": "Demande reçue. Connectez-vous avec vos coordonnées et votre mot de passe. Un compte déjà existant n’est pas modifié.",
        }
