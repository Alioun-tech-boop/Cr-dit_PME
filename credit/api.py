from credit.security.errors import public_error
import logging
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Header, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from credit.auth import authenticate, authorize
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from credit.application import run_analysis
from credit.businesses.contracts import BusinessCase
from credit.individuals.contracts import IndividualCase
from credit.documents.routes import register_document_routes
from credit.persistence import AnalysisRecord, CaseRecord, SecurityEvent, sessions
from credit.shared.contracts import Scenario
from credit.security.runtime import Limiter, audit, bounded_json, production_guard
from credit.security.access import enforce, client_fields, public_payload
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.orm.exc import StaleDataError
import os

logger = logging.getLogger("credit.requests")


def create_app(database_url=None):
    production_guard()
    app = FastAPI(
        title="Crédit PME — socle local",
        version="0.5.0",
        dependencies=[Depends(HTTPBearer(auto_error=False))],
        docs_url=None if os.getenv("CREDIT_ENV") == "production" else "/docs",
        redoc_url=None if os.getenv("CREDIT_ENV") == "production" else "/redoc",
        openapi_url=None if os.getenv("CREDIT_ENV") == "production" else "/openapi.json",
    )
    engine, factory = sessions(database_url) if database_url else sessions()
    app.state.engine = engine
    app.state.session_factory = factory
    limiter = Limiter()
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=os.getenv("CREDIT_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(
            ","
        ),
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "detail": [
                    {"loc": e["loc"], "type": e["type"], "msg": e["msg"]} for e in exc.errors()
                ]
            },
            status_code=422,
        )

    @app.exception_handler(StaleDataError)
    async def stale(request, exc):
        return JSONResponse({"detail": "Version périmée ; recharger le dossier"}, status_code=409)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        audit("request_failed", getattr(request.state, "actor", None), outcome="error")
        return JSONResponse(
            {"detail": "Erreur interne ; consulter la référence de requête"}, status_code=500
        )

    def db(request: Request):
        with factory() as session:
            session.info["actor"] = getattr(request.state, "actor", None)
            session.info["request"] = request
            actor = session.info["actor"]
            path = (
                request.scope.get("route").path if request.scope.get("route") else request.url.path
            )
            if (
                actor
                and actor.role in {"bank_agent", "bank_manager"}
                and not path.startswith(("/bank/", "/public/"))
                and path != "/health"
            ):
                raise HTTPException(403, "Accès réservé au portail bancaire")
            yield session

    @app.middleware("http")
    async def trace(request: Request, call_next):
        request_id = str(uuid4())
        start = time.monotonic()
        try:
            limiter.check(
                ("ip", request.client.host if request.client else "local"),
                int(os.getenv("CREDIT_RATE_REQUESTS", "600")),
            )
        except HTTPException as exc:
            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers={**(exc.headers or {}), "Cache-Control": "no-store"},
            )
        normalized_path = request.scope["path"].removeprefix(request.scope.get("root_path", ""))
        public_verification = request.method == "GET" and normalized_path.startswith(
            "/public/attestations/"
        )
        if not public_verification and normalized_path not in {
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        }:
            try:
                request.state.actor = authenticate(request)
                limiter.check(
                    ("actor", request.state.actor.id), int(os.getenv("CREDIT_RATE_ACTOR", "600"))
                )
                if request.method == "POST":
                    limiter.check(
                        ("cost", request.state.actor.id), int(os.getenv("CREDIT_RATE_JOBS", "120"))
                    )
                if (
                    os.getenv("CREDIT_ENV", "local") == "production"
                    and request.url.scheme != "https"
                ):
                    raise HTTPException(400, "HTTPS requis")
                await bounded_json(request)
                audit("authenticated", request.state.actor, request_id=request_id)
            except HTTPException as exc:
                if exc.status_code == 401:
                    try:
                        limiter.check(
                            ("auth_failure", request.client.host if request.client else "local"),
                            int(os.getenv("CREDIT_RATE_AUTH_FAILURES", "40")),
                        )
                    except HTTPException as limited:
                        exc = limited
                audit(
                    "authentication_or_request_denied",
                    getattr(request.state, "actor", None),
                    outcome=str(exc.status_code),
                    request_id=request_id,
                )
                return JSONResponse(
                    {"detail": exc.detail},
                    status_code=exc.status_code,
                    headers={
                        **(exc.headers or {}),
                        "Cache-Control": "no-store",
                        "X-Request-ID": request_id,
                    },
                )
        try:
            response = await call_next(request)
        except Exception:
            audit(
                "request_failed",
                getattr(request.state, "actor", None),
                outcome="error",
                request_id=request_id,
            )
            response = JSONResponse(
                {"detail": "Erreur interne", "request_id": request_id}, status_code=500
            )
        if response.status_code in {401, 403, 404}:
            audit(
                "access_denied",
                getattr(request.state, "actor", None),
                outcome=str(response.status_code),
                request_id=request_id,
            )
        if request.method in {"POST", "PUT", "PATCH"} and response.status_code < 400:
            audit(
                "operation",
                getattr(request.state, "actor", None),
                request_id=request_id,
                resource=getattr(request.state, "resource_id", None),
            )
        actor = getattr(request.state, "actor", None)
        if actor:
            try:
                with factory() as audit_session:
                    route = request.scope.get("route")
                    audit_session.add(
                        SecurityEvent(
                            actor_id=actor.id,
                            institution_id=actor.institution_id,
                            event=request.method + " " + getattr(route, "name", "unmatched"),
                            outcome=str(response.status_code),
                            request_id=request_id,
                            resource_id=getattr(request.state, "resource_id", None),
                        )
                    )
                    audit_session.commit()
            except Exception:
                audit("audit_storage_unavailable", actor, outcome="error", request_id=request_id)
                response = JSONResponse(
                    {"detail": "Historique de sécurité indisponible", "request_id": request_id},
                    status_code=503,
                )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
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
        query = select(CaseRecord).where(CaseRecord.id == case_id)
        if session.info["request"].method in {"POST", "PUT", "PATCH"}:
            query = query.with_for_update()
        record = session.scalar(query)
        if record is None or record.kind != kind:
            raise HTTPException(404, "Dossier introuvable")
        authorize(record, session.info["actor"], session)
        enforce(session.info["request"], session.info["actor"])
        session.info["request"].state.resource_id = record.id
        return record

    def save(session, kind, case, record=None, if_match=None, commit=True):
        client_fields(
            case,
            session.info["actor"],
            creating=record is None,
            previous=record.payload if record else None,
        )
        if record is not None:
            if if_match is None:
                raise HTTPException(428, "If-Match requis avec la version du dossier")
            if if_match.strip('"') != str(record.lock_version):
                raise HTTPException(409, "Version périmée ; recharger le dossier")
            if case.data_classification != record.payload.get("data_classification", "real"):
                raise HTTPException(409, "La classification du dossier est immuable")
        if record is None:
            from sqlalchemy import func

            count = session.scalar(
                select(func.count())
                .select_from(CaseRecord)
                .where(CaseRecord.owner_id == session.info["actor"].id)
            )
            if count >= int(os.getenv("CREDIT_MAX_CASES_PER_ACTOR", "1000")):
                raise HTTPException(429, "Quota de dossiers atteint")
            record = CaseRecord(
                kind=kind,
                owner_id=session.info["actor"].id,
                institution_id=session.info["actor"].institution_id,
            )
        payload = case.model_dump(mode="json")
        from credit.security.access import role

        if record.payload and role(session.info["actor"]) == "applicant":
            payload["record_details"]["internal_observations"] = record.payload.get(
                "record_details", {}
            ).get("internal_observations")
            payload["analysis_details"]["identity"] = record.payload.get(
                "analysis_details", {}
            ).get("identity", payload["analysis_details"]["identity"])
            payload["analysis_details"]["funding"]["verified_contribution"] = (
                record.payload.get("analysis_details", {})
                .get("funding", {})
                .get("verified_contribution")
            )
        record.payload = payload
        session.add(record)
        session.commit() if commit else session.flush()
        session.info["request"].state.resource_id = record.id
        return {
            "id": record.id,
            "kind": record.kind,
            "version": record.lock_version,
            "data": public_payload(record.payload, session.info["actor"]),
        }

    @app.post("/individuals", status_code=201)
    def create_individual(case: IndividualCase, session: Session = Depends(db)):
        return save(session, "individuals", case)

    @app.post("/businesses", status_code=201)
    def create_business(case: BusinessCase, session: Session = Depends(db)):
        return save(session, "businesses", case)

    @app.put("/individuals/{case_id}")
    def update_individual(
        case_id: str,
        case: IndividualCase,
        session: Session = Depends(db),
        if_match: str | None = Header(default=None),
    ):
        return save(
            session, "individuals", case, get_record(session, "individuals", case_id), if_match
        )

    @app.put("/businesses/{case_id}")
    def update_business(
        case_id: str,
        case: BusinessCase,
        session: Session = Depends(db),
        if_match: str | None = Header(default=None),
    ):
        return save(
            session, "businesses", case, get_record(session, "businesses", case_id), if_match
        )

    def register(kind):
        @app.get(f"/{kind}/{{case_id}}", name=f"get_{kind}")
        def get_case(case_id: str, session: Session = Depends(db)):
            record = get_record(session, kind, case_id)
            return {
                "id": record.id,
                "kind": kind,
                "version": record.lock_version,
                "data": public_payload(record.payload, session.info["actor"]),
            }

        @app.post(f"/{kind}/{{case_id}}/analyses", status_code=201, name=f"analyze_{kind}")
        def analyze(case_id: str, session: Session = Depends(db)):
            record = get_record(session, kind, case_id)
            return perform(session, record)

        @app.post(f"/{kind}/{{case_id}}/scenarios", status_code=201, name=f"scenario_{kind}")
        def scenario(case_id: str, scenario: Scenario, session: Session = Depends(db)):
            record = get_record(session, kind, case_id)
            return perform(session, record, scenario)

        @app.get(f"/{kind}/{{case_id}}/analyses", name=f"history_{kind}")
        def history(
            case_id: str,
            session: Session = Depends(db),
            limit: int = Query(100, ge=1, le=250),
            offset: int = Query(0, ge=0, le=100000),
        ):
            get_record(session, kind, case_id)
            records = session.scalars(
                select(AnalysisRecord)
                .where(AnalysisRecord.case_id == case_id)
                .order_by(AnalysisRecord.created_at)
                .offset(offset)
                .limit(limit)
            ).all()
            return [
                {"id": r.id, "created_at": r.created_at, "engine_version": r.engine_version}
                for r in records
            ]

    def perform(session, record, scenario=None):
        try:
            analysis = run_analysis(session, record, scenario)
        except ValueError as exc:
            raise HTTPException(422, public_error(exc)) from None
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

    @app.get("/security/events")
    def security_events(
        session: Session = Depends(db),
        limit: int = Query(100, ge=1, le=250),
        offset: int = Query(0, ge=0, le=100000),
    ):
        from credit.security.access import role

        actor = session.info["actor"]
        if role(actor) not in {"institution_manager", "administrator"}:
            raise HTTPException(403, "Administration institutionnelle requise")
        query = select(SecurityEvent).where(SecurityEvent.institution_id == actor.institution_id)
        return [
            {
                "id": e.id,
                "actor_id": e.actor_id,
                "institution_id": e.institution_id,
                "event": e.event,
                "outcome": e.outcome,
                "date": e.created_at,
                "request_id": e.request_id,
                "resource_id": e.resource_id,
            }
            for e in session.scalars(
                query.order_by(SecurityEvent.created_at.desc()).offset(offset).limit(limit)
            ).all()
        ]

    register_document_routes(app, db, get_record)
    from credit.documents.intake_routes import register_intake_routes

    register_intake_routes(app, db, get_record)
    from credit.assessment.routes import register_assessment_routes

    register_assessment_routes(app, db, get_record)
    from credit.financial_v2.routes import register_routes as register_financial_v2

    register_financial_v2(app, db, get_record)
    from credit.partners.routes import register_routes as register_partner_routes

    register_partner_routes(app, db, get_record)
    from credit.printing.routes import register_print_routes

    register_print_routes(app, db, get_record)
    from credit.web.routes import register_web_routes

    register_web_routes(app, db, get_record, save)
    return app


app = create_app()
