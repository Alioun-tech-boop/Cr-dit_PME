from credit.security.errors import public_error
import os
from datetime import timezone

from fastapi import Depends, HTTPException, Query, Header
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from credit.assessment.api_contracts import AssessmentRequest, SimulationRequest
from credit.assessment.application import run_assessment, simulate_assessment
from credit.assessment.contracts import AssessmentReport
from credit.assessment.reporting import render_french
from credit.persistence import AssessmentRecord


def view(item):
    return {
        "id": item.id,
        "case_id": item.case_id,
        "case_kind": item.case_kind,
        "parent_id": item.parent_id,
        "created_at": item.created_at.replace(tzinfo=timezone.utc)
        if item.created_at.tzinfo is None
        else item.created_at,
        **item.data,
    }


def register_assessment_routes(app, db, get_case):
    def register(kind):
        path = f"/{kind}/{{case_id}}/assessments"

        @app.post(path, status_code=201, name=f"assess_{kind}")
        def analyze(
            case_id: str,
            request: AssessmentRequest,
            session: Session = Depends(db),
            idempotency_key: str | None = Header(default=None, max_length=128),
        ):
            record = get_case(session, kind, case_id)
            if (
                request.mode == "demonstration"
                and os.getenv("CREDIT_ALLOW_DEMO", "false").lower() != "true"
            ):
                raise HTTPException(403, "Mode démonstration désactivé sur ce serveur")
            try:
                from credit.assessment.application import canonical_hash

                if idempotency_key:
                    previous = session.scalars(
                        select(AssessmentRecord).where(
                            AssessmentRecord.case_id == record.id,
                            AssessmentRecord.parent_id.is_(None),
                            AssessmentRecord.data["options"]["_idempotency_key"].as_string()
                            == idempotency_key,
                        )
                    ).first()
                    if previous:
                        if previous.data["options"].get("_request_sha256") != canonical_hash(
                            request.model_dump(mode="json")
                        ) or previous.data["options"].get("_case_input_sha256") != canonical_hash(
                            record.payload
                        ):
                            raise HTTPException(
                                409, "Clé d’idempotence réutilisée avec des données différentes"
                            )
                        return view(previous)
                item = run_assessment(
                    session, record, request, session.info["actor"], idempotency_key
                )
                return view(item)
            except ValueError as exc:
                raise HTTPException(422, public_error(exc)) from None

        @app.get(path, name=f"assess_history_{kind}")
        def history(
            case_id: str,
            session: Session = Depends(db),
            limit: int = Query(100, ge=1, le=250),
            offset: int = Query(0, ge=0, le=100000),
        ):
            get_case(session, kind, case_id)
            records = session.scalars(
                select(AssessmentRecord)
                .where(AssessmentRecord.case_id == case_id, AssessmentRecord.case_kind == kind)
                .order_by(AssessmentRecord.created_at)
                .offset(offset)
                .limit(limit)
            ).all()
            return [
                {
                    "id": r.id,
                    "parent_id": r.parent_id,
                    "created_at": r.created_at,
                    "engine_version": r.data["engine_version"],
                }
                for r in records
            ]

    register("individuals")
    register("businesses")

    def find(session, id):
        item = session.get(AssessmentRecord, id)
        if item is None:
            raise HTTPException(404, "Rapport introuvable")
        record = get_case(session, item.case_kind, item.case_id)
        return item, record

    @app.get("/assessments/{assessment_id}")
    def read(assessment_id: str, session: Session = Depends(db)):
        return view(find(session, assessment_id)[0])

    @app.get("/assessments/{assessment_id}/report", response_class=PlainTextResponse)
    def report(assessment_id: str, session: Session = Depends(db)):
        item, _ = find(session, assessment_id)
        if "sections" not in item.data["result"]:
            return "Simulation incomplète : " + " ; ".join(
                item.data["result"]["missing_information"]
            )
        return render_french(AssessmentReport.model_validate(item.data["result"]))

    @app.post("/assessments/{assessment_id}/simulations", status_code=201)
    def simulate(assessment_id: str, request: SimulationRequest, session: Session = Depends(db)):
        item, record = find(session, assessment_id)
        if (
            item.data["options"]["mode"] == "demonstration"
            and os.getenv("CREDIT_ALLOW_DEMO", "false").lower() != "true"
        ):
            raise HTTPException(403, "Mode démonstration désactivé sur ce serveur")
        try:
            return view(
                simulate_assessment(
                    session, record, item, request.specification, session.info["actor"]
                )
            )
        except ValueError as exc:
            raise HTTPException(422, public_error(exc)) from None
