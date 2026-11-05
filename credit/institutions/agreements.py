"""Conditions déclarées par la banque, calculs décimaux et document immuable."""

from datetime import date
from decimal import Decimal
import secrets
from fastapi import HTTPException
from sqlalchemy import select
from credit.partners import bank, delivery, signing
from credit.partners.models import Partner, Attestation, BankAttachment
from credit.partners.contracts import BankAction
from credit.institutions.models import BankDecisionRecord, ClientMessage, InstitutionAccount
from credit.persistence import identifier, now
from credit.printing.contracts import Presentation, Section, Table
from credit.printing.isolation import render_isolated
from credit.printing.presentation import french_date
from credit.shared.schedule import monthly_schedule


def normalized_terms(terms):
    if terms.validity_until < date.today() or terms.disbursement_date < date.today():
        raise HTTPException(
            422, "Validité et décaissement prévisionnel ne doivent pas être périmés"
        )
    try:
        if terms.schedule:
            rows = [x.model_dump(mode="json") for x in terms.schedule]
        else:
            loan = monthly_schedule(
                terms.principal,
                terms.annual_nominal_rate,
                terms.months,
                terms.first_due_date,
                terms.fee_per_payment,
            )
            rows = [
                {
                    "date": (p.due_date or p.period).isoformat(),
                    "principal": str(p.principal.value),
                    "interest": str(p.interest.value),
                    "fees": str(p.fees.value),
                }
                for p in loan.schedule
            ]
    except (ValueError, OverflowError) as exc:
        raise HTTPException(422, "Échéancier hors des limites techniques") from exc
    interest = sum(Decimal(x["interest"]) for x in rows)
    fees = sum(Decimal(x["fees"]) for x in rows) + terms.upfront_fees + terms.insurance_cost
    if sum(Decimal(x["principal"]) for x in rows) != terms.principal:
        raise HTTPException(422, "Capital remboursé incohérent")
    result = terms.model_dump(mode="json")
    result["schedule"] = rows
    result["total_interest"] = str(interest)
    result["total_fees_and_insurance"] = str(fees)
    result["total_credit_cost"] = str(interest + fees)
    result["total_due"] = str(terms.principal + interest + fees)
    result["last_due_date"] = rows[-1]["date"]
    result["schedule_method"] = (
        "explicit" if terms.schedule else "monthly_nominal_annual_divided_by_12"
    )
    return result


def present(t, partner, core, terms, decision_id, url, signed, actor, demonstration):
    currency = "FCFA / XOF"
    tables = [
        Table(
            columns=["Condition", "Valeur déclarée par la banque"],
            rows=[
                ["Emprunteur", core["applicant_name"]],
                ["Établissement", partner.data["configuration"]["name"]],
                ["Référence de l’offre", terms["reference"]],
                ["Produit", terms["product"]],
                ["Montant financé", terms["principal"] + " " + currency],
                ["Taux nominal annuel", str(Decimal(terms["annual_nominal_rate"]) * 100) + " %"],
                ["Date prévisionnelle de décaissement", french_date(terms["disbursement_date"])],
                [
                    "Première / dernière échéance",
                    french_date(terms["first_due_date"])
                    + " / "
                    + french_date(terms["last_due_date"]),
                ],
                ["Nombre d’échéances", str(terms["months"])],
                ["Frais initiaux séparés", terms["upfront_fees"] + " " + currency],
                ["Coût d’assurance chiffré", terms["insurance_cost"] + " " + currency],
                ["Intérêts totaux", terms["total_interest"] + " " + currency],
                [
                    "Coût du crédit (intérêts, frais et assurance)",
                    terms["total_credit_cost"] + " " + currency,
                ],
                ["Total à payer, capital compris", terms["total_due"] + " " + currency],
                ["Validité de l’offre", french_date(terms["validity_until"])],
            ],
        )
    ]
    sections = [Section(title="Conditions de financement", tables=tables)]
    for title, key in [
        ("Conditions de décaissement", "disbursement_conditions"),
        ("Assurance", "insurance"),
        ("Garanties", "collateral"),
        ("Mode de remboursement", "payment_method"),
        ("Remboursement anticipé", "early_repayment"),
        ("Retards et pénalités", "late_payment"),
    ]:
        sections.append(Section(title=title, paragraphs=[terms[key]]))
    sections.append(
        Section(
            title="Échéancier de référence — FCFA / XOF",
            tables=[
                Table(
                    columns=["Date", "Capital", "Intérêts", "Frais", "Total"],
                    rows=[
                        [
                            french_date(r["date"]),
                            r["principal"],
                            r["interest"],
                            r["fees"],
                            str(sum(Decimal(r[k]) for k in ["principal", "interest", "fees"])),
                        ]
                        for r in terms["schedule"]
                    ],
                )
            ],
        )
    )
    sections.append(
        Section(
            title="Émission et portée",
            paragraphs=[
                "Décision favorable enregistrée par "
                + terms["signatory_name"]
                + " — "
                + terms["signatory_function"]
                + ".",
                "Cette offre doit être acceptée selon les modalités de l’établissement. Elle ne prouve ni la signature de l’emprunteur ni un décaissement.",
                "Échéancier mensuel généré : taux nominal annuel divisé par 12 et ajustement de la dernière échéance. Un échéancier explicite fourni par la banque prévaut. Aucun taux effectif réglementaire calculé.",
                "Les frais initiaux et l’assurance chiffrée sont ajoutés au coût total ; ils ne sont pas incorporés au capital par le générateur.",
                "Signature cryptographique détachée du manifeste couvrant l’empreinte du PDF. Aucune certification par un prestataire de confiance revendiquée."
                if signed
                else "DOCUMENT NON SIGNÉ : aucun certificat électronique ni authentification cryptographique de l’émetteur.",
            ],
        )
    )
    return Presentation(
        template_id="bank_agreement",
        template_version="bank-agreement-1.0.0",
        title="Attestation d’accord de financement",
        audience="applicant",
        status=("DÉMONSTRATION — " if demonstration else "")
        + ("Offre bancaire — signature détachée" if signed else "Offre bancaire — NON SIGNÉE"),
        metadata={
            "Document": decision_id,
            "Édition": decision_id,
            "Dossier": t.case_id,
            "Version approuvée": str(core["case_version"]),
            "Analyse": core["analysis_id"],
            "Banque": partner.data["configuration"]["name"],
            "Émis le": now().isoformat(),
            "Auteur habilité": actor.id,
            "Devise": currency,
        },
        missing_information=[],
        notices=[
            "Ce document conserve les conditions déclarées par la banque. La validité cryptographique et la portée juridique sont distinctes."
        ],
        sections=sections,
        verification_url=url,
    )


def decision_view(record):
    return {
        "id": record.id,
        "transmission_id": record.transmission_id,
        "decision": record.decision,
        "state": record.state,
        "created_at": record.created_at,
        "sha256": record.sha256,
        "bank_name": record.data["bank_name"],
        "public_reason": record.data["public_reason"],
        "terms": record.data.get("terms"),
        "signature": record.data.get("signature"),
        "verification_url": record.data.get("verification_url"),
        "demonstration": record.data["demonstration"],
        "verification": verification(record) if record.payload else None,
    }


def issue(session, t, actor, body, key):
    request_sha = signing.digest(
        signing.canonical(body.model_dump(mode="json", exclude={"expected_revision"}))
    )
    previous = session.scalar(
        select(BankDecisionRecord).where(BankDecisionRecord.transmission_id == t.id)
    )
    if previous:
        if previous.operation_key == key and previous.request_sha256 == request_sha:
            return previous
        raise HTTPException(409, "Décision déjà émise ; son historique ne peut pas être réécrit")
    if t.revision != body.expected_revision:
        raise HTTPException(409, "Dossier modifié ; actualiser avant décision")
    if t.state not in {"received", "under_review", "additional_information"}:
        raise HTTPException(409, "Confirmer la réception avant de décider")
    if t.data.get("decision", {}).get("kind") in {
        "formal_offer",
        "refused",
        "disbursement_confirmed",
    }:
        raise HTTPException(409, "Une décision bancaire définitive existe déjà")
    partner = session.get(Partner, t.partner_id)
    from credit.partners.configuration import allow_demo

    allow_demo(t.data["demonstration"], "synthetic" if t.data["demonstration"] else "real")
    if partner.status not in {"active", "demonstration"} or partner.data.get("archived_at"):
        raise HTTPException(409, "Établissement non actif")
    demonstration = t.data["demonstration"]
    id = identifier()
    data = {
        "bank_name": partner.data["configuration"]["name"],
        "public_reason": body.public_reason,
        "demonstration": demonstration,
        "actor_id": actor.id,
    }
    record = BankDecisionRecord(
        id=id,
        transmission_id=t.id,
        actor_id=actor.id,
        bank_institution_id=t.bank_institution_id,
        decision=body.decision,
        state="refused",
        operation_key=key,
        request_sha256=request_sha,
        data=data,
    )
    attachments = []
    if body.decision == "approved":
        check = delivery.integrity(session, t)
        if (
            not check["valid"]
            or not check["trusted_keys"]
            or check["attestation_status"] != "valid"
        ):
            raise HTTPException(
                409, "Paquet ou attestation interne non valides : nouvelle revue requise"
            )
        terms = normalized_terms(body.terms)
        if body.preview_sha256 != signing.digest(signing.canonical(terms)):
            raise HTTPException(409, "Prévisualiser les conditions et leur coût avant de confirmer")
        managed = session.get(InstitutionAccount, actor.id)
        if managed and (
            terms["signatory_name"] != managed.professional_name
            or terms["signatory_function"] != managed.function
        ):
            raise HTTPException(
                422, "Utiliser l’identité professionnelle administrée du signataire"
            )
        signed = body.signature_mode == "detached"
        config = key_object = None
        if signed:
            config, key_object = signing.signing_key(t.bank_institution_id, demonstration)
            if not demonstration and t.partner_id not in config.get("partner_ids", []):
                raise HTTPException(503, "Clé bancaire non rattachée à cet établissement")
        token = secrets.token_urlsafe(32)
        url = signing.verification_url(token).replace(
            "/verify-attestation.html?", "/verify-bank-agreement.html?"
        )
        att = session.get(Attestation, t.attestation_id)
        core = att.data["envelope"]["core"]
        model = present(t, partner, core, terms, id, url, signed, actor, demonstration)
        _, payload = render_isolated(model)
        sha = signing.digest(payload)
        envelope = {
            "schema": "credix.bank-agreement.v1",
            "id": id,
            "issuer_id": t.bank_institution_id,
            "partner_id": t.partner_id,
            "transmission_id": t.id,
            "case_version": core["case_version"],
            "terms": terms,
            "pdf_sha256": sha,
            "presentation_sha256": signing.digest(signing.canonical(model.model_dump(mode="json"))),
            "issued_at": model.metadata["Émis le"],
            "signatory_actor_id": actor.id,
        }
        signature = signing.sign(envelope, config, key_object) if signed else None
        data.update(
            terms=terms,
            presentation=model.model_dump(mode="json"),
            envelope=envelope,
            signature=signature,
            verification_url=url,
        )
        record.state = "issued_signed" if signed else "issued_unsigned"
        record.public_token = token
        record.payload = payload
        record.sha256 = sha
        file = BankAttachment(
            id=identifier(),
            transmission_id=t.id,
            actor_id=actor.id,
            category="offer",
            media_type="application/pdf",
            sha256=sha,
            payload=payload,
            data={
                "name": "accord-" + id + ".pdf",
                "generated_agreement_id": id,
                "malware_status": "generated_document",
            },
        )
        session.add(file)
        session.flush()
        attachments = [file.id]
    session.add(record)
    session.flush()
    session.add(
        ClientMessage(
            actor_id=t.applicant_id,
            institution_id=t.issuer_id,
            transmission_id=t.id,
            decision_id=id,
            event_key="bank-decision:" + id,
            title=(
                "Offre de financement reçue"
                if body.decision == "approved"
                else "Décision bancaire : refus"
            )
            + " — "
            + data["bank_name"],
        )
    )
    action = BankAction(
        expected_revision=t.revision,
        action="decision",
        reason=body.public_reason,
        decision="formal_offer" if body.decision == "approved" else "refused",
        external_reference=body.terms.reference if body.terms else None,
        attachment_ids=attachments,
    )
    bank.apply(session, t, actor, action, key)  # Commit unique : décision, PDF et notification.
    return record


def verification(record):
    envelope = record.data.get("envelope", {})
    intact = (
        record.payload is not None
        and signing.digest(record.payload) == record.sha256 == envelope.get("pdf_sha256")
        and envelope.get("id") == record.id
        and envelope.get("issuer_id") == record.bank_institution_id
        and envelope.get("transmission_id") == record.transmission_id
        and envelope.get("terms") == record.data.get("terms")
        and signing.digest(signing.canonical(record.data.get("presentation", {})))
        == envelope.get("presentation_sha256")
    )
    signature = record.data.get("signature")
    if signature:
        try:
            result = signing.verify(record.data["envelope"], signature, record.bank_institution_id)
            valid = result["valid"] and result["key_status"] != "revoked" and intact
        except HTTPException:
            valid = False
    else:
        valid = False
    expired = (
        record.data.get("terms", {}).get("validity_until", "9999-12-31") < date.today().isoformat()
    )
    status = (
        "revoked"
        if record.state == "revoked"
        else "expired"
        if expired
        else "valid"
        if valid
        else "unsigned"
        if not signature
        else "invalid"
    )
    return {
        "status": status,
        "cryptographic_valid": valid,
        "integrity_valid": intact,
        "third_party_certification": False,
    }
