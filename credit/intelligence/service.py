"""Orchestration et persistance des niveaux 1 à 3.

Les analyses décisionnelles sont stockées, immuables et reproductibles. Les
garanties, sinistres et configurations institutionnelles sont journalisés.
"""

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from credit.application import CONTRACTS
from credit.assessment.application import canonical_hash
from credit.financial_v2.contracts import Facts, Policy, Stress
from credit.financial_v2.engines import BusinessAnalysisEngine, IndividualAnalysisEngine
from credit.financial_v2.scenarios import prepare
from credit.persistence import AssessmentRecord, CaseRecord
from credit.intelligence import (
    DECISION_ENGINE_VERSION,
    DECISION_RULES_VERSION,
    FINANCIAL_RULES_VERSION,
    INSTITUTIONAL_RULES_VERSION,
)
from credit.intelligence import decision as decision_rules
from credit.intelligence import financial as financial_rules
from credit.intelligence import institutional as institutional_rules
from credit.intelligence.models import (
    Claim,
    ClaimEvent,
    DecisionAnalysis,
    Guarantee,
    GuaranteeEvent,
    InstitutionCapacity,
    InstitutionLimit,
)

ENGINES = {"individuals": IndividualAnalysisEngine, "businesses": BusinessAnalysisEngine}
ACTIVE_STATUSES = {"approved", "transmitted", "active", "mobilized"}


def dec(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    # Les colonnes JSON n'acceptent pas Decimal : convertir en chaîne exacte.
    if isinstance(value, Decimal):
        return str(value)
    return value


def assessment_record(session, assessment_id):
    item = session.get(AssessmentRecord, assessment_id)
    if item is None:
        raise ValueError("Analyse source introuvable")
    if item.data.get("engine_version") != "financial_analysis_v2":
        raise ValueError("Une analyse financière v2 est requise pour ce calcul décisionnel")
    return item


def _case_payload(item):
    return deepcopy(item.data.get("input_snapshot") or {})


def _report(item):
    return deepcopy(item.data.get("result") or {})


def _guarantee_dict(row):
    return {
        "id": row.id,
        "case_id": row.case_id,
        "case_kind": row.case_kind,
        "reference": row.reference,
        "status": row.status,
        "requested_amount": str(row.requested_amount) if row.requested_amount is not None else None,
        "approved_amount": str(row.approved_amount) if row.approved_amount is not None else None,
        "partner_id": row.partner_id,
        "sector": row.sector,
        "region": row.region,
        "borrower_type": row.borrower_type,
        "risk_level": row.risk_level,
        "recommendation": row.recommendation,
        "effective_from": iso(row.effective_from),
        "effective_to": iso(row.effective_to),
    }


def _claim_dict(row):
    return {
        "id": row.id,
        "guarantee_id": row.guarantee_id,
        "reference": row.reference,
        "status": row.status,
        "declared_amount": str(row.declared_amount) if row.declared_amount is not None else None,
        "received_amount": str(row.received_amount) if row.received_amount is not None else None,
        "approved_amount": str(row.approved_amount) if row.approved_amount is not None else None,
        "paid_amount": str(row.paid_amount) if row.paid_amount is not None else None,
        "recovered_amount": str(row.recovered_amount) if row.recovered_amount is not None else None,
        "currency": row.currency,
        "reason": row.reason,
        "opened_at": iso(row.opened_at),
        "closed_at": iso(row.closed_at),
    }


def capacity_config(row):
    if row is None:
        return None
    return {
        "as_of": iso(row.as_of),
        "own_funds": str(row.own_funds) if row.own_funds is not None else None,
        "mobilizable_resources": str(row.mobilizable_resources)
        if row.mobilizable_resources is not None
        else None,
        "liquidities": str(row.liquidities) if row.liquidities is not None else None,
        "provisions": str(row.provisions) if row.provisions is not None else None,
        "safety_reserve": str(row.safety_reserve) if row.safety_reserve is not None else None,
        "max_global_exposure": str(row.max_global_exposure)
        if row.max_global_exposure is not None
        else None,
        "coverage_limit": str(row.coverage_limit) if row.coverage_limit is not None else None,
        "max_sector_share": str(row.max_sector_share)
        if row.max_sector_share is not None
        else None,
        "max_bank_share": str(row.max_bank_share) if row.max_bank_share is not None else None,
        "max_borrower_share": str(row.max_borrower_share)
        if row.max_borrower_share is not None
        else None,
        "source_reference": row.source_reference,
    }


def institution_capacity(session, institution_id):
    """Capacité complète, réservée aux routes institutionnelles internes."""
    if not institution_id:
        return institutional_rules.capacity_summary(None, [])
    config = capacity_config(session.get(InstitutionCapacity, institution_id))
    guarantees = [
        _guarantee_dict(g)
        for g in session.scalars(
            select(Guarantee).where(Guarantee.institution_id == institution_id)
        )
    ]
    claims = [
        _claim_dict(c)
        for c in session.scalars(
            select(Claim).where(Claim.institution_id == institution_id)
        )
    ]
    return institutional_rules.capacity_summary(config, guarantees, claims)


def institution_snapshot(session, institution_id):
    if not institution_id:
        return {
            "status": "not_configured",
            "remaining_capacity": None,
            "configured_cap": None,
            "active_commitments": None,
            "utilization": None,
            "alerts": ["Institution non identifiée : capacité non calculable."],
        }
    summary = institution_capacity(session, institution_id)
    return {
        "status": summary["status"],
        "remaining_capacity": summary["remaining_capacity"],
        "configured_cap": summary["configured_cap"],
        "active_commitments": summary["active_commitments"],
        "utilization": summary["utilization"],
        "alerts": summary["alerts"],
    }


def _min_from_periods(periods, *keys):
    values = []
    for row in periods:
        value = None
        for key in keys:
            if row.get(key) is not None:
                value = dec(row.get(key))
                break
        values.append(value)
    known = [v for v in values if v is not None]
    return min(known) if known else None


def _scenario_reading(item):
    financial = item.get("financial_calculations") or {}
    periods = financial.get("periods") or []
    return {
        "min_margin": financial_rules.text(_min_from_periods(periods, "margin_after_credit", "margin_after_debt")),
        "min_reserve": financial_rules.text(_min_from_periods(periods, "projected_reserve", "closing_cash")),
    }


def _severity(item):
    scenario = item.get("scenario") or item.get("assumptions") or {}
    return (
        (dec(scenario.get("revenue_drop")) or Decimal(0))
        + (dec(scenario.get("expense_increase")) or Decimal(0))
        + (dec(scenario.get("variable_cost_increase")) or Decimal(0))
    )


def _normalise_scenarios(readings):
    available = [r for r in readings if r.get("status") == "available"]
    if len(available) >= 2:
        # Le scénario le plus sévère est toujours identifié comme tel.
        available.sort(key=_severity, reverse=True)
        for index, item in enumerate(available):
            item["id"] = "severe" if index == 0 else "adverse"
    return readings


def standard_scenarios(item, run):
    report = _report(item)
    stored = [
        s
        for s in ((report.get("deep_analysis") or {}).get("scenarios") or [])
        if s.get("status") == "available"
    ]
    stored.sort(key=_severity, reverse=True)
    readings = []
    for index, entry in enumerate(stored[:2]):
        scenario = entry.get("scenario") or {}
        readings.append(
            {
                # Les scénarios stockés sont triés du plus sévère au moins sévère.
                "id": "severe" if index == 0 else "adverse",
                "status": "available",
                "source": "stored",
                "assumptions": {
                    "name": scenario.get("name"),
                    "revenue_drop": scenario.get("revenue_drop"),
                    "expense_increase": scenario.get("expense_increase"),
                    "rationale": scenario.get("rationale"),
                },
                "reason": None,
                **_scenario_reading(entry),
            }
        )
    if len(readings) >= 2:
        return _normalise_scenarios(readings)
    if not run:
        return readings
    case_payload = _case_payload(item)
    facts = Facts.model_validate((item.data.get("options") or {}).get("facts") or {})
    try:
        case = CONTRACTS[item.case_kind].model_validate(case_payload)
    except ValueError as exc:
        return readings + [
            {
                "id": "adverse" if not readings else "severe",
                "status": "not_available",
                "source": "not_computed",
                "reason": "Dossier source non rechargeable : " + str(exc),
            }
        ]
    engine = ENGINES[item.case_kind]()
    definitions = [
        (
            "adverse",
            "Scénario conventionnel défavorable",
            Decimal("0.10"),
            Decimal("0.05"),
        ),
        (
            "severe",
            "Scénario conventionnel fortement défavorable",
            Decimal("0.20"),
            Decimal("0.15"),
        ),
    ]
    existing = {r["id"] for r in readings}
    for id, name, revenue_drop, expense_increase in definitions:
        if id in existing:
            continue
        stress = Stress(
            id=id,
            name=name,
            revenue_drop=revenue_drop,
            expense_increase=expense_increase,
            rationale=(
                "Hypothèse conventionnelle Crédit PME : baisse des revenus/encaissements de "
                + str(revenue_drop * 100)
                + " % et hausse des charges de "
                + str(expense_increase * 100)
                + " %. Aucune prévision, aucune probabilité."
            ),
        )
        try:
            changed, notes, _ = prepare(case, stress, facts)
            result = engine.calculate(changed).model_dump(mode="json")
        except ValueError as exc:
            readings.append(
                {
                    "id": id,
                    "status": "not_available",
                    "source": "not_computed",
                    "reason": str(exc),
                }
            )
            continue
        readings.append(
            {
                "id": id,
                "status": "available",
                "source": "computed_standard",
                "assumptions": stress.model_dump(mode="json"),
                "reason": None,
                **_scenario_reading({"financial_calculations": result}),
            }
        )
    return _normalise_scenarios(readings)


def decision_view(row):
    return {
        "id": row.id,
        "case_id": row.case_id,
        "case_kind": row.case_kind,
        "assessment_id": row.assessment_id,
        "institution_id": row.institution_id,
        "engine_version": row.engine_version,
        "rules_version": row.rules_version,
        "input_sha256": row.input_sha256,
        "report_sha256": row.report_sha256,
        "client_visible": row.client_visible,
        "published_at": iso(row.published_at),
        "published_by": row.published_by,
        "published_note": row.published_note,
        "created_by": row.created_by,
        "created_at": iso(row.created_at),
        "data": deepcopy(row.data),
    }


def create_decision(session, actor, kind, case, request):
    item = assessment_record(session, request.assessment_id)
    if item.case_id != case.id or item.case_kind != kind:
        raise ValueError("L’analyse source n’appartient pas à ce dossier")
    case_payload = _case_payload(item)
    report = _report(item)
    intelligence = financial_rules.build_financial_intelligence(report, case_payload)
    reliability = decision_rules.build_reliability(report, case_payload, intelligence)
    scenario_results = standard_scenarios(item, request.run_standard_scenarios)
    scenarios = decision_rules.build_scenarios(report, scenario_results)
    institution = institution_snapshot(session, actor.institution_id)
    affordability = decision_rules.build_affordability(
        report, intelligence, case_payload, request, institution
    )
    decision = decision_rules.build_decision(
        report,
        case_payload,
        intelligence,
        reliability,
        scenarios,
        affordability,
        request,
        institution,
    )
    payload = {
        "engine_version": DECISION_ENGINE_VERSION,
        "rules_version": DECISION_RULES_VERSION,
        "assessment": {
            "id": item.id,
            "case_id": item.case_id,
            "case_kind": item.case_kind,
            "created_at": iso(item.created_at),
            "engine_version": item.data.get("engine_version"),
            "report_sha256": item.data.get("report_sha256"),
            "policy": (item.data.get("versions") or {}).get("policy"),
        },
        "financial_intelligence": intelligence,
        "reliability": reliability,
        "affordability": affordability,
        "scenarios": scenarios,
        "decision": decision,
        "versions": {
            "engine": DECISION_ENGINE_VERSION,
            "financial_rules": FINANCIAL_RULES_VERSION,
            "decision_rules": DECISION_RULES_VERSION,
            "source_engine": item.data.get("engine_version"),
            "source_rules": (item.data.get("versions") or {}).get("rules"),
        },
        "human_notes": request.human_notes,
        "notice": (
            "Analyse décisionnelle déterministe. Recommandation soumise à validation humaine. "
            "Aucune garantie n’est approuvée par ce calcul."
        ),
    }
    digest = canonical_hash(
        {
            "assessment_id": item.id,
            "request": request.model_dump(mode="json"),
            "result": report,
            "input": case_payload,
        }
    )
    existing = session.scalar(
        select(DecisionAnalysis).where(
            DecisionAnalysis.assessment_id == item.id,
            DecisionAnalysis.input_sha256 == digest,
            DecisionAnalysis.rules_version == DECISION_RULES_VERSION,
        )
    )
    if existing is not None:
        return existing
    row = DecisionAnalysis(
        case_id=item.case_id,
        case_kind=item.case_kind,
        assessment_id=item.id,
        institution_id=actor.institution_id,
        engine_version=DECISION_ENGINE_VERSION,
        rules_version=DECISION_RULES_VERSION,
        input_sha256=digest,
        report_sha256=canonical_hash(payload),
        data=payload,
        created_by=actor.id,
    )
    session.add(row)
    session.commit()
    return row


def publish_decision(session, actor, row, note):
    if row.institution_id and actor.institution_id and row.institution_id != actor.institution_id:
        raise ValueError("Analyse d’une autre institution")
    if not row.client_visible:
        row.client_visible = True
        row.published_at = datetime.now(timezone.utc)
        row.published_by = actor.id
        row.published_note = note
        session.commit()
    return row


def find_decision(session, decision_id, institution_id=None):
    row = session.get(DecisionAnalysis, decision_id)
    if row is None:
        raise ValueError("Analyse décisionnelle introuvable")
    if institution_id is not None and row.institution_id not in {None, institution_id}:
        raise ValueError("Analyse d’une autre institution")
    return row


def latest_published(session, case_id, case_kind):
    return session.scalar(
        select(DecisionAnalysis)
        .where(
            DecisionAnalysis.case_id == case_id,
            DecisionAnalysis.case_kind == case_kind,
            DecisionAnalysis.client_visible.is_(True),
        )
        .order_by(DecisionAnalysis.published_at.desc(), DecisionAnalysis.created_at.desc())
    )


def client_payload(session, row):
    data = deepcopy(row.data)
    intelligence = data["financial_intelligence"]
    decision = data["decision"]
    guarantee = session.scalar(
        select(Guarantee)
        .where(Guarantee.decision_analysis_id == row.id)
        .order_by(Guarantee.created_at.desc())
    )
    guarantee_view = None
    if guarantee is not None:
        guarantee_view = {
            "id": guarantee.id,
            "reference": guarantee.reference,
            "status": guarantee.status,
            "status_label": {
                "proposed": "Proposée",
                "pending_validation": "En attente de validation",
                "approved": "Approuvée",
                "transmitted": "Transmise à la banque",
                "active": "Active",
                "expired": "Expirée",
                "mobilized": "Mobilisée",
                "closed": "Clôturée",
                "rejected": "Refusée",
            }.get(guarantee.status, guarantee.status),
            "approved_amount": str(guarantee.approved_amount) if guarantee.approved_amount is not None else None,
            "requested_amount": str(guarantee.requested_amount) if guarantee.requested_amount is not None else None,
            "conditions": guarantee.conditions,
            "effective_from": iso(guarantee.effective_from),
            "effective_to": iso(guarantee.effective_to),
            "official_document": None,
            "official_document_notice": (
                "Aucun document de garantie signé n’est disponible. Une recommandation favorable "
                "ne constitue pas un certificat de garantie."
            ),
        }
    reliability = data["reliability"]
    score = intelligence["score"]
    state = "analyse_terminee"
    if reliability["suspended"]:
        state = "analyse_suspendue"
    elif score["status"] != "available":
        state = "informations_manquantes"
    elif decision["outcome"] == "favorable":
        state = "favorable"
    elif decision["outcome"] == "favorable_sous_conditions":
        state = "favorable_sous_conditions"
    elif decision["outcome"] == "defavorable":
        state = "defavorable"
    documents = []
    try:
        from credit.persistence import PrintEdition
        from credit.printing.catalog import ANALYSIS_TEMPLATES, CATALOG

        for edition in session.scalars(
            select(PrintEdition)
            .where(
                PrintEdition.case_id == row.case_id,
                PrintEdition.case_kind == row.case_kind,
                PrintEdition.audience == "applicant",
                PrintEdition.status == "completed",
            )
            .order_by(PrintEdition.created_at.desc())
        ):
            if edition.template_id not in ANALYSIS_TEMPLATES:
                continue
            documents.append(
                {
                    "id": edition.id,
                    "title": CATALOG.get(row.case_kind, {}).get(
                        edition.template_id, edition.template_id
                    ),
                    "template_id": edition.template_id,
                    "created_at": iso(edition.created_at),
                    "download_url": "/print-editions/" + edition.id + "/pdf",
                }
            )
    except Exception:
        documents = []
    return {
        "schema_version": "credit-pme.client-analysis.v1",
        "dossier": {
            "case_id": row.case_id,
            "case_kind": row.case_kind,
            "borrower_type": "Entreprise" if row.case_kind == "businesses" else "Particulier",
            "assessment_id": row.assessment_id,
            "decision_id": row.id,
            "processed_at": iso(data["assessment"].get("created_at")),
            "published_at": iso(row.published_at),
            "requested_amount": data["affordability"]["requested"]["principal"],
            "duration_months": data["affordability"]["requested"]["duration_months"],
            "currency": "XOF",
        },
        "state": state,
        "state_label": {
            "analyse_terminee": "Analyse terminée",
            "analyse_suspendue": "Analyse suspendue",
            "informations_manquantes": "Informations manquantes",
            "favorable": "Analyse favorable",
            "favorable_sous_conditions": "Analyse favorable sous conditions",
            "defavorable": "Analyse défavorable",
        }[state],
        "summary": {
            "score": score["value"],
            "score_label": score["label"],
            "score_status": score["status"],
            "risk_level": score["risk_level"],
            "recommendation": decision["label"],
            "recommendation_code": decision["outcome"],
            "monthly_capacity": intelligence["capacity"]["monthly_before_new_debt"],
            "minimum_margin": intelligence["capacity"]["minimum_margin_after_debt"],
            "guarantee_status": guarantee_view["status"] if guarantee_view else "not_created",
            "guarantee_status_label": guarantee_view["status_label"] if guarantee_view else "Non créée",
        },
        "score": {
            "value": score["value"],
            "label": score["label"],
            "band": score["band"],
            "risk_level": score["risk_level"],
            "status": score["status"],
            "coverage": score["coverage"],
            "formula": score["formula"],
            "criteria": intelligence["criteria"],
            "favorable": intelligence["favorable"],
            "unfavorable": intelligence["unfavorable"],
            "missing_criteria": intelligence["missing_criteria"],
            "notice": score["notice"],
        },
        "indicators": intelligence["groups"],
        "trends": intelligence["trends"],
        "risks": intelligence["risks"],
        "default_risk": intelligence["default_risk"],
        "scenarios": data["scenarios"],
        "reliability": {
            "level": reliability["level"],
            "label": reliability["label"],
            "components": reliability["components"],
            "human_verifications": reliability["human_verifications"],
            "notice": reliability["notice"],
        },
        "decision": {
            "outcome": decision["outcome"],
            "label": decision["label"],
            "justifications": decision["justifications"],
            "conditions": decision["conditions"],
            "reserves": decision["reserves"],
            "next_steps": decision["next_steps"],
            "recommended_guarantee_amount": decision["guarantee"]["recommended_amount"],
            "requested_guarantee_amount": decision["guarantee"]["requested_amount"],
            "human_approval_required": decision["guarantee"]["human_approval_required"],
            "human_approval_status": decision["guarantee"]["human_approval_status"],
            "notice": decision["guarantee"]["notice"],
        },
        "guarantee": guarantee_view,
        "documents": documents,
        "traceability": {
            "decision_id": row.id,
            "assessment_id": row.assessment_id,
            "engine_version": row.engine_version,
            "rules_version": row.rules_version,
            "financial_rules_version": FINANCIAL_RULES_VERSION,
            "decision_rules_version": DECISION_RULES_VERSION,
            "institutional_rules_version": INSTITUTIONAL_RULES_VERSION,
            "input_sha256": row.input_sha256,
            "report_sha256": row.report_sha256,
            "created_at": iso(row.created_at),
            "notice": "Analyse figée avec les données et règles de son exécution ; jamais recalculée en place.",
        },
        "confidentiality": {
            "institutional_capacity_exposed": False,
            "portfolio_exposed": False,
            "notice": "Les ressources, réserves et engagements globaux de Crédit PME ne sont pas communiqués.",
        },
    }


# ---------------------------------------------------------------------------
# Garanties
# ---------------------------------------------------------------------------

TRANSITIONS = {
    "submit": ({"proposed"}, "pending_validation"),
    "approve": ({"proposed", "pending_validation"}, "approved"),
    "reject": ({"proposed", "pending_validation"}, "rejected"),
    "transmit": ({"approved"}, "transmitted"),
    "activate": ({"transmitted"}, "active"),
    "expire": ({"active", "transmitted"}, "expired"),
    "mobilize": ({"active", "expired"}, "mobilized"),
    "close": ({"active", "expired", "mobilized", "rejected", "closed"}, "closed"),
}


def guarantee_view(row):
    return {
        **_guarantee_dict(row),
        "assessment_id": row.assessment_id,
        "decision_analysis_id": row.decision_analysis_id,
        "institution_id": row.institution_id,
        "conditions": row.conditions,
        "currency": row.currency,
        "data": deepcopy(row.data),
        "created_by": row.created_by,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
        "revision": row.revision,
    }


def create_guarantee(session, actor, request):
    decision = find_decision(session, request.decision_analysis_id, actor.institution_id)
    case = session.get(CaseRecord, decision.case_id)
    if case is None:
        raise ValueError("Dossier introuvable")
    decision_data = decision.data["decision"]
    requested = dec(request.approved_amount) or dec(
        decision_data["guarantee"]["requested_amount"]
    )
    if requested is None:
        raise ValueError("Montant garanti indisponible : le préciser explicitement")
    if request.partner_id is not None:
        from credit.partners.models import Partner

        partner = session.get(Partner, request.partner_id)
        if partner is None:
            raise ValueError("Banque partenaire inconnue")
    row = Guarantee(
        case_id=decision.case_id,
        case_kind=decision.case_kind,
        assessment_id=decision.assessment_id,
        decision_analysis_id=decision.id,
        institution_id=actor.institution_id or "unassigned",
        partner_id=request.partner_id,
        reference=request.reference or ("GAR-" + decision.id[:8].upper()),
        borrower_name=str((case.payload or {}).get("name") or "Dossier sans nom")[:200],
        borrower_type=decision.case_kind,
        sector=request.sector,
        region=request.region,
        requested_amount=requested,
        currency="XOF",
        status="proposed",
        risk_level=request.risk_level or decision_data["risk_level"],
        recommendation=decision_data["outcome"],
        conditions=request.conditions or list(decision_data.get("conditions") or []),
        effective_from=request.effective_from,
        effective_to=request.effective_to,
        data={
            "recommendation": decision_data,
            "note": request.note,
            "created_from_rules": DECISION_RULES_VERSION,
        },
        created_by=actor.id,
    )
    session.add(row)
    session.flush()
    session.add(
        GuaranteeEvent(
            guarantee_id=row.id,
            action="proposed",
            actor_id=actor.id,
            from_status=None,
            to_status="proposed",
            data={"recommendation": decision_data["outcome"]},
        )
    )
    session.commit()
    return row


def find_guarantee(session, guarantee_id, institution_id=None, lock=False):
    stmt = select(Guarantee).where(Guarantee.id == guarantee_id)
    if lock:
        stmt = stmt.with_for_update()
    row = session.scalar(stmt)
    if row is None:
        raise ValueError("Garantie introuvable")
    if institution_id is not None and row.institution_id != institution_id:
        raise ValueError("Garantie d’une autre institution")
    return row


def transition_guarantee(session, actor, guarantee_id, request):
    row = find_guarantee(session, guarantee_id, actor.institution_id, lock=True)
    allowed, target = TRANSITIONS[request.action]
    if row.status not in allowed:
        raise ValueError("Transition impossible depuis le statut " + row.status)
    previous = row.status
    if request.action == "approve":
        amount = dec(request.approved_amount)
        if amount is None or amount <= 0:
            raise ValueError("Montant approuvé strictement positif requis")
        if amount > row.requested_amount:
            raise ValueError("Le montant approuvé dépasse le montant demandé")
        snapshot = institution_snapshot(session, row.institution_id)
        remaining = dec(snapshot.get("remaining_capacity"))
        if snapshot.get("status") == "configured" and remaining is not None and amount > remaining:
            raise ValueError(
                "Plafond institutionnel insuffisant : capacité restante " + str(remaining) + " XOF"
            )
        row.approved_amount = amount
    row.status = target
    if request.effective_from is not None:
        row.effective_from = request.effective_from
    if request.effective_to is not None:
        row.effective_to = request.effective_to
    data = deepcopy(row.data or {})
    data.setdefault("history", []).append(
        {
            "action": request.action,
            "reason": request.reason,
            "actor_id": actor.id,
            "from": previous,
            "to": target,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    row.data = data
    session.add(
        GuaranteeEvent(
            guarantee_id=row.id,
            action=request.action,
            actor_id=actor.id,
            from_status=previous,
            to_status=target,
            data={"reason": request.reason, "approved_amount": iso(row.approved_amount)},
        )
    )
    session.commit()
    return row


def guarantee_events(session, guarantee_id):
    from credit.intelligence.models import GuaranteeEvent as Event

    return [
        {
            "id": e.id,
            "action": e.action,
            "actor_id": e.actor_id,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "data": e.data,
            "created_at": iso(e.created_at),
        }
        for e in session.scalars(
            select(Event)
            .where(Event.guarantee_id == guarantee_id)
            .order_by(Event.created_at)
        )
    ]


# ---------------------------------------------------------------------------
# Sinistres
# ---------------------------------------------------------------------------

CLAIM_TRANSITIONS = {
    "receive_documents": ({"declared"}, "documents_received"),
    "verify_conditions": ({"documents_received"}, "conditions_verified"),
    "assess_amount": ({"conditions_verified"}, "amount_assessed"),
    "approve": ({"amount_assessed"}, "approved"),
    "pay": ({"approved"}, "paid"),
    "record_recovery": ({"paid"}, "recovery"),
    "close": ({"paid", "recovery"}, "closed"),
    "reject": (
        {"declared", "documents_received", "conditions_verified", "amount_assessed"},
        "rejected",
    ),
}


def create_claim(session, actor, request):
    guarantee = find_guarantee(session, request.guarantee_id, actor.institution_id)
    if guarantee.status not in {"active", "mobilized"}:
        raise ValueError("Un sinistre ne peut être déclaré que sur une garantie active ou mobilisée")
    status = "documents_received" if request.documents_received else "declared"
    row = Claim(
        guarantee_id=guarantee.id,
        institution_id=guarantee.institution_id,
        reference=request.reference,
        status=status,
        declared_amount=request.declared_amount,
        currency=guarantee.currency,
        reason=request.reason,
    )
    session.add(row)
    session.flush()
    session.add(
        ClaimEvent(
            claim_id=row.id,
            action="declared",
            actor_id=actor.id,
            from_status=None,
            to_status="declared",
            amount=request.declared_amount,
            data={"reason": request.reason},
        )
    )
    if status == "documents_received":
        session.add(
            ClaimEvent(
                claim_id=row.id,
                action="receive_documents",
                actor_id=actor.id,
                from_status="declared",
                to_status="documents_received",
                data={"reason": "Justificatifs bancaires déclarés reçus à la création."},
            )
        )
    session.commit()
    return row


def find_claim(session, claim_id, institution_id=None, lock=False):
    stmt = select(Claim).where(Claim.id == claim_id)
    if lock:
        stmt = stmt.with_for_update()
    row = session.scalar(stmt)
    if row is None:
        raise ValueError("Sinistre introuvable")
    if institution_id is not None and row.institution_id != institution_id:
        raise ValueError("Sinistre d’une autre institution")
    return row


def transition_claim(session, actor, claim_id, request):
    row = find_claim(session, claim_id, actor.institution_id, lock=True)
    allowed, target = CLAIM_TRANSITIONS[request.action]
    if row.status not in allowed:
        raise ValueError("Transition de sinistre impossible depuis le statut " + row.status)
    previous = row.status
    amount = dec(request.amount)
    if request.action in {"assess_amount", "approve"}:
        if amount is None or amount <= 0:
            raise ValueError("Montant évalué strictement positif requis")
        if amount > row.declared_amount:
            raise ValueError("Le montant approuvé dépasse le montant déclaré")
        if request.action == "assess_amount":
            row.received_amount = amount
        else:
            row.approved_amount = amount
    elif request.action == "pay":
        if amount is None or amount <= 0:
            raise ValueError("Montant payé strictement positif requis")
        row.paid_amount = (dec(row.paid_amount) or Decimal(0)) + amount
    elif request.action == "record_recovery":
        if amount is None or amount <= 0:
            raise ValueError("Montant recouvré strictement positif requis")
        row.recovered_amount = (dec(row.recovered_amount) or Decimal(0)) + amount
    elif request.action == "close":
        row.closed_at = datetime.now(timezone.utc)
    row.status = target
    data = deepcopy(row.data or {})
    data.setdefault("history", []).append(
        {
            "action": request.action,
            "reason": request.reason,
            "actor_id": actor.id,
            "from": previous,
            "to": target,
            "amount": iso(amount),
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    row.data = data
    session.add(
        ClaimEvent(
            claim_id=row.id,
            action=request.action,
            actor_id=actor.id,
            from_status=previous,
            to_status=target,
            amount=amount,
            data={"reason": request.reason},
        )
    )
    session.commit()
    return row


def claim_view(row):
    return {
        **_claim_dict(row),
        "guarantee_id": row.guarantee_id,
        "institution_id": row.institution_id,
        "data": deepcopy(row.data),
        "revision": row.revision,
    }


def claim_events(session, claim_id):
    from credit.intelligence.models import ClaimEvent as Event

    return [
        {
            "id": e.id,
            "action": e.action,
            "actor_id": e.actor_id,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "amount": str(e.amount) if e.amount is not None else None,
            "data": e.data,
            "created_at": iso(e.created_at),
        }
        for e in session.scalars(
            select(Event).where(Event.claim_id == claim_id).order_by(Event.created_at)
        )
    ]


# ---------------------------------------------------------------------------
# Capacité et portefeuille institutionnels
# ---------------------------------------------------------------------------


def upsert_capacity(session, actor, institution_id, body):
    row = session.get(InstitutionCapacity, institution_id)
    if row is None:
        row = InstitutionCapacity(institution_id=institution_id, updated_by=actor.id)
        session.add(row)
    for field in [
        "as_of",
        "own_funds",
        "mobilizable_resources",
        "liquidities",
        "provisions",
        "safety_reserve",
        "max_global_exposure",
        "coverage_limit",
        "max_sector_share",
        "max_bank_share",
        "max_borrower_share",
        "source_reference",
    ]:
        setattr(row, field, getattr(body, field))
    row.updated_by = actor.id
    session.commit()
    return row


def upsert_limit(session, actor, institution_id, body):
    row = session.scalar(
        select(InstitutionLimit).where(
            InstitutionLimit.institution_id == institution_id,
            InstitutionLimit.scope == body.scope,
            InstitutionLimit.key == body.key,
        )
    )
    if row is None:
        row = InstitutionLimit(
            institution_id=institution_id,
            scope=body.scope,
            key=body.key,
            updated_by=actor.id,
        )
        session.add(row)
    row.max_amount = body.max_amount
    row.max_share = body.max_share
    row.note = body.note
    row.updated_by = actor.id
    session.commit()
    return row


def limit_view(row):
    return {
        "id": row.id,
        "institution_id": row.institution_id,
        "scope": row.scope,
        "key": row.key,
        "max_amount": str(row.max_amount) if row.max_amount is not None else None,
        "max_share": str(row.max_share) if row.max_share is not None else None,
        "note": row.note,
        "updated_by": row.updated_by,
        "updated_at": iso(row.updated_at),
    }


def portfolio(session, institution_id):
    guarantees = [
        _guarantee_dict(g)
        for g in session.scalars(
            select(Guarantee).where(Guarantee.institution_id == institution_id)
        )
    ]
    claims = [
        _claim_dict(c)
        for c in session.scalars(select(Claim).where(Claim.institution_id == institution_id))
    ]
    config = capacity_config(session.get(InstitutionCapacity, institution_id))
    return {
        "institution_id": institution_id,
        "capacity": institutional_rules.capacity_summary(config, guarantees, claims),
        "portfolio": institutional_rules.portfolio_metrics(guarantees, claims),
        "claims": institutional_rules.claim_summary(claims),
        "limits": [
            limit_view(row)
            for row in session.scalars(
                select(InstitutionLimit).where(InstitutionLimit.institution_id == institution_id)
            )
        ],
        "rules_version": INSTITUTIONAL_RULES_VERSION,
    }


def stress(session, institution_id, scenarios):
    guarantees = [
        _guarantee_dict(g)
        for g in session.scalars(
            select(Guarantee).where(Guarantee.institution_id == institution_id)
        )
    ]
    config = capacity_config(session.get(InstitutionCapacity, institution_id))
    return institutional_rules.stress_test(
        config, guarantees, [s.model_dump(mode="json") for s in scenarios]
    )
