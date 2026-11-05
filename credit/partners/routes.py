from pathlib import Path
import hashlib
import hmac
import io
import json
import os
import time
import zipfile
from fastapi import Depends, HTTPException, Header, Request, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from credit.persistence import CaseRecord, now, identifier
from credit.partners.models import (
    Partner,
    InstitutionPolicy,
    InternalReview,
    PacketFile,
    Attestation,
    Transmission,
    Outbox,
    PartnerEvent,
    BankAttachment,
)
from credit.partners.contracts import (
    WorkflowPolicy,
    PartnerInput,
    PartnerActivation,
    PartnerStatus,
    StartReview,
    ReviewDecision,
    SelectPartner,
    Confirm,
    BankAction,
    ApplicantSupplement,
    Reason,
    Webhook,
    BASE_CATEGORIES,
    AssignApplicant,
)
from credit.partners.configuration import policy, identity, allow_demo
from credit.partners import service, delivery, bank, signing
from credit.security.access import role
from credit.security.runtime import Limiter
from credit.partners import invalidation  # noqa: F401


def register_routes(app, db, get_case):
    limits = Limiter()

    def actor(session):
        return session.info["actor"]

    def admin(session):
        a = actor(session)
        if role(a) != "administrator" or not a.institution_id:
            raise HTTPException(403, "Administrateur institutionnel requis")
        return a

    def staff(session):
        a = actor(session)
        if role(a) not in {"analyst", "institution_manager", "administrator"}:
            raise HTTPException(403, "Agent institutionnel habilité requis")
        return a

    def revision(expected, item):
        if expected != item.version:
            raise HTTPException(409, "Configuration modifiée ; actualiser")

    def partner_find(session, id, administrative=False):
        a = admin(session) if administrative else actor(session)
        p = session.get(Partner, id)
        if not p or p.issuer_id != a.institution_id:
            raise HTTPException(404, "Partenaire introuvable")
        return p

    def public_partner(p):
        c = p.data["configuration"]
        return {
            "id": p.id,
            "status": p.status,
            "connection_status": p.data.get("connection_status", "not_verified"),
            **{
                k: c[k]
                for k in [
                    "name",
                    "presentation",
                    "country",
                    "activity_scope",
                    "cores",
                    "profiles",
                    "products",
                    "provided_conditions",
                    "information_updated_on",
                    "required_categories",
                    "allowed_categories",
                    "processing_notice",
                    "demonstration",
                    "reception_mode",
                ]
            },
            "activated_at": p.data.get("activated_at"),
            "verified_at": p.data.get("verified_at"),
            "notice": "Aucune promesse de financement, de taux ou de délai non fourni.",
        }

    def find_review(session, id):
        r = session.get(InternalReview, id)
        case = session.get(CaseRecord, r.case_id) if r else None
        if not case:
            raise HTTPException(404, "Revue introuvable")
        case = get_case(session, case.kind, case.id)
        if session.info["request"].method != "GET":
            r = session.scalar(
                select(InternalReview).where(InternalReview.id == id).with_for_update()
            )
        return r, case

    def find_transmission(session, id, bancaire=False):
        t = session.get(Transmission, id)
        a = actor(session)
        if not t:
            raise HTTPException(404, "Transmission introuvable")
        if bancaire:
            if (
                role(a) not in {"bank_agent", "bank_manager"}
                or a.institution_id != t.bank_institution_id
                or t.state in {"ready", "pending", "sending", "failed", "cancelled"}
            ):
                raise HTTPException(404, "Transmission introuvable")
            if t.state == "withdrawn" and not t.data.get("was_available_to_bank"):
                raise HTTPException(404, "Transmission introuvable")
        else:
            c = session.get(CaseRecord, t.case_id)
            get_case(session, c.kind, c.id)
            if role(a) == "applicant" and a.id != t.applicant_id:
                raise HTTPException(404, "Transmission introuvable")
        if session.info["request"].method != "GET":
            t = session.scalar(
                select(Transmission)
                .where(Transmission.id == id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        return t

    def binary(payload, name, media="application/pdf"):
        return Response(
            payload,
            media_type=media,
            headers={
                "Content-Disposition": 'attachment; filename="' + name + '"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    def budget(session):
        limits.check(
            ("export", actor(session).id), int(os.getenv("CREDIT_PARTNER_EXPORTS_PER_MINUTE", "30"))
        )

    def key_required(key):
        if not key or not key.strip():
            raise HTTPException(428, "Idempotency-Key requis")
        return key

    @app.put("/partners/admin/policy")
    def set_policy(
        body: WorkflowPolicy, session: Session = Depends(db), if_match: int | None = Header(None)
    ):
        a = admin(session)
        allow_demo(body.demonstration, "synthetic" if body.demonstration else "real")
        for signer in body.signatories:
            who = identity(signer.actor_id)
            if (
                not who
                or who["institution_id"] != a.institution_id
                or who["role"] not in {"institution_manager", "administrator"}
            ):
                raise HTTPException(
                    422, "Signataire actif de cette institution et rôle de responsabilité requis"
                )
        p = session.get(InstitutionPolicy, a.institution_id)
        if p:
            if if_match != p.version:
                raise HTTPException(409, "Version de politique requise ou périmée")
            p.data = {
                "policy": body.model_dump(mode="json"),
                "configured_by": a.id,
                "date": now().isoformat(),
            }
        else:
            p = InstitutionPolicy(
                institution_id=a.institution_id,
                data={
                    "policy": body.model_dump(mode="json"),
                    "configured_by": a.id,
                    "date": now().isoformat(),
                },
            )
            session.add(p)
        service.event(
            session, a, "institution_policy_configured", {"institution_id": a.institution_id}
        )
        session.commit()
        return {"version": p.version, "policy": p.data["policy"]}

    @app.get("/partners/admin/policy")
    def read_policy(session: Session = Depends(db)):
        staff(session)
        p, b = policy(session, actor(session).institution_id)
        return {"version": p.version, "policy": b.model_dump(mode="json")}

    @app.post("/partners/admin/banks", status_code=201)
    def create_partner(body: PartnerInput, session: Session = Depends(db)):
        a = admin(session)
        from credit.documents.policy import configuration

        catalog, _ = configuration()
        if not set(body.allowed_categories) <= BASE_CATEGORIES | set(catalog["rules"]):
            raise HTTPException(422, "Catégorie absente des catalogues documentaires")
        if a.institution_id == body.bank_institution_id:
            raise HTTPException(
                422, "Institution émettrice et banque destinataire doivent être distinctes"
            )
        allow_demo(body.demonstration, "synthetic" if body.demonstration else "real")
        p = Partner(
            id=identifier(),
            issuer_id=a.institution_id,
            bank_institution_id=body.bank_institution_id,
            status="preparation",
            data={
                "configuration": body.model_dump(mode="json"),
                "connection_status": "not_verified",
                "created_by": a.id,
                "created_at": now().isoformat(),
            },
        )
        session.add(p)
        service.event(session, a, "partner_created", {"partner_id": p.id})
        session.commit()
        return {**public_partner(p), "version": p.version}

    @app.get("/partners/admin/banks")
    def list_admin(session: Session = Depends(db)):
        a = admin(session)
        return [
            {
                **public_partner(p),
                "version": p.version,
                "activation_references": p.data.get("activation_references"),
            }
            for p in session.scalars(select(Partner).where(Partner.issuer_id == a.institution_id))
        ]

    @app.post("/partners/admin/banks/{partner_id}/test")
    def test_partner(partner_id: str, session: Session = Depends(db)):
        p = partner_find(session, partner_id, True)
        # Un portail configuré exige au moins un compte bancaire habilité existant.
        path = os.getenv("CREDIT_AUTH_FILE")
        users = json.loads(Path(path).read_text() if path else os.environ["CREDIT_AUTH_JSON"])[
            "users"
        ]
        bank_users = [
            identity(u["id"]) for u in users if u.get("institution_id") == p.bank_institution_id
        ]
        if not any(u and u["role"] in {"bank_agent", "bank_manager"} for u in bank_users):
            raise HTTPException(409, "Compte bancaire actif de réception requis")
        c = p.data["configuration"]
        from credit.partners.connectors import CONNECTORS, Delivery

        req = Delivery(
            tracking_id="self-test",
            idempotency_key="self-test",
            manifest_sha256="0" * 64,
            recipient_institution_id=p.bank_institution_id,
            file_hashes=[],
        )
        response = CONNECTORS[c["reception_mode"]].deliver(req, attempt=4, configuration=c)
        if not response.technical_accepted:
            raise HTTPException(409, "Test de connexion non concluant")
        p.data = {
            **p.data,
            "connection_status": "verified",
            "verified_at": now().isoformat(),
            "tested_by": actor(session).id,
            "test_notice": "Test local du portail ou du simulateur ; aucune API bancaire externe validée.",
        }
        service.event(session, actor(session), "partner_connection_tested", {"partner_id": p.id})
        session.commit()
        return {**public_partner(p), "version": p.version}

    @app.post("/partners/admin/banks/{partner_id}/activate")
    def activate_partner(partner_id: str, body: PartnerActivation, session: Session = Depends(db)):
        p = partner_find(session, partner_id, True)
        revision(body.expected_version, p)
        if p.data.get("connection_status") != "verified":
            raise HTTPException(409, "Tester la réception avant activation")
        ip, pol = policy(session, p.issuer_id)
        if p.data["configuration"]["demonstration"] != pol.demonstration:
            raise HTTPException(409, "Mode de l’institution et du partenaire incompatible")
        signing.signing_key(p.issuer_id, pol.demonstration)
        p.status = "demonstration" if pol.demonstration else "active"
        p.data = {
            **p.data,
            "activation_references": body.model_dump(mode="json"),
            "activated_at": now().isoformat(),
            "activated_by": actor(session).id,
        }
        service.event(
            session, actor(session), "partner_activated", {"partner_id": p.id, "status": p.status}
        )
        session.commit()
        return {**public_partner(p), "version": p.version}

    @app.post("/partners/admin/banks/{partner_id}/status")
    def change_partner(partner_id: str, body: PartnerStatus, session: Session = Depends(db)):
        p = partner_find(session, partner_id, True)
        revision(body.expected_version, p)
        p.status = body.status
        if body.status == "preparation":
            p.data = {**p.data, "connection_status": "not_verified"}
        service.event(
            session,
            actor(session),
            "partner_status_changed",
            {"partner_id": p.id, "status": p.status, "reason": body.reason},
        )
        session.commit()
        return {**public_partner(p), "version": p.version}

    def register(core):
        base = f"/{core}/{{case_id}}"

        @app.post(base + "/banking/assign-applicant", name="assign_applicant_" + core)
        def assign_applicant(case_id: str, body: AssignApplicant, session: Session = Depends(db)):
            from credit.partners.models import CaseGrant

            a = actor(session)
            if role(a) not in {"institution_manager", "administrator"}:
                raise HTTPException(403, "Responsable institutionnel requis")
            c = get_case(session, core, case_id)
            if c.lock_version != body.expected_case_version:
                raise HTTPException(409, "Version du dossier périmée")
            target = identity(body.actor_id)
            owner = identity(c.owner_id)
            if (
                not target
                or target["role"] != "applicant"
                or target["institution_id"] != c.institution_id
            ):
                raise HTTPException(422, "Compte demandeur actif de cette institution requis")
            if (
                not owner
                or owner["role"] == "applicant"
                or session.scalar(select(InternalReview.id).where(InternalReview.case_id == c.id))
            ):
                raise HTTPException(
                    409, "Réaffectation d’un dossier client ou déjà en revue interdite"
                )
            if not session.get(CaseGrant, (c.id, a.id)):
                session.add(CaseGrant(case_id=c.id, actor_id=a.id, granted_by=a.id))
            c.owner_id = body.actor_id
            service.event(
                session, a, "applicant_assigned", {"case_id": c.id, "applicant_id": body.actor_id}
            )
            session.commit()
            return {"case_id": c.id, "version": c.lock_version, "applicant_id": body.actor_id}

        @app.post(base + "/banking/review-access", name="review_access_" + core)
        def grant(case_id: str, session: Session = Depends(db)):
            c = get_case(session, core, case_id)
            service.request_access(session, c, actor(session))
            return {"status": "review_access_requested"}

        @app.get(base + "/banking", name="banking_" + core)
        def overview(case_id: str, session: Session = Depends(db)):
            c = get_case(session, core, case_id)
            reviews = session.scalars(
                select(InternalReview)
                .where(InternalReview.case_id == c.id)
                .order_by(InternalReview.created_at.desc())
            ).all()
            result = {
                "case_id": c.id,
                "case_version": c.lock_version,
                "analysis_state": "not_available",
                "internal_state": "draft",
                "reviews": [],
                "partners": [],
                "transmissions": [],
            }
            from credit.persistence import AssessmentRecord

            if session.scalar(
                select(AssessmentRecord.id).where(
                    AssessmentRecord.case_id == c.id, AssessmentRecord.parent_id.is_(None)
                )
            ):
                result["analysis_state"] = "completed"
                result["internal_state"] = "analysis_completed"
            for r in reviews:
                result["reviews"].append(service.review_view(session, r, c, actor(session)))
            if reviews:
                result["internal_state"] = result["reviews"][0]["state"]
                selected = next(
                    (r for r in reviews if r.state == "approved" and service.fresh(session, r, c)),
                    None,
                )
                if selected:
                    att = session.scalar(
                        select(Attestation).where(Attestation.review_id == selected.id)
                    )
                    if att and service.attestation_status(session, att) == "valid":
                        for p in session.scalars(
                            select(Partner).where(Partner.issuer_id == c.institution_id)
                        ):
                            try:
                                service.partner_eligible(session, p, c, selected)
                                result["partners"].append(public_partner(p))
                            except HTTPException:
                                pass
            result["transmissions"] = [
                delivery.transmission_view(session, t)
                for t in session.scalars(
                    select(Transmission)
                    .where(Transmission.case_id == c.id)
                    .order_by(Transmission.created_at.desc())
                )
            ]
            return result

        @app.post(base + "/internal-reviews", status_code=201, name="start_internal_review_" + core)
        def start(
            case_id: str,
            body: StartReview,
            session: Session = Depends(db),
            idempotency_key: str | None = Header(None, max_length=128),
        ):
            staff(session)
            c = get_case(session, core, case_id)
            try:
                r = service.start_review(
                    session, c, actor(session), body, key_required(idempotency_key)
                )
                return service.review_view(session, r, c, actor(session))
            except ValueError:
                session.rollback()
                raise HTTPException(422, "Paquet non généré ; revue non créée") from None

        @app.post(base + "/banking/previews", status_code=201, name="prepare_banking_" + core)
        def preview(
            case_id: str,
            body: SelectPartner,
            session: Session = Depends(db),
            idempotency_key: str | None = Header(None, max_length=128),
        ):
            c = get_case(session, core, case_id)
            t = delivery.prepare(session, c, actor(session), body, key_required(idempotency_key))
            return delivery.transmission_view(session, t)

    for c in ["individuals", "businesses"]:
        register(c)

    @app.get("/internal-reviews/{review_id}")
    def read_review(review_id: str, session: Session = Depends(db)):
        r, c = find_review(session, review_id)
        return service.review_view(session, r, c, actor(session))

    @app.post("/internal-reviews/{review_id}/decisions")
    def decision(review_id: str, body: ReviewDecision, session: Session = Depends(db)):
        staff(session)
        r, c = find_review(session, review_id)
        r = service.decide(session, r, c, actor(session), body)
        return service.review_view(session, r, c, actor(session))

    @app.post("/internal-reviews/{review_id}/attestation", status_code=201)
    def issue_attestation(review_id: str, session: Session = Depends(db)):
        staff(session)
        r, c = find_review(session, review_id)
        try:
            a = service.issue(session, r, c, actor(session))
            return {
                "id": a.id,
                "state": service.attestation_status(session, a),
                "verification_url": a.data["envelope"]["core"]["verification_url"],
                "file_id": a.data["file_id"],
            }
        except ValueError:
            session.rollback()
            raise HTTPException(422, "Attestation non générée") from None

    @app.get("/internal-reviews/{review_id}/files/{file_id}")
    def review_file(review_id: str, file_id: str, session: Session = Depends(db)):
        budget(session)
        r, c = find_review(session, review_id)
        if role(actor(session)) == "applicant" and not r.data.get("approved_at"):
            raise HTTPException(
                403, "La prévisualisation du paquet prêteur attend l’approbation interne"
            )
        f = session.get(PacketFile, file_id)
        if not f or f.review_id != r.id:
            raise HTTPException(404, "Édition introuvable")
        if signing.digest(f.payload) != f.sha256:
            raise HTTPException(409, "Intégrité du document non confirmée")
        service.event(
            session, actor(session), "review_file_downloaded", {"review_id": r.id, "file_id": f.id}
        )
        session.commit()
        return binary(f.payload, f.name, f.media_type)

    @app.post("/attestations/{attestation_id}/revoke")
    def revoke(attestation_id: str, body: Reason, session: Session = Depends(db)):
        staff(session)
        att = session.get(Attestation, attestation_id)
        if not att:
            raise HTTPException(404, "Attestation introuvable")
        r, c = find_review(session, att.review_id)
        if role(actor(session)) not in {"institution_manager", "administrator"}:
            raise HTTPException(403, "Responsable habilité requis")
        att.state = "revoked"
        att.data = {
            **att.data,
            "revocation": {
                "actor_id": actor(session).id,
                "reason": body.reason,
                "date": now().isoformat(),
            },
        }
        service.event(
            session,
            actor(session),
            "attestation_revoked",
            {"attestation_id": att.id, "reason": body.reason},
        )
        session.commit()
        return {"state": "revoked"}

    @app.get("/public/attestations/{token}")
    def public_verify(token: str, session: Session = Depends(db)):
        att = session.scalar(select(Attestation).where(Attestation.public_token == token))
        if not att:
            raise HTTPException(404, "Attestation introuvable")
        return {
            "issuer": att.data["envelope"]["core"]["issuer_name"],
            "attestation_id": att.id,
            "date": att.created_at,
            "status": service.attestation_status(session, att),
        }

    @app.get("/transmissions/{transmission_id}")
    def transmission(transmission_id: str, session: Session = Depends(db)):
        return delivery.transmission_view(session, find_transmission(session, transmission_id))

    @app.post("/transmissions/{transmission_id}/confirm")
    def confirm_transmission(transmission_id: str, body: Confirm, session: Session = Depends(db)):
        t = find_transmission(session, transmission_id)
        c = session.get(CaseRecord, t.case_id)
        return delivery.transmission_view(
            session, delivery.confirm(session, t, c, actor(session), body)
        )

    @app.post("/transmissions/{transmission_id}/dispatch")
    def dispatch(transmission_id: str, session: Session = Depends(db)):
        t = find_transmission(session, transmission_id)
        if actor(session).id != t.applicant_id and role(actor(session)) not in {
            "institution_manager",
            "administrator",
        }:
            raise HTTPException(403, "Reprise non autorisée")
        return delivery.transmission_view(session, delivery.dispatch(session, t.id))

    @app.post("/transmissions/{transmission_id}/retry")
    def retry(transmission_id: str, body: Reason, session: Session = Depends(db)):
        t = find_transmission(session, transmission_id)
        if role(actor(session)) not in {"institution_manager", "administrator"}:
            raise HTTPException(403, "Reprise manuelle réservée au responsable")
        job = session.scalar(select(Outbox).where(Outbox.transmission_id == t.id))
        if not job or job.state != "failed" or job.data.get("manual_restarts", 0) >= 2:
            raise HTTPException(409, "Reprise non disponible")
        delivery.usable(session, t)
        job.state = "pending"
        job.attempts = 0
        job.due_at = now()
        job.data = {**job.data, "manual_restarts": job.data.get("manual_restarts", 0) + 1}
        t.state = "pending"
        service.event(
            session, actor(session), "delivery_manually_restarted", {"reason": body.reason}, t
        )
        session.commit()
        return delivery.transmission_view(session, t)

    @app.post("/transmissions/{transmission_id}/withdraw")
    def withdraw(transmission_id: str, body: Reason, session: Session = Depends(db)):
        t = find_transmission(session, transmission_id)
        if actor(session).id != t.applicant_id:
            raise HTTPException(403, "Retrait réservé au demandeur")
        if t.state in {"withdrawn", "cancelled"}:
            return delivery.transmission_view(session, t)
        uncertain = (
            t.state == "sending"
            and session.get(Partner, t.partner_id).data["configuration"]["reception_mode"]
            != "portal"
        )
        was = uncertain or t.state in {
            "transmitted",
            "received",
            "under_review",
            "additional_information",
            "decision_available",
        }
        t.data = {
            **t.data,
            "was_available_to_bank": was,
            "delivery_may_have_occurred": uncertain,
            "withdrawal": {
                "reason": body.reason,
                "actor_id": actor(session).id,
                "date": now().isoformat(),
            },
            "withdrawal_notice": "Une copie déjà reçue ou téléchargée ne peut pas être effacée à distance.",
        }
        t.state = "withdrawn" if was else "cancelled"
        job = session.scalar(select(Outbox).where(Outbox.transmission_id == t.id))
        if job:
            job.state = "cancelled"
        service.event(
            session,
            actor(session),
            "request_withdrawn",
            {"reason": body.reason, "previously_available": was},
            t,
        )
        session.commit()
        return delivery.transmission_view(session, t)

    @app.get("/bank/inbox")
    def inbox(
        session: Session = Depends(db),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=10000),
    ):
        a = actor(session)
        if role(a) not in {"bank_agent", "bank_manager"} or not a.institution_id:
            raise HTTPException(403, "Espace bancaire réservé aux agents partenaires")
        rows = session.scalars(
            select(Transmission)
            .where(
                Transmission.bank_institution_id == a.institution_id,
                Transmission.state.in_(
                    [
                        "transmitted",
                        "received",
                        "under_review",
                        "additional_information",
                        "decision_available",
                        "withdrawn",
                    ]
                ),
            )
            .order_by(Transmission.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [
            delivery.transmission_view(session, t)
            for t in rows
            if t.state != "withdrawn" or t.data.get("was_available_to_bank")
        ]

    @app.get("/bank/transmissions/{transmission_id}")
    def bank_read(transmission_id: str, session: Session = Depends(db)):
        return delivery.transmission_view(
            session, find_transmission(session, transmission_id, True)
        )

    @app.post("/bank/transmissions/{transmission_id}/events")
    def bank_event(
        transmission_id: str,
        body: BankAction,
        session: Session = Depends(db),
        idempotency_key: str | None = Header(None, max_length=128),
    ):
        t = find_transmission(session, transmission_id, True)
        bank.apply(session, t, actor(session), body, key_required(idempotency_key))
        return delivery.transmission_view(session, t)

    @app.post("/bank/webhooks/{partner_id}")
    def webhook(
        partner_id: str,
        body: Webhook,
        session: Session = Depends(db),
        x_signature: str = Header(""),
        x_timestamp: str = Header(""),
    ):
        a = actor(session)
        p = session.get(Partner, partner_id)
        if (
            not p
            or p.bank_institution_id != a.institution_id
            or role(a) not in {"bank_agent", "bank_manager"}
        ):
            raise HTTPException(404, "Partenaire introuvable")
        ref = p.data["configuration"].get("webhook_secret_env")
        secret = os.getenv(ref, "") if ref else ""
        try:
            stamp = int(x_timestamp)
        except ValueError:
            raise HTTPException(401, "Événement non authentifié") from None
        expected = hmac.new(
            secret.encode(),
            x_timestamp.encode() + b"." + signing.canonical(body.model_dump(mode="json")),
            hashlib.sha256,
        ).hexdigest()
        if (
            not secret
            or abs(time.time() - stamp) > 300
            or not hmac.compare_digest(expected, x_signature)
        ):
            raise HTTPException(401, "Événement non authentifié ou expiré")
        t = find_transmission(session, body.transmission_id, True)
        if t.partner_id != p.id:
            raise HTTPException(404, "Transmission introuvable")
        event = bank.apply(session, t, a, body.event, "webhook:" + body.event_id, body.sequence)
        return {
            "event_id": event.id,
            "result": event.action,
            "transmission": delivery.transmission_view(session, t),
        }

    def access_file(session, id, file_id, bancaire):
        t = find_transmission(session, id, bancaire)
        budget(session)
        if file_id not in {f["id"] for f in t.data["manifest"]["files"]}:
            raise HTTPException(404, "Document non partagé")
        if not delivery.integrity(session, t)["valid"]:
            raise HTTPException(409, "Intégrité du paquet non confirmée")
        f = session.get(PacketFile, file_id)
        if not f or f.review_id != t.review_id or signing.digest(f.payload) != f.sha256:
            raise HTTPException(409, "Intégrité du fichier non confirmée")
        service.event(session, actor(session), "shared_file_downloaded", {"file_id": f.id}, t)
        session.commit()
        return binary(f.payload, f.name, f.media_type)

    @app.get("/transmissions/{transmission_id}/files/{file_id}")
    def file_read(transmission_id: str, file_id: str, session: Session = Depends(db)):
        return access_file(session, transmission_id, file_id, False)

    @app.get("/bank/transmissions/{transmission_id}/files/{file_id}")
    def bank_file_read(transmission_id: str, file_id: str, session: Session = Depends(db)):
        return access_file(session, transmission_id, file_id, True)

    def export(session, id, bancaire):
        t = find_transmission(session, id, bancaire)
        budget(session)
        check = delivery.integrity(session, t)
        if not check["valid"]:
            raise HTTPException(409, "Paquet altéré ; export interdit")
        att = session.get(Attestation, t.attestation_id)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("sharing-manifest.json", signing.canonical(t.data["manifest"]))
            archive.writestr("signed-manifest.json", signing.canonical(att.data["envelope"]))
            archive.writestr("signature.json", signing.canonical(att.data["signature"]))
            archive.writestr(
                "sharing-signature.json", signing.canonical(t.data["sharing_signature"])
            )
            for f in t.data["manifest"]["files"]:
                file = session.get(PacketFile, f["id"])
                archive.writestr(file.name, file.payload)
        service.event(
            session,
            actor(session),
            "packet_exported",
            {"manifest_sha256": t.data["manifest_sha256"]},
            t,
        )
        session.commit()
        return binary(output.getvalue(), "credit-pme-" + t.id + ".zip", "application/zip")

    @app.get("/transmissions/{transmission_id}/archive")
    def export_owner(transmission_id: str, session: Session = Depends(db)):
        return export(session, transmission_id, False)

    @app.get("/bank/transmissions/{transmission_id}/archive")
    def export_bank(transmission_id: str, session: Session = Depends(db)):
        return export(session, transmission_id, True)

    @app.get("/bank/transmissions/{transmission_id}/verify")
    def bank_verify(transmission_id: str, session: Session = Depends(db)):
        t = find_transmission(session, transmission_id, True)
        return delivery.integrity(session, t)

    def history(session, id, bancaire):
        t = find_transmission(session, id, bancaire)
        return [
            {
                "id": e.id,
                "actor_id": e.actor_id,
                "date": e.created_at,
                "event": e.action,
                "data": e.data,
            }
            for e in session.scalars(
                select(PartnerEvent)
                .where(PartnerEvent.transmission_id == t.id)
                .order_by(PartnerEvent.created_at)
            )
        ]

    @app.get("/transmissions/{transmission_id}/events")
    def events(transmission_id: str, session: Session = Depends(db)):
        return history(session, transmission_id, False)

    @app.get("/bank/transmissions/{transmission_id}/events")
    def bank_events(transmission_id: str, session: Session = Depends(db)):
        return history(session, transmission_id, True)

    async def upload(session, id, request, bancaire):
        t = find_transmission(session, id, bancaire)
        if not bancaire and actor(session).id != t.applicant_id:
            raise HTTPException(403, "Pièce complémentaire réservée au demandeur")
        if t.state not in {
            "received",
            "under_review",
            "additional_information",
            "decision_available",
        }:
            raise HTTPException(409, "Pièce non admise dans cet état")
        from sqlalchemy import func

        count = session.scalar(
            select(func.count())
            .select_from(BankAttachment)
            .where(BankAttachment.transmission_id == t.id)
        )
        if count >= 30:
            raise HTTPException(429, "Quota de compléments atteint")
        from credit.documents.intake_routes import bounded_body
        from credit.documents.policy import configuration

        limits, q = configuration()
        payload = await bounded_body(request, 5_000_000)
        previous = session.scalar(
            select(BankAttachment).where(
                BankAttachment.transmission_id == t.id,
                BankAttachment.actor_id == actor(session).id,
                BankAttachment.sha256 == signing.digest(payload),
            )
        )
        if previous:
            return {
                "id": previous.id,
                "sha256": previous.sha256,
                "status": "already_uploaded",
                "inspection": previous.data,
            }
        from starlette.concurrency import run_in_threadpool

        try:
            result = await run_in_threadpool(
                app.state.scan_runner.run,
                "inspect",
                {"quality": q},
                {"input": {"payload": payload}},
            )
        except ValueError:
            raise HTTPException(422, "Fichier non décodable ou hors limites") from None
        from credit.security.files import antimalware

        malware = await run_in_threadpool(antimalware, payload)
        if len(result.get("pages", [])) > 30:
            raise HTTPException(413, "Trop de pages")
        f = BankAttachment(
            transmission_id=t.id,
            actor_id=actor(session).id,
            category="bank_response" if bancaire else "applicant_supplement",
            sha256=signing.digest(payload),
            media_type=result["media_type"],
            payload=payload,
            data={
                "decode_status": "decoded",
                "antimalware": malware,
                "transcription_status": "not_reviewed",
                "authenticity_status": "not_assessed",
            },
        )
        session.add(f)
        session.commit()
        return {
            "id": f.id,
            "sha256": f.sha256,
            "status": "uploaded_not_shared",
            "inspection": f.data,
        }

    @app.post("/bank/transmissions/{transmission_id}/attachments", status_code=201)
    async def bank_upload(transmission_id: str, request: Request, session: Session = Depends(db)):
        return await upload(session, transmission_id, request, True)

    @app.post("/transmissions/{transmission_id}/attachments", status_code=201)
    async def applicant_upload(
        transmission_id: str, request: Request, session: Session = Depends(db)
    ):
        return await upload(session, transmission_id, request, False)

    @app.post("/transmissions/{transmission_id}/supplements", status_code=201)
    def supplement(
        transmission_id: str,
        body: ApplicantSupplement,
        session: Session = Depends(db),
        idempotency_key: str | None = Header(None, max_length=128),
    ):
        t = find_transmission(session, transmission_id)
        key = "supplement:" + key_required(idempotency_key)
        if actor(session).id != t.applicant_id:
            raise HTTPException(403, "Confirmation réservée au demandeur")
        sha = signing.digest(signing.canonical(body.model_dump(mode="json")))
        old = session.scalar(
            select(PartnerEvent).where(
                PartnerEvent.transmission_id == t.id, PartnerEvent.event_key == key
            )
        )
        if old:
            if old.data["request_sha256"] != sha:
                raise HTTPException(409, "Clé de complément réutilisée")
            return delivery.transmission_view(session, t)
        if (
            body.expected_revision != t.revision
            or t.state != "additional_information"
            or not body.accepted
        ):
            raise HTTPException(
                409, "Demande de complément actuelle et nouvelle confirmation requises"
            )
        manifest = []
        for id in body.attachment_ids:
            f = session.get(BankAttachment, id)
            if not f or f.transmission_id != t.id or f.actor_id != actor(session).id:
                raise HTTPException(404, "Pièce complémentaire introuvable")
            manifest.append({"id": f.id, "sha256": f.sha256})
        t.data = {
            **t.data,
            "shared_attachment_ids": sorted(
                set(t.data.get("shared_attachment_ids", []) + body.attachment_ids)
            ),
        }
        service.event(
            session,
            actor(session),
            "supplement_confirmed",
            {
                "request_sha256": sha,
                "files": manifest,
                "reason": body.reason,
                "consent_version": service.CONSENT_VERSION,
                "date": now().isoformat(),
                "notice": "Compléments séparés, non inclus dans l’attestation initiale.",
            },
            t,
            key,
        )
        session.commit()
        return delivery.transmission_view(session, t)

    def download_attachment(session, id, attachment_id, bancaire):
        t = find_transmission(session, id, bancaire)
        budget(session)
        f = session.get(BankAttachment, attachment_id)
        if (
            not f
            or f.transmission_id != t.id
            or (
                f.actor_id != actor(session).id
                and f.id not in t.data.get("shared_attachment_ids", [])
            )
        ):
            raise HTTPException(404, "Pièce non partagée")
        if signing.digest(f.payload) != f.sha256:
            raise HTTPException(409, "Pièce altérée")
        service.event(session, actor(session), "response_downloaded", {"attachment_id": f.id}, t)
        session.commit()
        return binary(
            f.payload,
            f.id
            + "."
            + (
                "pdf"
                if f.media_type == "application/pdf"
                else "png"
                if f.media_type == "image/png"
                else "jpg"
            ),
            f.media_type,
        )

    @app.get("/bank/transmissions/{transmission_id}/attachments/{attachment_id}")
    def bank_attachment(transmission_id: str, attachment_id: str, session: Session = Depends(db)):
        return download_attachment(session, transmission_id, attachment_id, True)

    @app.get("/transmissions/{transmission_id}/attachments/{attachment_id}")
    def owner_attachment(transmission_id: str, attachment_id: str, session: Session = Depends(db)):
        return download_attachment(session, transmission_id, attachment_id, False)
