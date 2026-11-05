"""Agrégats d'activité institutionnels, sans données financières individuelles."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from credit.persistence import CaseRecord, AssessmentRecord, WebRegistration
from credit.partners.models import Partner, Transmission, Outbox, PartnerEvent
from credit.institutions.models import InstitutionAccount, BankDecisionRecord


def build(session, institution_id, days):
    start = datetime.now(timezone.utc) - timedelta(days=days)

    def count(stmt):
        return session.scalar(stmt) or 0

    cases = select(CaseRecord.id).where(CaseRecord.institution_id == institution_id)
    transmissions = select(Transmission.id).where(Transmission.issuer_id == institution_id)
    partners = select(Partner.id).where(Partner.issuer_id == institution_id)
    counters = {
        "cases": count(
            select(func.count())
            .select_from(CaseRecord)
            .where(CaseRecord.institution_id == institution_id)
        ),
        "analyses_in_period": count(
            select(func.count())
            .select_from(AssessmentRecord)
            .where(AssessmentRecord.case_id.in_(cases), AssessmentRecord.created_at >= start)
        ),
        "registered_applicants": count(
            select(func.count())
            .select_from(WebRegistration)
            .where(WebRegistration.institution_id == institution_id)
        ),
        "managed_bank_accounts": count(
            select(func.count())
            .select_from(InstitutionAccount)
            .where(
                InstitutionAccount.partner_id.in_(partners), InstitutionAccount.status != "deleted"
            )
        ),
        "transmissions": count(
            select(func.count())
            .select_from(Transmission)
            .where(Transmission.issuer_id == institution_id)
        ),
        "approved_offers": count(
            select(func.count())
            .select_from(BankDecisionRecord)
            .where(
                BankDecisionRecord.transmission_id.in_(transmissions),
                BankDecisionRecord.decision == "approved",
            )
        ),
        "refusals": count(
            select(func.count())
            .select_from(BankDecisionRecord)
            .where(
                BankDecisionRecord.transmission_id.in_(transmissions),
                BankDecisionRecord.decision == "refused",
            )
        ),
        "failed_deliveries": count(
            select(func.count())
            .select_from(Outbox)
            .where(Outbox.transmission_id.in_(transmissions), Outbox.state == "failed")
        ),
    }
    states = dict(
        session.execute(
            select(Transmission.state, func.count())
            .where(Transmission.issuer_id == institution_id)
            .group_by(Transmission.state)
        ).all()
    )
    grouped = {}
    for day, n in session.execute(
        select(func.date(AssessmentRecord.created_at), func.count())
        .where(AssessmentRecord.case_id.in_(cases), AssessmentRecord.created_at >= start)
        .group_by(func.date(AssessmentRecord.created_at))
    ):
        grouped[str(day)] = n
    series = [
        {
            "date": (start + timedelta(days=i)).date().isoformat(),
            "analyses": grouped.get((start + timedelta(days=i)).date().isoformat(), 0),
        }
        for i in range(days + 1)
    ]
    events = session.scalars(
        select(PartnerEvent)
        .where(
            (PartnerEvent.institution_id == institution_id)
            | (PartnerEvent.transmission_id.in_(transmissions))
        )
        .order_by(PartnerEvent.created_at.desc())
        .limit(50)
    ).all()
    return {
        "period_days": days,
        "generated_at": datetime.now(timezone.utc),
        "counters": counters,
        "transmission_states": states,
        "analysis_series": series,
        "events": [
            {
                "id": e.id,
                "action": e.action,
                "actor_id": e.actor_id,
                "created_at": e.created_at,
                "transmission_id": e.transmission_id,
            }
            for e in events
        ],
        "definitions": {
            "cases": "Dossiers appartenant à votre institution, toutes dates confondues.",
            "analyses_in_period": "Exécutions et simulations enregistrées dans la période.",
            "approved_offers": "Décisions favorables enregistrées ; ne représentent pas des décaissements.",
            "registered_applicants": "Comptes demandeurs inscrits dans la base, hors identités techniques du registre serveur.",
        },
    }
