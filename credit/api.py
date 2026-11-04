import logging
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from credit.auth import authenticate, authorize
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from credit.application import run_analysis
from credit.businesses.contracts import BusinessCase
from credit.individuals.contracts import IndividualCase
from credit.documents.routes import register_document_routes
from credit.persistence import AnalysisRecord, CaseRecord, sessions
from credit.shared.contracts import Scenario

logger = logging.getLogger("credit.requests")


def create_app(database_url=None):
    app = FastAPI(
        title="Crédit PME — socle local",
        version="0.2.0",
        dependencies=[Depends(HTTPBearer(auto_error=False))],
    )
    engine, factory = sessions(database_url) if database_url else sessions()
    app.state.engine = engine

    def db(request: Request):
        with factory() as session:
            session.info["actor"] = getattr(request.state, "actor", None)
            yield session

    @app.middleware("http")
    async def trace(request: Request, call_next):
        request_id = str(uuid4())
        start = time.monotonic()
        if request.url.path not in {"/health", "/docs", "/openapi.json", "/redoc"}:
            try:
                request.state.actor = authenticate(request)
            except HTTPException as exc:
                return JSONResponse(
                    {"detail": exc.detail},
                    status_code=exc.status_code,
                    headers={
                        **(exc.headers or {}),
                        "Cache-Control": "no-store",
                        "X-Request-ID": request_id,
                    },
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request_id
        # Aucun corps, paramètre, nom, identifiant métier ou URL brute dans les journaux.
        route = request.scope.get("route")
        logger.info(
            "request=%s method=%s route=%s status=%s duration_ms=%.1f",
            request_id,
            request.method,
            getattr(route, "path", "unmatched"),
            response.status_code,
            (time.monotonic() - start) * 1000,
        )
        return response

    @app.get("/health")
    def health(session: Session = Depends(db)):
        try:
            session.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(503, "Base indisponible") from None
        return {"status": "ok"}

    def get_record(session, kind, case_id):
        record = session.get(CaseRecord, case_id)
        if record is None or record.kind != kind:
            raise HTTPException(404, "Dossier introuvable")
        authorize(record, session.info["actor"])
        return record

    def save(session, kind, case, record=None):
        if record is None:
            record = CaseRecord(kind=kind, owner_id=session.info["actor"].id)
        record.payload = case.model_dump(mode="json")
        session.add(record)
        session.commit()
        return {"id": record.id, "kind": record.kind, "data": record.payload}

    @app.post("/individuals", status_code=201)
    def create_individual(case: IndividualCase, session: Session = Depends(db)):
        return save(session, "individuals", case)

    @app.post("/businesses", status_code=201)
    def create_business(case: BusinessCase, session: Session = Depends(db)):
        return save(session, "businesses", case)

    @app.put("/individuals/{case_id}")
    def update_individual(case_id: str, case: IndividualCase, session: Session = Depends(db)):
        return save(session, "individuals", case, get_record(session, "individuals", case_id))

    @app.put("/businesses/{case_id}")
    def update_business(case_id: str, case: BusinessCase, session: Session = Depends(db)):
        return save(session, "businesses", case, get_record(session, "businesses", case_id))

    def register(kind):
        @app.get(f"/{kind}/{{case_id}}", name=f"get_{kind}")
        def get_case(case_id: str, session: Session = Depends(db)):
            record = get_record(session, kind, case_id)
            return {"id": record.id, "kind": kind, "data": record.payload}

        @app.post(f"/{kind}/{{case_id}}/analyses", status_code=201, name=f"analyze_{kind}")
        def analyze(case_id: str, session: Session = Depends(db)):
            record = get_record(session, kind, case_id)
            return perform(session, record)

        @app.post(f"/{kind}/{{case_id}}/scenarios", status_code=201, name=f"scenario_{kind}")
        def scenario(case_id: str, scenario: Scenario, session: Session = Depends(db)):
            record = get_record(session, kind, case_id)
            return perform(session, record, scenario)

        @app.get(f"/{kind}/{{case_id}}/analyses", name=f"history_{kind}")
        def history(case_id: str, session: Session = Depends(db)):
            get_record(session, kind, case_id)
            records = session.scalars(
                select(AnalysisRecord)
                .where(AnalysisRecord.case_id == case_id)
                .order_by(AnalysisRecord.created_at)
            ).all()
            return [
                {"id": r.id, "created_at": r.created_at, "engine_version": r.engine_version}
                for r in records
            ]

    def perform(session, record, scenario=None):
        try:
            analysis = run_analysis(session, record, scenario)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"id": analysis.id, "result": analysis.result}

    register("individuals")
    register("businesses")

    @app.get("/analyses/{analysis_id}")
    def get_analysis(analysis_id: str, session: Session = Depends(db)):
        record = session.get(AnalysisRecord, analysis_id)
        if record is None:
            raise HTTPException(404, "Analyse introuvable")
        get_record(session, record.kind, record.case_id)
        return {
            "id": record.id,
            "case_id": record.case_id,
            "kind": record.kind,
            "input_snapshot": record.input_snapshot,
            "result": record.result,
            "scenario": record.scenario,
            "configuration": record.configuration,
            "engine_version": record.engine_version,
            "evidence_snapshot": record.evidence_snapshot,
            "created_at": record.created_at,
        }

    register_document_routes(app, db, get_record)
    from credit.documents.intake_routes import register_intake_routes

    register_intake_routes(app, db, get_record)
    return app


app = create_app()
