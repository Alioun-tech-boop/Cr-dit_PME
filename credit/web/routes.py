"""Contrats de reprise et lecture publiée ; contrôles d'objet à chaque lecture."""

from copy import deepcopy
from fastapi import Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from credit.persistence import JourneyDraft, CaseRecord, AssessmentRecord, PrintPublication
from credit.security.access import public_payload, role
from credit.individuals.contracts import IndividualCase
from credit.businesses.contracts import BusinessCase
from credit.assessment.routes import view as assessment_view
from credit.assessment.application import canonical_hash
from credit.printing.presentation import public_financial
from credit.web.budget import budget_chart
from credit.partners.models import CaseGrant


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(individuals|businesses)$")
    draft: dict
    case_id: str | None = None
    case_version: int | None = None


class Finalize(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict
    case_version: int | None = None


def register_web_routes(app, db, get_case, save_case):
    def draft_view(item):
        return {
            "id": item.id,
            "kind": item.kind,
            "version": item.version,
            "case_id": item.case_id,
            "case_version": item.payload.get("_case_version"),
            "draft": deepcopy(item.payload),
            "updated_at": item.updated_at,
        }

    def find(session, draft_id):
        item = session.scalar(
            select(JourneyDraft).where(JourneyDraft.id == draft_id).with_for_update()
        )
        actor = session.info["actor"]
        if not item or item.owner_id != actor.id or item.institution_id != actor.institution_id:
            raise HTTPException(404, "Brouillon introuvable")
        return item

    def version_check(item, version):
        if version is None:
            raise HTTPException(428, "If-Match requis")
        if version.strip('"') != str(item.version):
            raise HTTPException(409, "Brouillon modifié ; rechargez-le avant de poursuivre")

    def clean(body):
        import json

        if len(json.dumps(body.draft).encode()) > 500000:
            raise HTTPException(413, "Brouillon trop volumineux")
        data = deepcopy(body.draft)
        if data.get("core") != body.kind:
            raise HTTPException(422, "Noyau incompatible")
        # Un brouillon UI n'est ni une preuve validée ni une analyse : ne jamais le consommer directement.
        for key in ("report", "fixture", "original", "remote", "remoteDraft", "sourceDemo"):
            data.pop(key, None)
        return {k: v for k, v in data.items() if not k.startswith("_")}

    @app.get("/journeys")
    def listing(session: Session = Depends(db), limit: int = Query(100, ge=1, le=100)):
        actor = session.info["actor"]
        return [
            draft_view(x)
            for x in session.scalars(
                select(JourneyDraft)
                .where(
                    JourneyDraft.owner_id == actor.id,
                    JourneyDraft.institution_id == actor.institution_id,
                )
                .order_by(JourneyDraft.updated_at.desc())
                .limit(limit)
            )
        ]

    @app.post("/journeys", status_code=201)
    def create(
        body: DraftInput,
        session: Session = Depends(db),
        idempotency_key: str = Header(min_length=16, max_length=128),
    ):
        actor = session.info["actor"]
        key = canonical_hash(
            {"actor": actor.id, "institution": actor.institution_id, "key": idempotency_key}
        )
        previous = session.scalar(select(JourneyDraft).where(JourneyDraft.operation_key == key))
        if previous:
            if previous.kind != body.kind or clean(body) != {
                k: v for k, v in previous.payload.items() if not k.startswith("_")
            }:
                raise HTTPException(409, "Clé incompatible")
            return draft_view(previous)
        count = session.scalar(
            select(func.count()).select_from(JourneyDraft).where(JourneyDraft.owner_id == actor.id)
        )
        if count >= 1000:
            raise HTTPException(429, "Quota de brouillons atteint")
        linked = get_case(session, body.kind, body.case_id) if body.case_id else None
        if linked and body.case_version != linked.lock_version:
            raise HTTPException(409, "Le dossier lié a changé ; rechargez-le")
        initial = clean(body)
        if linked:
            initial["_case_version"] = linked.lock_version
        item = JourneyDraft(
            owner_id=actor.id,
            institution_id=actor.institution_id,
            kind=body.kind,
            payload=initial,
            case_id=linked.id if linked else None,
            operation_key=key,
        )
        session.add(item)
        session.commit()
        return draft_view(item)

    @app.get("/journeys/{draft_id}")
    def read(draft_id: str, session: Session = Depends(db)):
        return draft_view(find(session, draft_id))

    @app.put("/journeys/{draft_id}")
    def update(
        draft_id: str,
        body: DraftInput,
        session: Session = Depends(db),
        if_match: str | None = Header(None),
    ):
        item = find(session, draft_id)
        version_check(item, if_match)
        if item.kind != body.kind:
            raise HTTPException(409, "Noyau immuable")
        item.payload = {
            **{k: v for k, v in item.payload.items() if k.startswith("_")},
            **clean(body),
        }
        session.commit()
        return draft_view(item)

    @app.post("/journeys/{draft_id}/case")
    def finalize(
        draft_id: str,
        body: Finalize,
        session: Session = Depends(db),
        if_match: str | None = Header(None),
    ):
        item = find(session, draft_id)
        previous = get_case(session, item.kind, item.case_id) if item.case_id else None
        # Réponse perdue : reconnaître l'instantané déjà enregistré avant le contrôle de version.
        if previous and canonical_hash(previous.payload) == item.payload.get("_case_sha256"):
            model = IndividualCase if item.kind == "individuals" else BusinessCase
            parsed = model.model_validate(body.payload)
            if canonical_hash(parsed.model_dump(mode="json")) == item.payload.get(
                "_case_request_sha256"
            ):
                return {
                    "id": previous.id,
                    "kind": item.kind,
                    "version": previous.lock_version,
                    "data": public_payload(previous.payload, session.info["actor"]),
                    "draft_version": item.version,
                }
        version_check(item, if_match)
        model = IndividualCase if item.kind == "individuals" else BusinessCase
        try:
            parsed = model.model_validate(body.payload)
        except ValueError:
            raise HTTPException(
                422, "Données métier invalides ; vérifiez périodes et montants"
            ) from None
        saved = save_case(
            session,
            item.kind,
            parsed,
            previous,
            str(body.case_version) if body.case_version is not None else None,
            commit=False,
        )
        item.case_id = saved["id"]
        item.payload = {
            **item.payload,
            "_case_version": saved["version"],
            "_case_sha256": canonical_hash(session.get(CaseRecord, saved["id"]).payload),
            "_case_request_sha256": canonical_hash(parsed.model_dump(mode="json")),
        }
        session.commit()
        return {**saved, "draft_version": item.version}

    def register(kind):
        @app.get(f"/{kind}", name=f"list_{kind}")
        def cases(
            session: Session = Depends(db),
            limit: int = Query(100, ge=1, le=100),
            offset: int = Query(0, ge=0, le=100000),
        ):
            actor = session.info["actor"]
            query = select(CaseRecord).where(
                CaseRecord.kind == kind,
                CaseRecord.institution_id == actor.institution_id,
                or_(
                    CaseRecord.owner_id == actor.id,
                    CaseRecord.id.in_(actor.case_ids),
                    CaseRecord.id.in_(
                        select(CaseGrant.case_id).where(CaseGrant.actor_id == actor.id)
                    ),
                ),
            )
            return [
                {
                    "id": x.id,
                    "kind": kind,
                    "version": x.lock_version,
                    "data": public_payload(x.payload, actor),
                }
                for x in session.scalars(
                    query.order_by(CaseRecord.updated_at.desc()).offset(offset).limit(limit)
                )
            ]

        @app.get(f"/{kind}/{{case_id}}/published-assessment", name=f"published_{kind}")
        def published(case_id: str, session: Session = Depends(db)):
            get_case(session, kind, case_id)
            items = session.scalars(
                select(AssessmentRecord)
                .where(
                    AssessmentRecord.case_id == case_id,
                    AssessmentRecord.case_kind == kind,
                    AssessmentRecord.parent_id.is_(None),
                )
                .order_by(AssessmentRecord.created_at.desc())
            ).all()
            staff = role(session.info["actor"]) != "applicant"
            if staff and items:
                return {
                    "audience": "analyst",
                    "assessment_id": items[0].id,
                    "report": {
                        **assessment_view(items[0])["result"],
                        "budget_chart": budget_chart(
                            items[0].data["result"],
                            items[0].data["input_snapshot"],
                            case_id=case_id,
                            assessment_id=items[0].id,
                        ),
                    },
                }
            for item in items:
                publication = session.scalar(
                    select(PrintPublication)
                    .where(PrintPublication.assessment_id == item.id)
                    .order_by(PrintPublication.created_at.desc())
                )
                if not publication or not any(
                    publication.data.get(k) for k in ("financial_results", "suggestions")
                ):
                    continue
                report = item.data["result"]
                result = {
                    "core": kind,
                    "engine_version": report["engine_version"],
                    "financial_calculations": public_financial(report)
                    if publication.data.get("financial_results")
                    else {"periods": []},
                    "suggestions": [],
                    "publication_id": publication.id,
                }
                if publication.data.get("financial_results"):
                    result["budget_chart"] = budget_chart(
                        report, item.data["input_snapshot"], case_id=case_id, assessment_id=item.id
                    )
                if publication.data.get("suggestions"):
                    result["suggestions"] = [
                        {
                            k: deepcopy(s[k])
                            for k in (
                                "id",
                                "problem",
                                "action",
                                "recipient",
                                "priority",
                                "prerequisites",
                                "simulated_effect",
                                "costs_and_limits",
                                "evidence_needed",
                            )
                        }
                        for s in report["suggestions"]
                        if s["recipient"] == "demandeur"
                    ]
                return {"audience": "applicant", "assessment_id": item.id, "report": result}
            raise HTTPException(404, "Aucune analyse communiquée pour ce dossier")

    for kind in ("individuals", "businesses"):
        register(kind)
