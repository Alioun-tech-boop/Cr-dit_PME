import hashlib
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, delete
from credit.auth import Actor
from credit.persistence import WebUser, WebSession, SecurityEvent, identifier
from credit.partners.models import Partner
from credit.institutions.models import InstitutionAccount
from credit.institutions.contracts import ActivateAccount
from credit.security.runtime import audit


def managed_actor(user, db):
    account = db.get(InstitutionAccount, user.actor_id)
    if account is None:
        return None
    partner = db.get(Partner, account.partner_id)
    if (
        account.status != "active"
        or account.role not in {"bank_agent", "bank_manager"}
        or not partner
        or partner.data.get("archived_at")
    ):
        raise HTTPException(401, "Accès établissement désactivé")
    return Actor(
        id=user.actor_id,
        institution_id=partner.bank_institution_id,
        role=account.role,
        partner_ids=(partner.id,),
    )


def register_activation(app, factory, csrf, limiter, passwords, password_slots):
    from fastapi import Request

    @app.post("/auth/activate")
    def activate(body: ActivateAccount, request: Request):
        csrf(request)
        limiter.check(("activation", request.client.host if request.client else "local"), 10)
        if not password_slots.acquire(blocking=False):
            raise HTTPException(429, "Activation occupée ; réessayez")
        try:
            hashed = passwords.hash(body.password)
        finally:
            password_slots.release()
        digest = hashlib.sha256(body.token.encode()).hexdigest()
        with factory() as db:
            item = db.scalar(
                select(InstitutionAccount)
                .where(InstitutionAccount.invitation_digest == digest)
                .with_for_update()
            )
            expiry = item.invitation_expires if item else None
            if expiry and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            partner = db.get(Partner, item.partner_id) if item else None
            if (
                not item
                or not expiry
                or expiry <= datetime.now(timezone.utc)
                or item.status != "invited"
                or not partner
                or partner.data.get("archived_at")
            ):
                raise HTTPException(400, "Lien invalide, expiré ou déjà utilisé")
            user = db.get(WebUser, item.actor_id)
            user.password_hash = hashed
            user.enabled = 1
            item.status = "active"
            item.invitation_digest = None
            item.invitation_expires = None
            db.execute(delete(WebSession).where(WebSession.actor_id == item.actor_id))
            db.add(
                SecurityEvent(
                    actor_id=item.actor_id,
                    institution_id=partner.bank_institution_id,
                    event="institution_account_activated",
                    outcome="success",
                    request_id=identifier(),
                    resource_id=item.actor_id,
                )
            )
            db.commit()
        audit("institution_account_activated", outcome="success")
        return {"status": "activated"}
