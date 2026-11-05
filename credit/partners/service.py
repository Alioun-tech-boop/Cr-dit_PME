from copy import deepcopy
from datetime import timedelta, timezone
import secrets
from sqlalchemy import select
from fastapi import HTTPException
from credit.persistence import (
    CaseRecord,
    AssessmentRecord,
    SubmissionRecord,
    SourceRecord,
    DocumentRun,
    ReviewRecord,
    StructuredRecord,
    DocumentRecord,
    now,
    identifier,
)
from credit.assessment.application import canonical_hash, bind_reviewed_values
from credit.assessment.api_contracts import ReviewedValueBinding
from credit.partners.models import (
    InternalReview,
    InstitutionPolicy,
    Attestation,
    PartnerEvent,
    CaseGrant,
)
from credit.partners.configuration import policy, identity, allow_demo
from credit.partners import signing, packets
from credit.printing.contracts import Presentation, Section
from credit.printing.presentation import table_section
from credit.printing.isolation import render_isolated
from credit.security.access import role

CONSENT_VERSION = "bank-sharing-fr-v1"
CONSENT_TEXT = (
    "Je demande la transmission à cette seule banque des fichiers et catégories de données présentés, "
    "pour l’étude de ce financement. La validation interne n’est ni un accord bancaire ni une garantie de remboursement. "
    "Le retrait ne permet pas d’effacer une copie déjà reçue ou téléchargée par la banque."
)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def event(session, actor, action, data, transmission=None, event_key=None):
    if transmission is not None and transmission in session.new:
        session.flush()  # Parent inséré avant l'événement ; contrainte FK PostgreSQL effective.
    item = PartnerEvent(
        actor_id=actor.id,
        institution_id=actor.institution_id or "",
        action=action,
        transmission_id=transmission.id if transmission else None,
        event_key=event_key,
        data=deepcopy(data),
    )
    session.add(item)
    return item


def fingerprint(session, case):
    submissions = session.scalars(
        select(SubmissionRecord)
        .where(SubmissionRecord.case_id == case.id)
        .order_by(SubmissionRecord.id)
    ).all()
    sources = session.scalars(
        select(SourceRecord)
        .where(SourceRecord.submission_id.in_([s.id for s in submissions]))
        .order_by(SourceRecord.id)
    ).all()
    runs = session.scalars(
        select(DocumentRun)
        .where(DocumentRun.submission_id.in_([s.id for s in submissions]))
        .order_by(DocumentRun.id)
    ).all()
    reviews = session.scalars(
        select(ReviewRecord)
        .where(ReviewRecord.run_id.in_([r.id for r in runs]))
        .order_by(ReviewRecord.id)
    ).all()
    structured = session.scalars(
        select(StructuredRecord)
        .where(StructuredRecord.case_id == case.id)
        .order_by(StructuredRecord.id)
    ).all()
    old = session.scalars(
        select(DocumentRecord).where(DocumentRecord.case_id == case.id).order_by(DocumentRecord.id)
    ).all()
    return canonical_hash(
        {
            "case_version": case.lock_version,
            "payload": case.payload,
            "submissions": [(s.id, s.lock_version, s.data) for s in submissions],
            "sources": [(s.id, s.sha256) for s in sources],
            "runs": [(r.id, r.data) for r in runs],
            "reviews": [(r.id, r.data) for r in reviews],
            "structured": [(s.id, s.data) for s in structured],
            "legacy": [(s.id, s.document_sha256, s.extraction) for s in old],
        }
    )


def fresh(session, review, case):
    current = session.get(InstitutionPolicy, case.institution_id)
    return bool(
        current
        and current.version == review.data["institution_policy_version"]
        and case.lock_version == review.case_version
        and fingerprint(session, case) == review.fingerprint
    )


def require_fresh(session, review, case):
    if not fresh(session, review, case) or review.state in {
        "superseded",
        "needs_completion",
        "not_approved",
    }:
        raise HTTPException(
            409,
            "Version modifiée ou revue non utilisable : réanalyse et nouvelle approbation requises",
        )


def applicant(case, actor):
    who = identity(case.owner_id)
    if (
        actor.id != case.owner_id
        or role(actor) != "applicant"
        or not who
        or who["institution_id"] != case.institution_id
    ):
        raise HTTPException(403, "Choix et confirmation réservés au demandeur titulaire du dossier")


def request_access(session, case, actor):
    applicant(case, actor)
    item, p = policy(session, case.institution_id)
    for id in set(p.reviewers + [s.actor_id for s in p.signatories]):
        who = identity(id)
        if (
            not who
            or who["institution_id"] != case.institution_id
            or who["role"] not in {"analyst", "institution_manager", "administrator"}
        ):
            raise HTTPException(409, "Équipe de revue institutionnelle non configurée correctement")
        if session.get(CaseGrant, (case.id, id)) is None:
            session.add(CaseGrant(case_id=case.id, actor_id=id, granted_by=actor.id))
    event(
        session,
        actor,
        "review_access_requested",
        {"case_id": case.id, "policy_version": item.version},
    )
    session.commit()


def start_review(session, case, actor, body, key):
    if role(actor) not in {"analyst", "institution_manager", "administrator"}:
        raise HTTPException(403, "Revue institutionnelle requise")
    if body.expected_case_version != case.lock_version:
        raise HTTPException(409, "Version du dossier périmée")
    previous = session.scalar(
        select(InternalReview).where(
            InternalReview.case_id == case.id, InternalReview.operation_key == key
        )
    )
    if previous:
        if previous.data["request_sha256"] != canonical_hash(body.model_dump(mode="json")):
            raise HTTPException(409, "Clé de revue réutilisée pour une autre demande")
        require_fresh(session, previous, case)
        return previous
    owner = identity(case.owner_id)
    if not owner or owner["role"] != "applicant" or owner["institution_id"] != case.institution_id:
        raise HTTPException(
            409, "Un compte demandeur titulaire doit porter ce dossier avant la mise en relation"
        )
    item, p = policy(session, case.institution_id)
    allow_demo(p.demonstration, case.payload.get("data_classification", "real"))
    assessment = session.get(AssessmentRecord, body.assessment_id)
    if (
        not assessment
        or assessment.case_id != case.id
        or assessment.case_kind != case.kind
        or assessment.parent_id
    ):
        raise HTTPException(404, "Analyse principale introuvable dans ce dossier")
    report = assessment.data["result"]
    if "sections" not in report or "financial_calculations" not in report:
        raise HTTPException(409, "Analyse non terminée")
    snapshot, _ = bind_reviewed_values(
        session,
        case,
        deepcopy(case.payload),
        [
            ReviewedValueBinding.model_validate(b)
            for b in assessment.data["options"].get("validated_sources", [])
        ],
    )
    if canonical_hash(snapshot) != assessment.data["input_sha256"]:
        raise HTTPException(409, "Analyse périmée : relancer sur la version actuelle")
    if (
        p.require_approved_financial_policy
        and report["scoring"].get("criteria_validation_status") != "approved"
    ):
        raise HTTPException(
            409, "Politique financière approuvée nécessaire selon la politique de revue"
        )
    incomplete = bool(
        report.get("missing_information")
        or report["financial_calculations"]["status"] == "incomplete"
    )
    deficits = bool(
        report["financial_risk"]["period_deficits"]
        or report["financial_risk"]["negative_balance_periods"]
    )
    if incomplete and not p.allow_incomplete_with_reserves:
        raise HTTPException(409, "Données à compléter avant revue selon la politique")
    if deficits and not p.allow_deficits_with_reserves:
        raise HTTPException(409, "Déficits incompatibles avec la politique de revue")
    if len(set(body.source_ids)) != len(body.source_ids):
        raise HTTPException(422, "Justificatif dupliqué")
    if case.kind == "businesses" and p.require_business_authority_evidence:
        source = (
            session.get(SourceRecord, body.business_authority_source_id)
            if body.business_authority_source_id
            else None
        )
        sub = session.get(SubmissionRecord, source.submission_id) if source else None
        if (
            not sub
            or source.id not in body.source_ids
            or sub.case_id != case.id
            or sub.data["document_type"]
            not in {"articles", "appointment", "power_of_attorney", "borrowing_resolution"}
        ):
            raise HTTPException(
                409, "Justificatif du pouvoir d’agir à sélectionner et examiner avant approbation"
            )
    from sqlalchemy import func

    if (
        session.scalar(
            select(func.count())
            .select_from(InternalReview)
            .where(InternalReview.case_id == case.id)
        )
        >= 20
    ):
        raise HTTPException(429, "Quota de revues atteint pour ce dossier")
    id = identifier()
    review = InternalReview(
        id=id,
        case_id=case.id,
        assessment_id=assessment.id,
        case_version=case.lock_version,
        fingerprint=fingerprint(session, case),
        operation_key=key,
        state="internal_review",
        data={
            "request_sha256": canonical_hash(body.model_dump(mode="json")),
            "institution_policy_version": item.version,
            "policy_snapshot": p.model_dump(mode="json"),
            "created_by": actor.id,
            "analysis_author": assessment.data["actor_id"],
            "applicant_id": case.owner_id,
            "approvals": [],
            "decisions": [],
            "requires_reserves": incomplete or deficits,
            "business_authority_source_id": body.business_authority_source_id,
            "source_ids": body.source_ids,
        },
    )
    session.add(review)
    session.flush()
    manifest, sha = packets.build(session, case, assessment, review, body.source_ids)
    review.data = {**review.data, "approved_manifest": manifest, "approved_manifest_sha256": sha}
    event(
        session,
        actor,
        "internal_review_started",
        {"review_id": review.id, "case_id": case.id, "assessment_id": assessment.id},
    )
    session.commit()
    return review


def decide(session, review, case, actor, body):
    require_fresh(session, review, case)
    if body.expected_revision != review.revision:
        raise HTTPException(409, "Revue modifiée ; actualiser")
    if review.state not in {"internal_review", "second_validation"}:
        raise HTTPException(409, "Transition de revue interdite")
    p = review.data["policy_snapshot"]
    signer = next((s for s in p["signatories"] if s["actor_id"] == actor.id), None)
    if (
        role(actor) not in {"institution_manager", "administrator"}
        or not signer
        or actor.id == case.owner_id
    ):
        raise HTTPException(
            403, "Signataire institutionnel habilité requis ; le demandeur ne peut pas s’approuver"
        )
    if p["separate_analysis_author"] and actor.id == review.data["analysis_author"]:
        raise HTTPException(403, "Validation indépendante de l’auteur de l’analyse requise")
    if (
        review.data["requires_reserves"]
        and body.decision == "approve"
        and not body.public_reserves.strip()
    ):
        raise HTTPException(422, "Réserves communicables explicites nécessaires pour cette analyse")
    if any(d["actor_id"] == actor.id for d in review.data["decisions"]):
        raise HTTPException(409, "Une seule décision par signataire sur cette version")
    if body.decision == "approve" and not body.authorize_packet_preview:
        raise HTTPException(
            422,
            "Confirmer explicitement l’autorisation de prévisualisation privée du paquet bancaire par le demandeur",
        )
    if body.decision == "needs_completion" and not body.public_reserves.strip():
        raise HTTPException(
            422, "Préciser les compléments nécessaires dans le message communicable au demandeur"
        )
    data = deepcopy(review.data)
    decision = {
        "actor_id": actor.id,
        "signer": signer,
        "date": now().isoformat(),
        "decision": body.decision,
        "reason": body.reason,
        "public_reserves": body.public_reserves,
        "packet_preview_authorized": body.authorize_packet_preview,
    }
    if any(d["actor_id"] == actor.id for d in data["decisions"]):
        raise HTTPException(409, "Une seule décision par signataire sur cette version")
    data["decisions"].append(decision)
    if body.decision == "approve":
        data["approvals"].append(decision)
        review.state = (
            "approved" if len(data["approvals"]) >= p["required_approvals"] else "second_validation"
        )
        if review.state == "approved":
            data["approved_at"] = now().isoformat()
            for old in session.scalars(
                select(InternalReview).where(
                    InternalReview.case_id == case.id,
                    InternalReview.id != review.id,
                    InternalReview.state == "approved",
                )
            ):
                old.state = "superseded"
                for att in session.scalars(
                    select(Attestation).where(
                        Attestation.review_id == old.id, Attestation.state == "valid"
                    )
                ):
                    att.state = "replaced"
    else:
        review.state = body.decision
    review.data = data
    event(
        session,
        actor,
        "internal_decision",
        {"review_id": review.id, "case_id": case.id, "decision": body.decision},
    )
    session.commit()
    return review


def attestation_status(session, attestation):
    if attestation.state != "valid":
        return attestation.state
    signature = signing.verify(
        attestation.data["envelope"], attestation.data["signature"], attestation.data["issuer_id"]
    )
    if not signature["valid"] or signature["key_status"] == "revoked":
        return "revoked"
    review = session.get(InternalReview, attestation.review_id)
    case = session.get(CaseRecord, review.case_id)
    if review.state != "approved" or not fresh(session, review, case):
        return "replaced"
    if attestation.expires_at and utc(attestation.expires_at) <= now():
        return "expired"
    return "valid"


def issue(session, review, case, actor):
    require_fresh(session, review, case)
    if review.state != "approved":
        raise HTTPException(409, "Approbation interne complète requise")
    if role(actor) not in {"institution_manager", "administrator"}:
        raise HTTPException(403, "Émission réservée aux responsables habilités")
    old = session.scalar(select(Attestation).where(Attestation.review_id == review.id))
    if old:
        if attestation_status(session, old) != "valid":
            raise HTTPException(409, "Nouvelle revue requise pour remplacer cette attestation")
        return old
    p = review.data["policy_snapshot"]
    allow_demo(p["demonstration"], case.payload.get("data_classification", "real"))
    config, key = signing.signing_key(case.institution_id, p["demonstration"])
    assessment = session.get(AssessmentRecord, review.assessment_id)
    id = identifier()
    token = secrets.token_urlsafe(32)
    url = signing.verification_url(token)
    issued = now()
    expiry = (
        issued + timedelta(days=p["attestation_valid_days"])
        if p["attestation_valid_days"]
        else None
    )
    approvals = review.data["approvals"]
    signer = approvals[-1]["signer"]
    core = {
        "attestation_id": id,
        "issuer_id": case.institution_id,
        "issuer_name": p["issuer_name"],
        "issuer_declared_identity": p["issuer_identity_statement"],
        "case_id": case.id,
        "case_kind": case.kind,
        "case_version": review.case_version,
        "applicant_name": case.payload["name"],
        "analysis_id": assessment.id,
        "analysis_date": utc(assessment.created_at).isoformat(),
        "analysis_engine": assessment.data["engine_version"],
        "financial_policy_reference": assessment.data["result"].get("versions", {}).get("policy"),
        "internal_policy_version": review.data["institution_policy_version"],
        "internal_policy_reference": p["approved_reference"],
        "financing": assessment.data["result"]["financing_conditions"],
        "approved_at": review.data["approved_at"],
        "signer": signer,
        "review_count": len(approvals),
        "scope": p["scope"],
        "reserves": [a["public_reserves"] for a in approvals if a["public_reserves"]],
        "issued_at": issued.isoformat(),
        "expires_at": expiry.isoformat() if expiry else None,
        "approved_manifest_sha256": review.data["approved_manifest_sha256"],
        "verification_url": url,
        "key_id": config["id"],
        "demonstration": p["demonstration"],
        "notice": "La version identifiée a été analysée, revue et approuvée en interne. Aucun remboursement garanti, accord bancaire, authenticité générale ou agrément non établi n’est attesté.",
    }
    model = Presentation(
        template_id="internal_attestation",
        title="Attestation de validation interne du dossier de financement",
        audience="applicant",
        status="DÉMONSTRATION — sans valeur de certification tierce"
        if p["demonstration"]
        else "Validation interne — signature cryptographique détachée",
        metadata={
            "Dossier": case.id,
            "Édition": id,
            "Date": issued.strftime("%d/%m/%Y"),
            "Devise": "FCFA / XOF",
            "Clé de signature": config["id"],
        },
        missing_information=[],
        notices=[
            core["notice"],
            "Signature Ed25519 détachée du manifeste fourni ; le QR code et le nom imprimé ne sont pas une signature électronique certifiée.",
        ],
        verification_url=url,
        sections=[
            table_section("Périmètre de l’attestation", core),
            Section(
                title="Informations contrôlées et réserves",
                paragraphs=core["reserves"]
                or [
                    "Contrôles limités à la revue déclarée ; aucune authenticité générale des pièces certifiée."
                ],
            ),
        ],
        template_version="internal-attestation-v1",
        platform_name=p["issuer_name"],
    )
    _, pdf = render_isolated(model)
    file = packets.add_file(
        session,
        review,
        "attestation",
        pdf,
        metadata={"attestation_id": id, "core_sha256": signing.digest(signing.canonical(core))},
    )
    envelope = {
        "schema_version": "signed-attestation-envelope-v1",
        "core": core,
        "approved_manifest": review.data["approved_manifest"],
        "attestation_file": packets.info(file),
    }
    signature = signing.sign(envelope, config, key)
    attestation = Attestation(
        id=id,
        review_id=review.id,
        public_token=token,
        key_id=config["id"],
        state="valid",
        created_at=issued,
        expires_at=expiry,
        data={
            "issuer_id": case.institution_id,
            "envelope": envelope,
            "signature": signature,
            "file_id": file.id,
        },
    )
    session.add(attestation)
    event(
        session,
        actor,
        "attestation_issued",
        {"attestation_id": id, "review_id": review.id, "key_id": config["id"]},
    )
    session.commit()
    return attestation


def partner_eligible(session, partner, case, review):
    d = partner.data["configuration"]
    if (
        partner.issuer_id != case.institution_id
        or partner.status not in {"active", "demonstration"}
        or partner.data.get("connection_status") != "verified"
    ):
        raise HTTPException(409, "Banque non activée ou connexion indisponible")
    if partner.status == "demonstration":
        allow_demo(True, case.payload.get("data_classification", "real"))
    if d["demonstration"] != review.data["policy_snapshot"]["demonstration"]:
        raise HTTPException(409, "Configuration de démonstration et dossier réel incompatibles")
    profile = case.payload.get("profile", case.payload.get("mode"))
    if (
        case.kind not in d["cores"]
        or profile not in d["profiles"]
        or case.payload["analysis_details"]["funding"]["product_id"] not in d["products"]
    ):
        raise HTTPException(409, "Profil ou produit non couvert par ce partenaire")
    return d


def review_view(session, review, case, actor):
    result = {
        "id": review.id,
        "case_id": review.case_id,
        "case_version": review.case_version,
        "assessment_id": review.assessment_id,
        "state": review.state if fresh(session, review, case) else "superseded",
        "revision": review.revision,
        "approvals_count": len(review.data["approvals"]),
        "required_approvals": review.data["policy_snapshot"]["required_approvals"],
        "approved_at": review.data.get("approved_at"),
        "manifest_sha256": review.data["approved_manifest_sha256"],
        "files": review.data["approved_manifest"]["files"],
        "public_reserves": [d["public_reserves"] for d in review.data["approvals"]],
        "public_decisions": [
            {k: d[k] for k in ["decision", "date", "public_reserves"]}
            for d in review.data["decisions"]
        ],
        "business_authority_source_id": review.data.get("business_authority_source_id"),
    }
    if role(actor) != "applicant":
        result["decisions"] = review.data["decisions"]
    att = session.scalar(select(Attestation).where(Attestation.review_id == review.id))
    result["attestation"] = (
        {
            "id": att.id,
            "state": attestation_status(session, att),
            "file_id": att.data["file_id"],
            "verification_url": att.data["envelope"]["core"]["verification_url"],
        }
        if att
        else None
    )
    if att:
        result["files"] = result["files"] + [att.data["envelope"]["attestation_file"]]
    return result
