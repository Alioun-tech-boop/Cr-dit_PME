"""Invalider les autorisations futures, jamais les fichiers ou rapports déjà émis."""

from sqlalchemy import event, select
from sqlalchemy.orm import Session
from credit.persistence import (
    CaseRecord,
    SubmissionRecord,
    SourceRecord,
    DocumentRun,
    ReviewRecord,
    StructuredRecord,
    DocumentRecord,
)
from credit.partners.models import InternalReview, Attestation, PartnerEvent


@event.listens_for(Session, "before_flush")
def invalidate_approvals(session, flush_context, instances):
    case_ids = set()
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if obj in session.dirty and not session.is_modified(obj, include_collections=False):
            continue
        if isinstance(obj, CaseRecord):
            case_ids.add(obj.id)
        elif isinstance(obj, (SubmissionRecord, StructuredRecord, DocumentRecord)):
            case_ids.add(obj.case_id)
        elif isinstance(obj, (SourceRecord, DocumentRun)):
            sub = session.get(SubmissionRecord, obj.submission_id)
            if sub:
                case_ids.add(sub.case_id)
        elif isinstance(obj, ReviewRecord):
            run = session.get(DocumentRun, obj.run_id)
            sub = session.get(SubmissionRecord, run.submission_id) if run else None
            if sub:
                case_ids.add(sub.case_id)
    ids = case_ids - {None}
    if ids:
        list(
            session.scalars(
                select(CaseRecord.id)
                .where(CaseRecord.id.in_(ids))
                .order_by(CaseRecord.id)
                .with_for_update()
            )
        )
    for id in ids:
        for review in session.scalars(
            select(InternalReview).where(
                InternalReview.case_id == id,
                InternalReview.state.in_(["internal_review", "second_validation", "approved"]),
            )
        ):
            review.state = "superseded"
            for att in session.scalars(
                select(Attestation).where(
                    Attestation.review_id == review.id, Attestation.state == "valid"
                )
            ):
                att.state = "replaced"
            actor = session.info.get("actor")
            case = session.get(CaseRecord, id)
            session.add(
                PartnerEvent(
                    actor_id=actor.id if actor else "system",
                    institution_id=case.institution_id or "",
                    action="approval_superseded",
                    data={
                        "case_id": id,
                        "review_id": review.id,
                        "reason": "Données ou pièces modifiées ; nouvelle analyse/revue requise.",
                    },
                )
            )
