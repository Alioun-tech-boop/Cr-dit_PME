from copy import deepcopy
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pydantic import TypeAdapter
from sqlalchemy import select
from typing import Any
from credit.shared.contracts import Scenario

from credit.application import CONTRACTS
from credit.assessment.engines import (
    IndividualAnalysisEngine,
    BusinessAnalysisEngine,
    ENGINE_VERSION,
)
from credit.assessment.policy import load_policy, AssessmentPolicy
from credit.assessment.simulation import prepare_simulation
from credit.assessment.reporting import compare_financial
from credit.persistence import (
    AssessmentRecord,
    ReviewRecord,
    DocumentRun,
    SubmissionRecord,
    identifier,
)

ENGINES = {"individuals": IndividualAnalysisEngine, "businesses": BusinessAnalysisEngine}


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def bind_reviewed_values(session, record, snapshot, bindings):
    from credit.shared.contracts import Amount, SignedAmount

    typed_case = CONTRACTS[record.kind].model_validate(snapshot)
    validations = []
    targets = set()
    used_values = set()
    for binding in bindings:
        if binding.target_path in targets:
            raise ValueError("Champ visé deux fois par des revues")
        targets.add(binding.target_path)
        value_key = (binding.review_id, binding.field, binding.expected_period)
        if value_key in used_values:
            raise ValueError("Même valeur revue liée plusieurs fois : risque de double comptage")
        used_values.add(value_key)
        review = session.get(ReviewRecord, binding.review_id)
        run = session.get(DocumentRun, review.run_id) if review else None
        submission = session.get(SubmissionRecord, run.submission_id) if run else None
        if not submission or submission.case_id != record.id or submission.case_kind != record.kind:
            raise ValueError("Revue inconnue ou non accessible dans ce dossier")
        latest = session.scalars(
            select(ReviewRecord)
            .where(ReviewRecord.run_id == run.id)
            .order_by(ReviewRecord.created_at.desc(), ReviewRecord.id.desc())
        ).first()
        if (
            submission.data.get("latest_run_id") != run.id
            or run.data.get("revision") != submission.data.get("revision")
            or not latest
            or latest.id != review.id
        ):
            raise ValueError(
                "Source ou revue périmée : rattacher une validation de la version courante"
            )
        period_reviews = [
            entry
            for entry in review.data["extraction"].get("review_history", [])
            if entry["field"] == "period"
        ]
        reviewed_period = period_reviews[-1]["value"] if period_reviews else None
        if isinstance(reviewed_period, dict):
            reviewed_period = reviewed_period.get("value")
        if reviewed_period != binding.expected_period.isoformat():
            raise ValueError(
                "Période ISO du document à confirmer par une revue humaine, séparément du montant"
            )
        if submission.data["period"] != binding.expected_period.isoformat():
            raise ValueError("Période de la pièce différente de la période explicitement attendue")
        decision = review.data["decisions"].get(binding.field)
        if not isinstance(decision, dict):
            raise ValueError("Cette revue ne valide pas le champ demandé")
        value = decision["value"]
        if (
            not isinstance(value, dict)
            or value.get("currency") != "XOF"
            or value.get("unit_multiplier") != "1"
            or "amount" not in value
            or isinstance(value.get("amount"), (float, bool))
        ):
            raise ValueError("Montant, devise XOF et échelle 1 explicitement validés nécessaires")
        try:
            amount = Decimal(str(value["amount"]))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("Montant décimal invalide ; corriger la transcription") from None
        if not amount.is_finite():
            raise ValueError("Montant validé non fini")
        evidence = {
            e["id"]: e
            for e in review.data["extraction"]["evidence"]
            + review.data["extraction"]["tables"]
            + review.data["extraction"]["form_fields"]
        }
        locations = []
        for evidence_id in decision["evidence_ids"]:
            if evidence_id not in evidence:
                raise ValueError("Preuve de revue manquante")
            e = evidence[evidence_id]
            locations.append(
                {
                    "evidence_id": evidence_id,
                    "processing_page": e["page"],
                    "bbox": e["bbox"],
                    "source": e.get("source"),
                }
            )
        parts = binding.target_path.split(".")
        typed_target = typed_case
        try:
            for part in parts:
                typed_target = (
                    typed_target[int(part)]
                    if isinstance(typed_target, list)
                    else getattr(typed_target, part)
                )
        except (AttributeError, IndexError, ValueError):
            raise ValueError("Chemin cible inexistant") from None
        if not isinstance(typed_target, (Amount, SignedAmount)):
            raise ValueError(
                "La cible doit être un montant structuré, pas une métadonnée documentaire"
            )
        node = snapshot
        period = None
        for part in parts:
            if isinstance(node, dict):
                period = node.get("period", node.get("end", period))
                if part not in node:
                    raise ValueError("Chemin cible inexistant")
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                raise ValueError("Chemin cible invalide")
        if period is None:
            period = snapshot["analysis_details"]["as_of"] or snapshot["periods"][0]["period"]
        if period != binding.expected_period.isoformat():
            raise ValueError(
                "La période de la valeur financière ne correspond pas à la pièce revue"
            )
        if not isinstance(node, dict) or not {"value", "state", "evidence_ids"} <= set(node):
            raise ValueError("La cible doit être un montant structuré existant")
        evidence_id = f"review:{review.id}:{binding.field}"
        metadata = {
            "id": evidence_id,
            "source": f"submission/{submission.id}/run/{run.id}/review/{review.id}",
            "period": period,
            "currency": "XOF",
            "collected_at": submission.data["created_at"][:10],
            "status": "verified",
            "verification_method": "Transcription humaine ; authenticité non évaluée",
            "page": locations[0]["processing_page"] if locations else None,
            "bbox": locations[0]["bbox"] if locations else None,
            "submission_id": submission.id,
            "run_id": run.id,
            "review_id": review.id,
            "value_reference": binding.field,
            "source_locations": locations,
            "authenticity_status": "not_assessed",
        }
        snapshot["evidence"] = [e for e in snapshot["evidence"] if e["id"] != evidence_id] + [
            metadata
        ]
        node.update(value=str(amount), state="known", evidence_ids=[evidence_id])
        validations.append(
            {
                "review_id": review.id,
                "reviewer": review.actor_id,
                "date": review.data["created_at"],
                "field": binding.field,
                "target_path": binding.target_path,
                "reason": decision["reason"],
                "period_validation": period_reviews[-1],
                "source_locations": locations,
            }
        )
    return snapshot, validations


def store(
    session,
    record,
    snapshot,
    result,
    options,
    actor,
    parent_id=None,
    simulation=None,
    validations=None,
):
    # Conversion unique Decimal/date -> JSON, identique pour les rapports complets et simulations en attente.
    adapter = TypeAdapter(Any)
    result = adapter.dump_python(result, mode="json")
    snapshot = adapter.dump_python(snapshot, mode="json")
    options = adapter.dump_python(options, mode="json")
    # Aucun calcul ni rapport historique n'est muté en cas de modification du dossier.
    item = AssessmentRecord(
        id=identifier(),
        case_id=record.id,
        case_kind=record.kind,
        parent_id=parent_id,
        data={
            "input_snapshot": deepcopy(snapshot),
            "input_sha256": canonical_hash(snapshot),
            "result": deepcopy(result),
            "report_sha256": canonical_hash(result),
            "options": deepcopy(options),
            "policy_snapshot": deepcopy(result.get("policy_snapshot")),
            "engine_version": result.get("engine_version", ENGINE_VERSION),
            "evidence_snapshot": deepcopy(snapshot["evidence"]),
            "human_validations": deepcopy(validations or []),
            "simulation": deepcopy(simulation),
            "actor_id": actor.id,
        },
    )
    session.add(item)
    session.commit()
    return item


def run_assessment(session, record, request, actor, idempotency_key=None):
    snapshot = CONTRACTS[record.kind].model_validate(record.payload).model_dump(mode="json")
    snapshot, validations = bind_reviewed_values(
        session, record, snapshot, request.validated_sources
    )
    case = CONTRACTS[record.kind].model_validate(snapshot)
    policy = load_policy(request.policy_id, record.kind, request.mode, case.data_classification)
    result = ENGINES[record.kind]().analyze(case, policy, request.mode, request.stress_scenarios)
    result.human_validations = validations
    payload = result.model_dump(mode="json")
    options = request.model_dump(mode="json")
    if idempotency_key:
        options.update(
            _idempotency_key=idempotency_key,
            _request_sha256=canonical_hash(request.model_dump(mode="json")),
            _case_input_sha256=canonical_hash(record.payload),
        )
    return store(
        session,
        record,
        snapshot,
        payload,
        options,
        actor,
        validations=validations,
    )


def simulate_assessment(session, record, parent, spec, actor):
    if "sections" not in parent.data["result"]:
        raise ValueError(
            "Simulation incomplète : repartir de son analyse d’origine avec des projections explicites"
        )
    if parent.data["engine_version"] != ENGINE_VERSION:
        raise ValueError(
            "Version du moteur historique différente : migrer explicitement avant une comparaison"
        )
    case = CONTRACTS[record.kind].model_validate(parent.data["input_snapshot"])
    policy = (
        AssessmentPolicy.model_validate(parent.data["policy_snapshot"])
        if parent.data["policy_snapshot"]
        else None
    )
    options = deepcopy(parent.data["options"])
    active_scenario = options.get("_active_scenario")
    prepared = prepare_simulation(case, spec, policy)
    if prepared["case"] is None:
        result = {
            "status": prepared["status"],
            "terms": prepared["terms"],
            "missing_information": prepared["missing_information"],
            "policy_snapshot": parent.data["policy_snapshot"],
            "financial_comparison": None,
            "assumptions": prepared["assumptions"],
            "lender_decision": None,
        }
        return store(
            session,
            record,
            prepared["input_snapshot"],
            result,
            options,
            actor,
            parent.id,
            spec.model_dump(mode="json"),
            parent.data["human_validations"],
        )
    engine = ENGINES[record.kind]()
    inherited_scenario = Scenario.model_validate(active_scenario) if active_scenario else None
    scenario = spec.scenario if spec.kind == "stress" else inherited_scenario
    options["_active_scenario"] = scenario.model_dump(mode="json") if scenario else None
    report = engine.analyze(
        prepared["case"],
        policy,
        options["mode"],
        scenario=scenario,
        stress_scenarios=None
        if options["stress_scenarios"] is None
        else [Scenario.model_validate(s) for s in options["stress_scenarios"]],
        include_suggestions=False,
    )
    base_financial = engine.calculate(case, inherited_scenario)
    comparison = compare_financial(base_financial, engine.calculate(prepared["case"], scenario))
    report.comparisons = [{"kind": spec.kind, "terms": prepared["terms"], **comparison}]
    report.assumptions += prepared["assumptions"]
    if spec.kind == "stress":
        report.assumptions.append(
            "Les paramètres de stress remplacent le scénario actif, sans composition silencieuse."
        )
    report.human_validations = parent.data["human_validations"]
    return store(
        session,
        record,
        prepared["input_snapshot"],
        report.model_dump(mode="json"),
        options,
        actor,
        parent.id,
        spec.model_dump(mode="json"),
        parent.data["human_validations"],
    )
