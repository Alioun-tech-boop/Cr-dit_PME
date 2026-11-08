"""Routes des niveaux décisionnel et institutionnel.

Namespace additif : aucune route existante n'est modifiée. Les analyses
décisionnelles restent internes jusqu'à publication explicite. L'endpoint
client renvoie une charge utile filtrée, sans capacité ni portefeuille.
"""

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from credit.intelligence import service
from credit.intelligence.contracts import (
    CapacityUpsert,
    ClaimAction,
    ClaimCreate,
    DecisionRequest,
    GuaranteeAction,
    GuaranteeCreate,
    LimitUpsert,
    PublishRequest,
    StressRequest,
)
from credit.intelligence.models import (
    Claim,
    DecisionAnalysis,
    Guarantee,
    InstitutionCapacity,
    InstitutionLimit,
)
from credit.security.access import require_staff, role
from credit.security.errors import public_error

STAFF = {"analyst", "institution_manager", "administrator"}
MANAGERS = {"institution_manager", "administrator"}


def register_routes(app, db, get_case):
    def staff(session):
        require_staff(session.info["actor"])
        return session.info["actor"]

    def manager(session):
        actor = session.info["actor"]
        if role(actor) not in MANAGERS:
            raise HTTPException(403, "Responsable institutionnel requis")
        if not actor.institution_id:
            raise HTTPException(403, "Compte non rattaché à une institution")
        return actor

    def institution_reader(session):
        actor = session.info["actor"]
        if role(actor) not in STAFF:
            raise HTTPException(403, "Habilitation d'analyse requise")
        if not actor.institution_id:
            raise HTTPException(403, "Compte non rattaché à une institution")
        return actor

    def decision_for(session, kind, case_id, decision_id):
        row = service.find_decision(session, decision_id)
        if row.case_id != case_id or row.case_kind != kind:
            raise HTTPException(404, "Analyse décisionnelle introuvable")
        return row

    def guarantee_for(session, guarantee_id, actor, lock=False):
        try:
            return service.find_guarantee(
                session, guarantee_id, actor.institution_id, lock=lock
            )
        except ValueError as exc:
            raise HTTPException(404, public_error(exc)) from None

    def claim_for(session, claim_id, actor, lock=False):
        try:
            return service.find_claim(session, claim_id, actor.institution_id, lock=lock)
        except ValueError as exc:
            raise HTTPException(404, public_error(exc)) from None

    def register_decision(kind):
        base = f"/{kind}/{{case_id}}/decision-analyses"

        @app.post(base, status_code=201, name=f"decision_create_{kind}")
        def create(
            case_id: str,
            request: DecisionRequest,
            session: Session = Depends(db),
        ):
            staff(session)
            case = get_case(session, kind, case_id)
            try:
                row = service.create_decision(
                    session, session.info["actor"], kind, case, request
                )
            except ValueError as exc:
                session.rollback()
                raise HTTPException(422, public_error(exc)) from None
            return service.decision_view(row)

        @app.get(base, name=f"decision_history_{kind}")
        def history(
            case_id: str,
            session: Session = Depends(db),
            limit: int = Query(100, ge=1, le=250),
            offset: int = Query(0, ge=0, le=100000),
        ):
            staff(session)
            get_case(session, kind, case_id)
            rows = session.scalars(
                select(DecisionAnalysis)
                .where(
                    DecisionAnalysis.case_id == case_id,
                    DecisionAnalysis.case_kind == kind,
                )
                .order_by(DecisionAnalysis.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return [
                {
                    "id": row.id,
                    "assessment_id": row.assessment_id,
                    "institution_id": row.institution_id,
                    "engine_version": row.engine_version,
                    "rules_version": row.rules_version,
                    "client_visible": row.client_visible,
                    "published_at": service.iso(row.published_at),
                    "created_by": row.created_by,
                    "created_at": service.iso(row.created_at),
                    "outcome": (row.data.get("decision") or {}).get("outcome"),
                    "score": (row.data.get("financial_intelligence") or {})
                    .get("score", {})
                    .get("value"),
                }
                for row in rows
            ]

        @app.get(base + "/{decision_id}", name=f"decision_read_{kind}")
        def read(case_id: str, decision_id: str, session: Session = Depends(db)):
            staff(session)
            get_case(session, kind, case_id)
            return service.decision_view(decision_for(session, kind, case_id, decision_id))

        @app.post(base + "/{decision_id}/publish", name=f"decision_publish_{kind}")
        def publish(
            case_id: str,
            decision_id: str,
            request: PublishRequest,
            session: Session = Depends(db),
        ):
            staff(session)
            get_case(session, kind, case_id)
            row = decision_for(session, kind, case_id, decision_id)
            try:
                row = service.publish_decision(session, session.info["actor"], row, request.note)
            except ValueError as exc:
                session.rollback()
                raise HTTPException(403, public_error(exc)) from None
            return service.decision_view(row)

        @app.get(
            f"/{kind}/{{case_id}}/client-analysis",
            name=f"client_analysis_{kind}",
        )
        def client_analysis(case_id: str, session: Session = Depends(db)):
            get_case(session, kind, case_id)
            row = service.latest_published(session, case_id, kind)
            if row is None:
                raise HTTPException(404, "Aucune analyse communiquée pour ce dossier")
            return service.client_payload(session, row)

    register_decision("individuals")
    register_decision("businesses")

    # ------------------------------------------------------------------
    # Garanties : cycle de vie institutionnel
    # ------------------------------------------------------------------

    @app.get("/risk/guarantees", name="risk_guarantees")
    def guarantees(
        session: Session = Depends(db),
        status: str | None = Query(None, max_length=30),
        limit: int = Query(100, ge=1, le=250),
        offset: int = Query(0, ge=0, le=100000),
    ):
        actor = institution_reader(session)
        query = select(Guarantee).where(Guarantee.institution_id == actor.institution_id)
        if status:
            query = query.where(Guarantee.status == status)
        return [
            service.guarantee_view(row)
            for row in session.scalars(
                query.order_by(Guarantee.created_at.desc()).offset(offset).limit(limit)
            )
        ]

    @app.post("/risk/guarantees", status_code=201, name="risk_guarantee_create")
    def create_guarantee(request: GuaranteeCreate, session: Session = Depends(db)):
        actor = manager(session)
        try:
            row = service.create_guarantee(session, actor, request)
        except ValueError as exc:
            session.rollback()
            raise HTTPException(422, public_error(exc)) from None
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "Référence de garantie déjà utilisée") from None
        return service.guarantee_view(row)

    @app.get("/risk/guarantees/{guarantee_id}", name="risk_guarantee_read")
    def read_guarantee(guarantee_id: str, session: Session = Depends(db)):
        actor = institution_reader(session)
        row = guarantee_for(session, guarantee_id, actor)
        return {
            **service.guarantee_view(row),
            "events": service.guarantee_events(session, row.id),
            "claims": [
                service.claim_view(claim)
                for claim in session.scalars(
                    select(Claim)
                    .where(Claim.guarantee_id == row.id)
                    .order_by(Claim.opened_at)
                )
            ],
        }

    @app.post(
        "/risk/guarantees/{guarantee_id}/action",
        name="risk_guarantee_action",
    )
    def guarantee_action(
        guarantee_id: str, request: GuaranteeAction, session: Session = Depends(db)
    ):
        actor = manager(session)
        try:
            row = service.transition_guarantee(session, actor, guarantee_id, request)
        except ValueError as exc:
            session.rollback()
            raise HTTPException(422, public_error(exc)) from None
        return service.guarantee_view(row)

    @app.get(
        "/risk/guarantees/{guarantee_id}/events", name="risk_guarantee_events"
    )
    def guarantee_events(guarantee_id: str, session: Session = Depends(db)):
        actor = institution_reader(session)
        row = guarantee_for(session, guarantee_id, actor)
        return service.guarantee_events(session, row.id)

    # ------------------------------------------------------------------
    # Sinistres : déclaration, instruction, paiement, recouvrement
    # ------------------------------------------------------------------

    @app.get("/risk/claims", name="risk_claims")
    def claims(
        session: Session = Depends(db),
        limit: int = Query(100, ge=1, le=250),
        offset: int = Query(0, ge=0, le=100000),
    ):
        actor = institution_reader(session)
        return [
            service.claim_view(row)
            for row in session.scalars(
                select(Claim)
                .where(Claim.institution_id == actor.institution_id)
                .order_by(Claim.opened_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ]

    @app.post("/risk/claims", status_code=201, name="risk_claim_create")
    def create_claim(request: ClaimCreate, session: Session = Depends(db)):
        actor = manager(session)
        try:
            row = service.create_claim(session, actor, request)
        except ValueError as exc:
            session.rollback()
            raise HTTPException(422, public_error(exc)) from None
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "Référence de sinistre déjà utilisée") from None
        return service.claim_view(row)

    @app.get("/risk/claims/{claim_id}", name="risk_claim_read")
    def read_claim(claim_id: str, session: Session = Depends(db)):
        actor = institution_reader(session)
        row = claim_for(session, claim_id, actor)
        return {
            **service.claim_view(row),
            "events": service.claim_events(session, row.id),
        }

    @app.post("/risk/claims/{claim_id}/action", name="risk_claim_action")
    def claim_action(claim_id: str, request: ClaimAction, session: Session = Depends(db)):
        actor = manager(session)
        try:
            row = service.transition_claim(session, actor, claim_id, request)
        except ValueError as exc:
            session.rollback()
            raise HTTPException(422, public_error(exc)) from None
        return service.claim_view(row)

    # ------------------------------------------------------------------
    # Capacité, limites, portefeuille et stress tests
    # ------------------------------------------------------------------

    @app.get("/risk/capacity", name="risk_capacity")
    def capacity(session: Session = Depends(db)):
        actor = institution_reader(session)
        snapshot = service.institution_capacity(session, actor.institution_id)
        config = session.get(InstitutionCapacity, actor.institution_id)
        return {
            **snapshot,
            "institution_id": actor.institution_id,
            "parameters": service.capacity_config(config),
            "rules_version": service.INSTITUTIONAL_RULES_VERSION,
        }

    @app.put("/risk/capacity", name="risk_capacity_upsert")
    def upsert_capacity(request: CapacityUpsert, session: Session = Depends(db)):
        actor = manager(session)
        row = service.upsert_capacity(session, actor, actor.institution_id, request)
        return {
            "institution_id": row.institution_id,
            "parameters": service.capacity_config(row),
            "updated_at": service.iso(row.updated_at),
            "updated_by": row.updated_by,
            "revision": row.revision,
        }

    @app.get("/risk/limits", name="risk_limits")
    def limits(session: Session = Depends(db)):
        actor = institution_reader(session)
        return [
            service.limit_view(row)
            for row in session.scalars(
                select(InstitutionLimit)
                .where(InstitutionLimit.institution_id == actor.institution_id)
                .order_by(InstitutionLimit.scope, InstitutionLimit.key)
            )
        ]

    @app.put("/risk/limits", name="risk_limit_upsert")
    def upsert_limit(request: LimitUpsert, session: Session = Depends(db)):
        actor = manager(session)
        row = service.upsert_limit(session, actor, actor.institution_id, request)
        return service.limit_view(row)

    @app.get("/risk/portfolio", name="risk_portfolio")
    def portfolio(session: Session = Depends(db)):
        actor = institution_reader(session)
        return service.portfolio(session, actor.institution_id)

    @app.post("/risk/stress", name="risk_stress")
    def stress(request: StressRequest, session: Session = Depends(db)):
        actor = institution_reader(session)
        return service.stress(session, actor.institution_id, request.scenarios)
