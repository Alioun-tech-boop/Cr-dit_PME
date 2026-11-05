"""Transitions bancaires indépendantes de l'analyse et de la décision interne."""

from copy import deepcopy
from fastapi import HTTPException
from sqlalchemy import select
from credit.partners.models import PartnerEvent, BankAttachment, Partner
from credit.partners import service, signing
from credit.security.access import role

TRANSITIONS = {
    "received": {"transmitted"},
    "under_review": {"received", "additional_information"},
    "additional_information": {"received", "under_review", "additional_information"},
    "decision": {"received", "under_review", "additional_information", "decision_available"},
}


def apply(session, t, actor, body, key, sequence=None):
    previous = session.scalar(
        select(PartnerEvent).where(
            PartnerEvent.transmission_id == t.id, PartnerEvent.event_key == key
        )
    )
    request_sha = signing.digest(
        signing.canonical(
            {k: v for k, v in body.model_dump(mode="json").items() if k != "expected_revision"}
        )
    )
    if previous:
        if previous.data["request_sha256"] != request_sha:
            raise HTTPException(409, "Identifiant d’événement réutilisé avec un autre contenu")
        return previous
    if sequence is not None and sequence <= t.data.get("last_sequence", 0):
        result = service.event(
            session,
            actor,
            "ignored_out_of_order",
            {"request_sha256": request_sha, "sequence": sequence},
            t,
            key,
        )
        session.commit()
        return result
    if sequence is None and body.expected_revision != t.revision:
        raise HTTPException(409, "Suivi modifié ; actualiser")
    partner = session.get(Partner, t.partner_id)
    from credit.partners.configuration import allow_demo

    allow_demo(t.data["demonstration"], "synthetic" if t.data["demonstration"] else "real")
    if partner.status not in {"active", "demonstration"} or partner.data.get("archived_at"):
        raise HTTPException(409, "Établissement suspendu ou non actif : décision indisponible")
    if t.state not in TRANSITIONS[body.action]:
        raise HTTPException(409, "Transition bancaire interdite ou événement reçu dans le désordre")
    if body.action == "additional_information" and not body.requested_information:
        raise HTTPException(422, "Préciser les compléments demandés")
    if body.action == "decision":
        if (
            t.data.get("decision", {}).get("kind") == "formal_offer"
            and body.decision != "disbursement_confirmed"
        ):
            raise HTTPException(
                409,
                "Offre formelle déjà émise ; révoquer explicitement plutôt que réécrire la décision",
            )
        if not body.decision:
            raise HTTPException(422, "Nature de la décision bancaire requise")
        if body.decision == "disbursement_confirmed":
            from credit.institutions.models import BankDecisionRecord

            agreement = session.scalar(
                select(BankDecisionRecord).where(BankDecisionRecord.transmission_id == t.id)
            )
            if agreement is not None and agreement.state == "revoked":
                raise HTTPException(
                    409, "Offre révoquée : décaissement non enregistrable sur cette offre"
                )
        if body.decision in {"formal_offer", "disbursement_confirmed"}:
            if (
                role(actor) != "bank_manager"
                or not body.external_reference
                or not body.attachment_ids
            ):
                raise HTTPException(403, "Référence externe, pièce et responsable bancaire requis")
        if (
            body.decision == "disbursement_confirmed"
            and t.data.get("decision", {}).get("kind") != "formal_offer"
        ):
            raise HTTPException(
                409, "Décaissement suivi uniquement après une offre formelle enregistrée"
            )
        if t.data.get("decision", {}).get("kind") in {"refused", "disbursement_confirmed"}:
            raise HTTPException(
                409, "Décision finale déjà enregistrée ; aucune régression automatique"
            )
    for id in body.attachment_ids:
        file = session.get(BankAttachment, id)
        if not file or file.transmission_id != t.id:
            raise HTTPException(404, "Pièce de réponse introuvable")
    if body.action == "decision" and t.data.get("decision"):
        ranks = {
            "favorable_opinion": 1,
            "conditional_offer": 2,
            "formal_offer": 3,
            "disbursement_confirmed": 4,
            "refused": 4,
        }
        if ranks[body.decision] < ranks[t.data["decision"]["kind"]]:
            raise HTTPException(
                409,
                "Une décision moins avancée ne peut pas remplacer automatiquement la décision enregistrée",
            )
    data = deepcopy(t.data)
    if sequence is not None:
        data["last_sequence"] = sequence
    data["shared_attachment_ids"] = sorted(
        set(data.get("shared_attachment_ids", []) + body.attachment_ids)
    )
    if body.action == "decision":
        data["decision"] = {
            "kind": body.decision,
            "reason": body.reason,
            "external_reference": body.external_reference,
            "actor_id": actor.id,
            "date": service.now().isoformat(),
            "attachment_ids": body.attachment_ids,
        }
        t.state = "decision_available"
    else:
        t.state = {
            "additional_information": "additional_information",
            "under_review": "under_review",
            "received": "received",
        }[body.action]
    if body.action == "additional_information":
        data["requested_information"] = body.requested_information
    t.data = data
    result = service.event(
        session,
        actor,
        "bank_" + body.action,
        {
            "request_sha256": request_sha,
            "sequence": sequence,
            **body.model_dump(mode="json"),
            "date": service.now().isoformat(),
        },
        t,
        key,
    )
    session.commit()
    return result
