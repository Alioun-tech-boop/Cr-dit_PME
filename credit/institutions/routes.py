"""API des consoles : droits sur chaque établissement, transmission et édition."""

from copy import deepcopy
from datetime import timedelta
import hashlib
import secrets
from threading import BoundedSemaphore
from argon2 import PasswordHasher
from fastapi import Depends, Header, HTTPException, Query
from fastapi.responses import Response, HTMLResponse
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from credit.security.access import role
from credit.security.runtime import Limiter, audit
from credit.persistence import WebUser, WebSession, AssessmentRecord, identifier, now
from credit.partners.models import Partner, Transmission, InternalReview, Attestation
from credit.partners import service, signing
from credit.partners.contracts import Reason
from credit.institutions.models import InstitutionAccount, BankDecisionRecord, ClientMessage
from credit.institutions.contracts import (
    AccountCreate,
    AccountChange,
    Expected,
    PartnerEdit,
    BankDecision,
)
from credit.institutions import agreements, metrics
from credit.printing.contracts import Presentation
from credit.printing.render import html_document


INVITE_GATE = BoundedSemaphore(2)


def register_routes(app, db):
    limits = Limiter()

    def actor(session):
        return session.info["actor"]

    def admin(session):
        a = actor(session)
        if role(a) != "administrator" or not a.institution_id:
            raise HTTPException(403, "Administration réservée aux administrateurs habilités")
        return a

    def partner(session, id):
        a = admin(session)
        p = session.scalar(select(Partner).where(Partner.id == id).with_for_update())
        if not p or p.issuer_id != a.institution_id:
            raise HTTPException(404, "Établissement introuvable")
        return p

    def account_view(session, a):
        u = session.get(WebUser, a.actor_id)
        return {
            "id": a.actor_id,
            "username": u.username,
            "role": a.role,
            "professional_name": a.professional_name,
            "function": a.function,
            "status": a.status,
            "revision": a.revision,
            "partner_id": a.partner_id,
            "created_at": a.created_at,
        }

    def account_find(session, id):
        item = session.scalar(
            select(InstitutionAccount).where(InstitutionAccount.actor_id == id).with_for_update()
        )
        if not item:
            raise HTTPException(404, "Compte introuvable")
        p = partner(session, item.partner_id)
        return item, p

    def revoke_sessions(session, user):
        user.revision += 1
        session.execute(delete(WebSession).where(WebSession.actor_id == user.actor_id))

    def invite(item):
        token = secrets.token_urlsafe(48)
        item.invitation_digest = hashlib.sha256(token.encode()).hexdigest()
        item.invitation_expires = now() + timedelta(hours=24)
        item.status = "invited"
        # Le jeton reste dans le fragment, jamais dans les URL des journaux HTTP.
        url = (
            signing.verification_url(token).split("/verify-attestation.html?")[0]
            + "/activate-account.html#"
            + token
        )
        return {
            "activation_url": url,
            "expires_at": item.invitation_expires,
            "notice": "Lien secret à usage unique, valable 24 h. À communiquer au représentant vérifié par un canal approprié ; aucun message envoyé automatiquement.",
        }

    def find_bank(session, id, write=False):
        a = actor(session)
        if role(a) not in {"bank_agent", "bank_manager"}:
            raise HTTPException(403, "Espace établissement réservé")
        stmt = select(Transmission).where(Transmission.id == id)
        if write:
            stmt = stmt.with_for_update()
        t = session.scalar(stmt)
        if (
            not t
            or t.bank_institution_id != a.institution_id
            or (a.partner_ids and t.partner_id not in a.partner_ids)
            or t.state in {"ready", "pending", "sending", "failed", "cancelled"}
            or (t.state == "withdrawn" and not t.data.get("was_available_to_bank"))
        ):
            raise HTTPException(404, "Transmission introuvable")
        return t

    def find_decision(session, id, bank=False):
        stmt = select(BankDecisionRecord).where(BankDecisionRecord.id == id)
        if session.info["request"].method != "GET":
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        item = session.scalar(stmt)
        if not item:
            raise HTTPException(404, "Document introuvable")
        if bank:
            find_bank(session, item.transmission_id)
        else:
            t = session.get(Transmission, item.transmission_id)
            a = actor(session)
            if t.applicant_id != a.id or t.issuer_id != a.institution_id:
                raise HTTPException(404, "Document introuvable")
        return item

    def export_limit(session):
        limits.check(("institution_export", actor(session).id), 30)

    @app.get("/institution-admin/metrics")
    def dashboard(days: int = Query(30, ge=1, le=365), session: Session = Depends(db)):
        return metrics.build(session, admin(session).institution_id, days)

    @app.patch("/institution-admin/partners/{id}")
    def edit_partner(id: str, body: PartnerEdit, session: Session = Depends(db)):
        p = partner(session, id)
        if body.expected_version != p.version:
            raise HTTPException(409, "Établissement modifié ; actualiser")
        if p.data.get("archived_at"):
            raise HTTPException(409, "Établissement archivé")
        data = deepcopy(p.data)
        data["configuration"].update(body.model_dump(exclude={"expected_version"}))
        data["connection_status"] = "not_verified"
        data.pop("activation_references", None)
        p.data = data
        p.status = "preparation"
        service.event(
            session,
            actor(session),
            "partner_profile_updated",
            {"partner_id": p.id, "requires_reactivation": True},
        )
        session.commit()
        return {"id": p.id, "version": p.version, "status": p.status}

    @app.delete("/institution-admin/partners/{id}")
    def archive_partner(id: str, body: Expected, session: Session = Depends(db)):
        p = partner(session, id)
        if body.expected_revision != p.version:
            raise HTTPException(409, "Version périmée")
        data = deepcopy(p.data)
        data["archived_at"] = now().isoformat()
        p.data = data
        p.status = "suspended"
        for item in session.scalars(
            select(InstitutionAccount).where(InstitutionAccount.partner_id == p.id)
        ):
            item.status = "disabled"
            item.invitation_digest = None
            u = session.get(WebUser, item.actor_id)
            u.enabled = 0
            revoke_sessions(session, u)
        service.event(session, actor(session), "partner_archived", {"partner_id": p.id})
        session.commit()
        return {"status": "archived", "history_preserved": True}

    @app.get("/institution-admin/partners/{id}/signature")
    def signature_configuration(id: str, session: Session = Depends(db)):
        p = partner(session, id)
        try:
            keys = [
                {
                    "id": k["id"],
                    "status": k["status"],
                    "purpose": k["purpose"],
                    "partner_bound": p.id in k.get("partner_ids", []),
                }
                for k in signing.keyring()
                if p.bank_institution_id in k["issuer_ids"]
            ]
        except HTTPException:
            keys = []
        return {
            "keys": keys,
            "notice": "Clé bancaire privée à provisionner par l’opérateur et à rattacher à cet établissement ; aucune certification tierce configurée.",
        }

    @app.get("/institution-admin/partners/{id}/accounts")
    def list_accounts(id: str, session: Session = Depends(db)):
        partner(session, id)
        return [
            account_view(session, a)
            for a in session.scalars(
                select(InstitutionAccount).where(
                    InstitutionAccount.partner_id == id, InstitutionAccount.status != "deleted"
                )
            )
        ]

    @app.post("/institution-admin/partners/{id}/accounts", status_code=201)
    def create_account(id: str, body: AccountCreate, session: Session = Depends(db)):
        p = partner(session, id)
        if p.data.get("archived_at"):
            raise HTTPException(409, "Établissement archivé")
        limits.check(("invite", actor(session).id), 10)
        if not INVITE_GATE.acquire(blocking=False):
            raise HTTPException(429, "Création de compte occupée")
        try:
            initial_hash = PasswordHasher().hash(secrets.token_urlsafe(48))
        finally:
            INVITE_GATE.release()
        user = WebUser(
            actor_id=identifier(),
            username=body.username.lower(),
            password_hash=initial_hash,
            enabled=0,
            profile={"display_name": body.professional_name, "email": "", "telephone": ""},
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "Identifiant indisponible") from None
        item = InstitutionAccount(
            actor_id=user.actor_id,
            partner_id=p.id,
            role=body.role,
            professional_name=body.professional_name,
            function=body.function,
        )
        activation = invite(item)
        session.add(item)
        service.event(
            session,
            actor(session),
            "bank_account_invited",
            {"partner_id": p.id, "account_id": user.actor_id},
        )
        session.commit()
        return {**account_view(session, item), **activation}

    @app.patch("/institution-admin/accounts/{id}")
    def update_account(id: str, body: AccountChange, session: Session = Depends(db)):
        item, p = account_find(session, id)
        if item.revision != body.expected_revision:
            raise HTTPException(409, "Compte modifié ; actualiser")
        if item.status == "deleted" or p.data.get("archived_at"):
            raise HTTPException(409, "Compte ou établissement supprimé")
        if body.status == "active" and item.status == "invited":
            raise HTTPException(
                409, "Le titulaire doit activer son accès et choisir son mot de passe"
            )
        for key, value in body.model_dump(exclude={"expected_revision"}, exclude_none=True).items():
            setattr(item, key, value)
        u = session.get(WebUser, id)
        u.enabled = int(item.status == "active")
        if item.status in {"deleted", "disabled"}:
            item.invitation_digest = None
            item.invitation_expires = None
        revoke_sessions(session, u)
        service.event(
            session,
            actor(session),
            "bank_account_updated",
            {"partner_id": p.id, "account_id": id, "status": item.status},
        )
        session.commit()
        return account_view(session, item)

    @app.post("/institution-admin/accounts/{id}/reset")
    def reset_account(id: str, body: Expected, session: Session = Depends(db)):
        item, p = account_find(session, id)
        if item.revision != body.expected_revision:
            raise HTTPException(409, "Compte modifié ; actualiser")
        if item.status == "deleted" or p.data.get("archived_at"):
            raise HTTPException(409, "Compte supprimé")
        limits.check(("invite", actor(session).id), 10)
        data = invite(item)
        u = session.get(WebUser, id)
        u.enabled = 0
        revoke_sessions(session, u)
        service.event(
            session, actor(session), "bank_account_reset", {"partner_id": p.id, "account_id": id}
        )
        session.commit()
        return {**account_view(session, item), **data}

    @app.get("/bank/workspace")
    def workspace(session: Session = Depends(db)):
        a = actor(session)
        if role(a) not in {"bank_agent", "bank_manager"}:
            raise HTTPException(403, "Accès établissement requis")
        managed = session.get(InstitutionAccount, a.id)
        result = {
            "role": role(a),
            "professional_name": managed.professional_name if managed else None,
            "function": managed.function if managed else None,
            "institutions": [],
        }
        for p in session.scalars(
            select(Partner).where(
                Partner.bank_institution_id == a.institution_id,
                Partner.id.in_(a.partner_ids) if a.partner_ids else True,
            )
        ):
            result["institutions"].append(
                {
                    "id": p.id,
                    "name": p.data["configuration"]["name"],
                    "type": p.data["configuration"].get("institution_type", "bank"),
                    "status": p.status,
                    "demonstration": p.data["configuration"]["demonstration"],
                }
            )
        try:
            result["signature_configured"] = any(
                k["status"] == "active" and a.institution_id in k["issuer_ids"]
                for k in signing.keyring()
            )
        except HTTPException:
            result["signature_configured"] = False
        return result

    @app.get("/bank/transmissions/{id}/analysis")
    def bank_analysis(id: str, session: Session = Depends(db)):
        t = find_bank(session, id)
        if not any(f["category"] == "lender_report" for f in t.data["manifest"]["files"]):
            raise HTTPException(403, "Le rapport détaillé ne fait pas partie du paquet autorisé")
        r = session.get(InternalReview, t.review_id)
        a = session.get(AssessmentRecord, r.assessment_id)
        attestation = session.get(Attestation, t.attestation_id)
        from credit.assessment.application import canonical_hash

        expected = attestation.data["envelope"]["approved_manifest"]["analysis_sha256"]
        if canonical_hash(a.data["result"]) != expected:
            raise HTTPException(409, "L’analyse ne correspond plus à la version attestée")

        def clean(value):
            if isinstance(value, dict):
                return {
                    k: clean(v)
                    for k, v in value.items()
                    if k not in {"internal_observations", "internal_notes", "private_notes"}
                }
            if isinstance(value, list):
                return [clean(v) for v in value]
            return value

        return {
            "analysis_id": a.id,
            "case_version": r.case_version,
            "case_kind": a.case_kind,
            "report": clean(deepcopy(a.data["result"])),
            "scope": "Rapport destiné au prêteur, version figée et partagée ; notes internes exclues.",
        }

    @app.get("/bank/transmissions/{id}/agreement")
    def bank_agreement(id: str, session: Session = Depends(db)):
        find_bank(session, id)
        item = session.scalar(
            select(BankDecisionRecord).where(BankDecisionRecord.transmission_id == id)
        )
        return agreements.decision_view(item) if item else None

    @app.post("/bank/transmissions/{id}/decision-preview")
    def decision_preview(id: str, body: BankDecision, session: Session = Depends(db)):
        find_bank(session, id)
        if role(actor(session)) != "bank_manager":
            raise HTTPException(403, "Responsable bancaire requis")
        if body.decision != "approved" or body.terms is None:
            raise HTTPException(422, "Conditions d’accord requises")
        terms = agreements.normalized_terms(body.terms)
        return {
            "terms": terms,
            "terms_sha256": signing.digest(signing.canonical(terms)),
            "notice": "Prévisualisation uniquement : aucune décision enregistrée.",
        }

    @app.post("/bank/transmissions/{id}/decision", status_code=201)
    def decide(
        id: str,
        body: BankDecision,
        session: Session = Depends(db),
        idempotency_key: str = Header(min_length=16, max_length=128),
    ):
        t = find_bank(session, id, True)
        a = actor(session)
        if role(a) != "bank_manager":
            raise HTTPException(403, "Décision réservée au responsable bancaire")
        limits.check(("bank_decision", a.id), 10)
        return agreements.decision_view(agreements.issue(session, t, a, body, idempotency_key))

    @app.get("/inbox")
    def client_inbox(
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=10000),
        session: Session = Depends(db),
    ):
        a = actor(session)
        return [
            {
                "id": m.id,
                "title": m.title,
                "decision_id": m.decision_id,
                "transmission_id": m.transmission_id,
                "created_at": m.created_at,
                "read_at": m.read_at,
                "decision": agreements.decision_view(
                    session.get(BankDecisionRecord, m.decision_id)
                ),
            }
            for m in session.scalars(
                select(ClientMessage)
                .where(
                    ClientMessage.actor_id == a.id, ClientMessage.institution_id == a.institution_id
                )
                .order_by(ClientMessage.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ]

    @app.post("/inbox/{id}/read")
    def read_message(id: str, session: Session = Depends(db)):
        m = session.get(ClientMessage, id)
        a = actor(session)
        if not m or m.actor_id != a.id or m.institution_id != a.institution_id:
            raise HTTPException(404, "Message introuvable")
        if not m.read_at:
            m.read_at = now()
            session.commit()
        return {"read": True}

    def document(id, session, kind, bank):
        item = find_decision(session, id, bank)
        export_limit(session)
        if not item.payload:
            raise HTTPException(404, "Aucun accord PDF pour une décision de refus")
        status = agreements.verification(item)
        if not status["integrity_valid"]:
            raise HTTPException(409, "Intégrité du document non confirmée")
        audit("bank_agreement_download", actor(session), resource=item.id)
        if kind == "preview":
            return HTMLResponse(
                html_document(Presentation.model_validate(item.data["presentation"])),
                headers={
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'"
                },
            )
        if kind == "signature":
            return {
                "envelope": item.data["envelope"],
                "signature": item.data.get("signature"),
                "verification": status,
            }
        return Response(
            item.payload,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="accord-' + item.id + '.pdf"',
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    for bancaire, prefix in [(True, "/bank"), (False, "")]:

        def register_documents(bank_mode, path):
            @app.get(path + "/agreements/{id}/pdf")
            def pdf(id: str, session: Session = Depends(db)):
                return document(id, session, "pdf", bank_mode)

            @app.get(path + "/agreements/{id}/preview")
            def preview(id: str, session: Session = Depends(db)):
                return document(id, session, "preview", bank_mode)

            @app.get(path + "/agreements/{id}/signature")
            def signature(id: str, session: Session = Depends(db)):
                return document(id, session, "signature", bank_mode)

        register_documents(bancaire, prefix)

    @app.post("/bank/agreements/{id}/revoke")
    def revoke_agreement(id: str, body: Reason, session: Session = Depends(db)):
        item = find_decision(session, id, True)
        if role(actor(session)) != "bank_manager":
            raise HTTPException(403, "Responsable bancaire requis")
        if item.state != "revoked":
            data = deepcopy(item.data)
            data["revocation"] = {
                "reason": body.reason,
                "actor_id": actor(session).id,
                "date": now().isoformat(),
            }
            item.data = data
            item.state = "revoked"
            t = session.get(Transmission, item.transmission_id)
            session.add(
                ClientMessage(
                    actor_id=t.applicant_id,
                    institution_id=t.issuer_id,
                    transmission_id=t.id,
                    decision_id=item.id,
                    event_key="bank-revocation:" + item.id,
                    title="Offre révoquée — " + data["bank_name"],
                )
            )
            service.event(
                session, actor(session), "bank_agreement_revoked", {"agreement_id": id}, t
            )
            session.commit()
        return agreements.decision_view(item)

    @app.get("/public/bank-agreements/{token}")
    def public_status(token: str, session: Session = Depends(db)):
        item = session.scalar(
            select(BankDecisionRecord).where(BankDecisionRecord.public_token == token)
        )
        if not item:
            raise HTTPException(404, "Attestation introuvable")
        state = agreements.verification(item)
        return {
            "issuer": item.data["bank_name"],
            "id": item.id,
            "date": item.created_at,
            "status": state["status"],
            "third_party_certification": False,
        }
