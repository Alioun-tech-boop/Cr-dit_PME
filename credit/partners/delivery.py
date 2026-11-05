from datetime import timedelta, datetime
import os
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError
from fastapi import HTTPException
from credit.persistence import CaseRecord, now, identifier
from credit.partners.models import (
    Transmission,
    InternalReview,
    Attestation,
    Partner,
    Outbox,
    PacketFile,
    BankAttachment,
)
from credit.partners import signing, service
from credit.partners.configuration import identity
from credit.partners.connectors import CONNECTORS, Delivery, Acknowledgment


def transmission_view(session, t):
    att = session.get(Attestation, t.attestation_id)
    p = session.get(Partner, t.partner_id)
    return {
        "id": t.id,
        "case_id": t.case_id,
        "partner_id": t.partner_id,
        "partner_name": p.data["configuration"]["name"],
        "state": t.state,
        "revision": t.revision,
        "created_at": t.created_at,
        "case_version": t.data["manifest"]["case_version"],
        "attestation_id": t.attestation_id,
        "attestation_status": service.attestation_status(session, att),
        "manifest": t.data["manifest"],
        "manifest_sha256": t.data["manifest_sha256"],
        "consent_text": service.CONSENT_TEXT,
        "consent_version": service.CONSENT_VERSION,
        "processing_notice": t.data["processing_notice"],
        "confirmation": t.data.get("confirmation"),
        "decision": t.data.get("decision"),
        "external_id": t.data.get("external_id"),
        "requested_information": t.data.get("requested_information", []),
        "failure": t.data.get("failure"),
        "financing": att.data["envelope"]["core"]["financing"],
        "attachments": [
            {
                "id": f.id,
                "category": f.category,
                "sha256": f.sha256,
                "media_type": f.media_type,
                "shared": f.id in t.data.get("shared_attachment_ids", []),
            }
            for f in session.scalars(
                select(BankAttachment).where(BankAttachment.transmission_id == t.id)
            )
            if f.id in t.data.get("shared_attachment_ids", [])
            or (session.info.get("actor") and f.actor_id == session.info["actor"].id)
        ],
        "demonstration": t.data["demonstration"],
    }


def prepare(session, case, actor, body, key):
    service.applicant(case, actor)
    old = session.scalar(
        select(Transmission).where(
            Transmission.case_id == case.id, Transmission.operation_key == key
        )
    )
    request_sha = signing.digest(signing.canonical(body.model_dump(mode="json")))
    if old:
        if old.data["request_sha256"] != request_sha:
            raise HTTPException(409, "Clé de préparation réutilisée pour un autre paquet")
        return old
    review = session.get(InternalReview, body.review_id)
    if not review or review.case_id != case.id:
        raise HTTPException(404, "Revue introuvable")
    service.require_fresh(session, review, case)
    if review.state != "approved":
        raise HTTPException(409, "Validation interne complète requise avant choix bancaire")
    att = session.scalar(select(Attestation).where(Attestation.review_id == review.id))
    if not att or service.attestation_status(session, att) != "valid":
        raise HTTPException(409, "Attestation signée et utilisable requise")
    partner = session.get(Partner, body.partner_id)
    if not partner:
        raise HTTPException(404, "Partenaire introuvable")
    config = service.partner_eligible(session, partner, case, review)
    available = {
        f["id"]: f
        for f in att.data["envelope"]["approved_manifest"]["files"]
        + [att.data["envelope"]["attestation_file"]]
    }
    if len(body.file_ids) != len(set(body.file_ids)) or not set(body.file_ids) <= available.keys():
        raise HTTPException(422, "Sélection de documents non autorisée")
    files = [available[id] for id in body.file_ids]
    if any(f["category"] not in config["allowed_categories"] for f in files):
        raise HTTPException(409, "Catégorie non nécessaire ou non autorisée pour ce destinataire")
    missing = set(config["required_categories"]) - {f["category"] for f in files}
    if missing:
        raise HTTPException(409, "Pièces exigées manquantes : " + ", ".join(sorted(missing)))
    for previous in session.scalars(select(Transmission).where(Transmission.case_id == case.id)):
        if previous.data.get("decision", {}).get("kind") in {
            "formal_offer",
            "disbursement_confirmed",
        }:
            raise HTTPException(
                409,
                "Offre formelle ou financement confirmé déjà enregistré : nouvelle demande et revue des engagements nécessaires",
            )
    active = session.scalar(
        select(Transmission).where(
            Transmission.case_id == case.id,
            Transmission.state.not_in(["ready", "withdrawn", "cancelled", "failed"]),
        )
    )
    if active:
        raise HTTPException(
            409, "Une transmission est déjà active : aucun autre destinataire automatique"
        )
    id = identifier()
    manifest = {
        "schema_version": "bank-sharing-manifest-v1",
        "tracking_id": id,
        "case_id": case.id,
        "case_kind": case.kind,
        "case_version": review.case_version,
        "review_id": review.id,
        "attestation_id": att.id,
        "partner_id": partner.id,
        "recipient_institution_id": partner.bank_institution_id,
        "files": files,
        "attestation_envelope_sha256": signing.digest(signing.canonical(att.data["envelope"])),
    }
    signing_config, signing_key = signing.signing_key(case.institution_id, config["demonstration"])
    sharing_signature = signing.sign(manifest, signing_config, signing_key)
    t = Transmission(
        id=id,
        case_id=case.id,
        review_id=review.id,
        attestation_id=att.id,
        partner_id=partner.id,
        issuer_id=case.institution_id,
        bank_institution_id=partner.bank_institution_id,
        applicant_id=actor.id,
        operation_key=key,
        state="ready",
        data={
            "manifest": manifest,
            "manifest_sha256": signing.digest(signing.canonical(manifest)),
            "request_sha256": request_sha,
            "sharing_signature": sharing_signature,
            "demonstration": config["demonstration"],
            "processing_notice": config["processing_notice"],
            "partner_version": partner.version,
            "consent_policy": review.data["policy_snapshot"]["consent_valid_hours"],
            "last_sequence": 0,
        },
    )
    session.add(t)
    service.event(
        session, actor, "sharing_prepared", {"manifest_sha256": t.data["manifest_sha256"]}, t
    )
    session.commit()
    return t


def confirm(session, t, case, actor, body):
    service.applicant(case, actor)
    if body.accepted is not True:
        raise HTTPException(422, "Confirmation explicite non précochée requise")
    expected = {
        "manifest_sha256": t.data["manifest_sha256"],
        "attestation_id": t.attestation_id,
        "consent_version": service.CONSENT_VERSION,
    }
    if any(getattr(body, k) != v for k, v in expected.items()):
        raise HTTPException(409, "Confirmation différente du paquet prévisualisé")
    if t.data.get("confirmation"):
        if t.data["confirmation"]["authority_statement"] != body.authority_statement:
            raise HTTPException(409, "Confirmation déjà enregistrée avec un autre pouvoir déclaré")
        return t
    if t.revision != body.expected_revision or t.state != "ready":
        raise HTTPException(409, "Préparation modifiée ; actualiser et confirmer à nouveau")
    review = session.get(InternalReview, t.review_id)
    att = session.get(Attestation, t.attestation_id)
    partner = session.get(Partner, t.partner_id)
    service.require_fresh(session, review, case)
    service.partner_eligible(session, partner, case, review)
    if partner.version != t.data["partner_version"]:
        raise HTTPException(
            409, "Configuration de la banque modifiée : nouvelle prévisualisation requise"
        )
    if service.attestation_status(session, att) != "valid":
        raise HTTPException(409, "Attestation non utilisable")
    active = session.scalar(
        select(Transmission).where(
            Transmission.case_id == case.id,
            Transmission.id != t.id,
            Transmission.state.not_in(["ready", "withdrawn", "cancelled", "failed"]),
        )
    )
    if active:
        raise HTTPException(409, "Une autre transmission est déjà active")
    t.data = {
        **t.data,
        "confirmation": {
            **expected,
            "actor_id": actor.id,
            "institution_id": actor.institution_id,
            "authority_statement": body.authority_statement,
            "authority_evidence_source_id": review.data.get("business_authority_source_id"),
            "accepted_text": service.CONSENT_TEXT,
            "date": now().isoformat(),
        },
    }
    t.state = "pending"
    session.add(Outbox(transmission_id=t.id, data={"attempts": []}))
    service.event(
        session,
        actor,
        "sharing_confirmed",
        {"manifest_sha256": t.data["manifest_sha256"], "consent_version": service.CONSENT_VERSION},
        t,
    )
    session.commit()
    return t


def integrity(session, t):
    att = session.get(Attestation, t.attestation_id)
    signature = signing.verify(att.data["envelope"], att.data["signature"], t.issuer_id)
    sharing_signature = signing.verify(t.data["manifest"], t.data["sharing_signature"], t.issuer_id)
    manifest_valid = (
        signing.digest(signing.canonical(t.data["manifest"])) == t.data["manifest_sha256"]
    )
    envelope_valid = (
        signing.digest(signing.canonical(att.data["envelope"]))
        == t.data["manifest"]["attestation_envelope_sha256"]
    )
    signed = {
        f["id"]: f["sha256"]
        for f in att.data["envelope"]["approved_manifest"]["files"]
        + [att.data["envelope"]["attestation_file"]]
    }
    references_valid = (
        t.data["manifest"]["case_id"] == t.case_id == att.data["envelope"]["core"]["case_id"]
        and t.data["manifest"]["recipient_institution_id"] == t.bank_institution_id
        and t.data["manifest"]["partner_id"] == t.partner_id
        and t.data["manifest"]["attestation_id"] == att.id
        and t.data["manifest"]["case_version"] == att.data["envelope"]["core"]["case_version"]
    )
    approved_valid = (
        signing.digest(signing.canonical(att.data["envelope"]["approved_manifest"]))
        == att.data["envelope"]["core"]["approved_manifest_sha256"]
    )
    files = []
    for entry in t.data["manifest"]["files"]:
        file = session.get(PacketFile, entry["id"])
        files.append(
            {
                "id": entry["id"],
                "valid": bool(
                    file
                    and file.review_id == t.review_id
                    and file.sha256 == entry["sha256"] == signed.get(file.id)
                    and signing.digest(file.payload) == entry["sha256"]
                ),
            }
        )
    return {
        "signature": signature,
        "sharing_signature": sharing_signature,
        "manifest_valid": manifest_valid,
        "approved_manifest_valid": approved_valid,
        "envelope_valid": envelope_valid,
        "files": files,
        "valid": signature["valid"]
        and sharing_signature["valid"]
        and references_valid
        and manifest_valid
        and envelope_valid
        and approved_valid
        and all(f["valid"] for f in files),
        "attestation_status": service.attestation_status(session, att),
        "trusted_keys": signature["key_status"] != "revoked"
        and sharing_signature["key_status"] != "revoked",
        "notice": "Validité cryptographique et confiance juridique dans l’émetteur sont distinctes.",
    }


def usable(session, t):
    if t.state in {"withdrawn", "cancelled"} or not t.data.get("confirmation"):
        raise HTTPException(409, "Autorisation de transmission absente ou retirée")
    who = identity(t.applicant_id)
    if not who or who["role"] != "applicant" or who["institution_id"] != t.issuer_id:
        raise HTTPException(409, "Demandeur non habilité à transmettre")
    if (
        service.utc(datetime.fromisoformat(t.data["confirmation"]["date"]))
        + timedelta(hours=t.data["consent_policy"])
        <= now()
    ):
        raise HTTPException(409, "Confirmation expirée")
    case = session.get(CaseRecord, t.case_id)
    review = session.get(InternalReview, t.review_id)
    partner = session.get(Partner, t.partner_id)
    service.require_fresh(session, review, case)
    service.partner_eligible(session, partner, case, review)
    if partner.version != t.data["partner_version"]:
        raise HTTPException(409, "Configuration partenaire modifiée depuis la confirmation")
    result = integrity(session, t)
    if not result["valid"] or not result["trusted_keys"] or result["attestation_status"] != "valid":
        raise HTTPException(409, "Intégrité ou attestation non utilisable")
    return partner


def dispatch(session, transmission_id):
    """Claim transactionnel + bail. Tout adaptateur doit respecter la clé stable en cas de reprise."""
    t = session.get(Transmission, transmission_id)
    if t is None:
        return None
    # Ordre global des verrous : dossier, transmission, outbox, partenaire.
    locked = session.scalar(
        select(CaseRecord.id).where(CaseRecord.id == t.case_id).with_for_update(skip_locked=True)
    )
    if locked is None:
        return t
    t = session.scalar(
        select(Transmission)
        .where(Transmission.id == transmission_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    job = session.scalar(
        select(Outbox).where(Outbox.transmission_id == transmission_id).with_for_update()
    )
    if not job or job.state in {"completed", "cancelled"}:
        return t
    if job.state == "failed":
        return t
    if service.utc(job.due_at) > now() or (
        job.leased_until and service.utc(job.leased_until) > now()
    ):
        return t
    try:
        partner = usable(session, t)
    except HTTPException:
        job.state = "failed"
        t.state = "failed"
        t.data = {
            **t.data,
            "failure": "Autorisation, validation ou configuration non utilisable. Nouvelle revue ou préparation requise.",
        }
        session.commit()
        return t
    job.state = "processing"
    job.attempts += 1
    job.leased_until = now() + timedelta(seconds=60)
    t.state = "sending"
    try:
        session.commit()
    except StaleDataError:
        session.rollback()
        return session.get(Transmission, transmission_id)
    # Aucun secret du demandeur ni URL client : adaptateur administré.
    request = Delivery(
        tracking_id=t.id,
        idempotency_key=t.id,
        manifest_sha256=t.data["manifest_sha256"],
        recipient_institution_id=t.bank_institution_id,
        file_hashes=[f["sha256"] for f in t.data["manifest"]["files"]],
    )
    attempt = {"number": job.attempts, "date": now().isoformat()}
    try:
        response = CONNECTORS[partner.data["configuration"]["reception_mode"]].deliver(
            request, attempt=job.attempts, configuration=partner.data["configuration"]
        )
        ack = Acknowledgment.model_validate(response)
        if not ack.technical_accepted:
            raise ValueError("technical_refusal")
        # Recontrôle après l'appel, pour une révocation / un retrait concurrent.
        session.scalar(select(CaseRecord.id).where(CaseRecord.id == t.case_id).with_for_update())
        session.refresh(t, with_for_update=True)
        session.refresh(job, with_for_update=True)
        session.scalar(select(Partner.id).where(Partner.id == t.partner_id).with_for_update())
        if t.state in {"withdrawn", "cancelled"}:
            job.state = "cancelled"
            attempt["result"] = "returned_after_withdrawal"
        else:
            usable(session, t)
            t.state = "transmitted"
            t.data = {
                **t.data,
                "external_id": ack.external_id,
                "technical_acknowledgment": ack.model_dump(mode="json"),
                "failure": None,
            }
            job.state = "completed"
            attempt["result"] = "technical_accepted"
    except (TimeoutError, ValueError, HTTPException, KeyError):
        session.scalar(select(CaseRecord.id).where(CaseRecord.id == t.case_id).with_for_update())
        session.refresh(t, with_for_update=True)
        session.refresh(job, with_for_update=True)
        session.scalar(select(Partner.id).where(Partner.id == t.partner_id).with_for_update())
        if t.state in {"withdrawn", "cancelled"}:
            job.state = "cancelled"
        else:
            job.state = "failed" if job.attempts >= 3 else "pending"
            t.state = "failed" if job.state == "failed" else "pending"
            t.data = {
                **t.data,
                "failure": "Échec technique ; aucune réception métier ni décision bancaire déduite.",
            }
        job.due_at = now() + timedelta(
            seconds=min(
                300, 2**job.attempts * int(os.getenv("CREDIT_PARTNER_RETRY_BASE_SECONDS", "15"))
            )
        )
        attempt["result"] = "technical_failure"
    job.leased_until = None
    job.data = {"attempts": job.data["attempts"] + [attempt]}
    from credit.auth import Actor

    service.event(
        session, Actor("outbox-worker", institution_id=t.issuer_id), "delivery_attempt", attempt, t
    )
    session.commit()
    return t
