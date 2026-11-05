"""Routes v2 séparées : lecture des anciennes analyses inchangée."""

from copy import deepcopy
import os

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from credit.application import CONTRACTS
from credit.assessment.application import bind_reviewed_values, canonical_hash, store
from credit.assessment.routes import view
from credit.assessment.reporting import compare_financial, render_french
from credit.financial_v2 import ENGINE_VERSION
from credit.financial_v2.contracts import (
    AnalysisRequest,
    Facts,
    Policy,
    Report,
    Stress,
    PolicyException,
)
from credit.financial_v2.engines import IndividualAnalysisEngine, BusinessAnalysisEngine
from credit.financial_v2.policy import load_policy
from credit.financial_v2.scenarios import prepare
from credit.persistence import AssessmentRecord
from credit.security.access import require_staff, role
from credit.security.errors import public_error

ENGINES = {"individuals": IndividualAnalysisEngine, "businesses": BusinessAnalysisEngine}


def register_routes(app, db, get_case):
    def allowed(session, mode):
        require_staff(session.info["actor"])
        if mode == "demonstration" and os.getenv("CREDIT_ALLOW_DEMO", "false").lower() != "true":
            raise HTTPException(403, "Mode démonstration désactivé")

    def previous(session, record, key, digest, parent=None):
        if not key:
            return None
        query = select(AssessmentRecord).where(
            AssessmentRecord.case_id == record.id,
            AssessmentRecord.data["options"]["_idempotency_key"].as_string() == key,
        )
        item = session.scalars(query).first()
        if item and (
            item.data["options"].get("_request_sha256") != digest
            or item.parent_id != parent
            or (
                parent is None
                and item.data["options"].get("_case_input_sha256") != canonical_hash(record.payload)
            )
        ):
            raise HTTPException(409, "Clé réutilisée pour des données différentes")
        return item

    def register(kind):
        @app.post(
            f"/{kind}/{{case_id}}/financial-analyses", status_code=201, name=f"financial_v2_{kind}"
        )
        def analyze(
            case_id: str,
            request: AnalysisRequest,
            session: Session = Depends(db),
            idempotency_key: str | None = Header(default=None, max_length=128),
            if_match: str | None = Header(default=None),
        ):
            allowed(session, request.mode)
            record = get_case(session, kind, case_id)
            if if_match is not None and if_match.strip('"') != str(record.lock_version):
                raise HTTPException(409, "Version du dossier périmée")
            work = len(record.payload["periods"]) * (
                1
                + len(request.scenarios)
                + sum(t.steps + 65 for t in request.reverse_tests)
                + len(request.financing_candidates) * (1 + len(request.scenarios))
            )
            if work > int(os.getenv("CREDIT_FINANCIAL_V2_MAX_WORK", "50000")):
                raise HTTPException(
                    413, "Réduire le nombre de variantes, scénarios ou pas de recherche"
                )
            digest = canonical_hash(request.model_dump(mode="json"))
            item = previous(session, record, idempotency_key, digest)
            if item:
                return view(item)
            try:
                snapshot, validations = bind_reviewed_values(
                    session, record, deepcopy(record.payload), request.validated_sources
                )
                case = CONTRACTS[kind].model_validate(snapshot)
                actor = session.info["actor"]
                report = ENGINES[kind]().analyze(
                    case,
                    load_policy(request.policy_id),
                    request.mode,
                    request.facts,
                    request.scenarios,
                    request.reverse_tests,
                    request.financing_candidates,
                    actor.institution_id,
                )
                report.human_validations = validations
                options = request.model_dump(mode="json")
                options.update(
                    _idempotency_key=idempotency_key,
                    _request_sha256=digest,
                    _case_input_sha256=canonical_hash(record.payload),
                )
                return view(
                    store(
                        session,
                        record,
                        snapshot,
                        report.model_dump(mode="json"),
                        options,
                        actor,
                        validations=validations,
                    )
                )
            except ValueError as exc:
                raise HTTPException(422, public_error(exc)) from None

    for kind in ENGINES:
        register(kind)

    def find(session, id):
        require_staff(session.info["actor"])
        item = session.get(AssessmentRecord, id)
        if item is None:
            raise HTTPException(404, "Analyse introuvable")
        record = get_case(session, item.case_kind, item.case_id)
        if item.data["engine_version"] != ENGINE_VERSION:
            raise HTTPException(
                409, "Cette opération exige une analyse v2 ; historique non recalculé"
            )
        return item, record

    @app.get("/financial-analyses/{assessment_id}")
    def read(assessment_id: str, session: Session = Depends(db)):
        return view(find(session, assessment_id)[0])

    @app.get("/financial-analyses/{assessment_id}/report")
    def report(assessment_id: str, session: Session = Depends(db)):
        from fastapi.responses import PlainTextResponse

        result = find(session, assessment_id)[0].data["result"]
        return PlainTextResponse(render_french(Report.model_validate(result)))

    @app.post("/financial-analyses/{assessment_id}/simulations", status_code=201)
    def simulate(
        assessment_id: str,
        request: Stress,
        session: Session = Depends(db),
        idempotency_key: str | None = Header(default=None, max_length=128),
    ):
        parent, record = find(session, assessment_id)
        options = deepcopy(parent.data["options"])
        allowed(session, options["mode"])
        digest = canonical_hash(request.model_dump(mode="json"))
        old = previous(session, record, idempotency_key, digest, parent.id)
        if old:
            return view(old)
        try:
            case = CONTRACTS[record.kind].model_validate(parent.data["input_snapshot"])
            facts = Facts.model_validate(options["facts"])
            changed, assumptions, _ = prepare(case, request, facts)
            policy = (
                Policy.model_validate(parent.data["policy_snapshot"])
                if parent.data["policy_snapshot"]
                else None
            )
            engine = ENGINES[record.kind]()
            actor = session.info["actor"]
            result = engine.analyze(
                changed, policy, options["mode"], facts, institution_id=actor.institution_id
            )
            result.assumptions += assumptions
            result.comparisons = [
                {
                    "kind": "stress",
                    "assumptions": request.model_dump(mode="json"),
                    **compare_financial(engine.calculate(case), engine.calculate(changed)),
                }
            ]
            result.human_validations = parent.data["human_validations"]
            options.update(_idempotency_key=idempotency_key, _request_sha256=digest)
            return view(
                store(
                    session,
                    record,
                    changed.model_dump(mode="json"),
                    result.model_dump(mode="json"),
                    options,
                    actor,
                    parent.id,
                    request.model_dump(mode="json"),
                    result.human_validations,
                )
            )
        except ValueError as exc:
            raise HTTPException(422, public_error(exc)) from None

    @app.post("/financial-analyses/{assessment_id}/exceptions", status_code=201)
    def exception(assessment_id: str, request: PolicyException, session: Session = Depends(db)):
        from datetime import datetime, timezone

        parent, record = find(session, assessment_id)
        actor = session.info["actor"]
        if role(actor) not in {"institution_manager", "administrator"}:
            raise HTTPException(403, "Dérogation réservée au responsable habilité")
        result = deepcopy(parent.data["result"])
        available = {r["id"] for r in result["scoring"]["rules"]} | {
            r["id"] for r in result["deep_analysis"]["product_constraints"]
        }
        if not set(request.limit_ids) <= available:
            raise HTTPException(422, "Limites inconnues de cette analyse")
        result["deep_analysis"].setdefault("policy_exceptions", []).append(
            {
                **request.model_dump(mode="json"),
                "actor_id": actor.id,
                "institution_id": actor.institution_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "notice": "Dérogation enregistrée séparément ; calculs et qualifications non modifiés.",
            }
        )
        exception_options = {
            k: v for k, v in parent.data["options"].items() if not k.startswith("_")
        }
        return view(
            store(
                session,
                record,
                parent.data["input_snapshot"],
                result,
                exception_options,
                actor,
                parent.id,
                validations=parent.data["human_validations"],
            )
        )
