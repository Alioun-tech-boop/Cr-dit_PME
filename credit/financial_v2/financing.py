"""Exploration bornée de propositions de produit, sans modifier les faits source."""

from decimal import Decimal
from datetime import date
import calendar
from credit.shared.contracts import Loan, Payment, Amount
from credit.shared.schedule import monthly_schedule, rounded
from credit.shared.calculation import Context
from credit.assessment.simulation import loan_summary
from credit.financial_v2.scenarios import prepare


def constraints(financial, product):
    results = []

    def add(id, values, threshold, op):
        passed = (
            None
            if any(v is None for v in values) or not values
            else all(op(v, threshold) for v in values)
        )
        results.append({"id": id, "threshold": threshold, "observed": values, "passed": passed})

    add(
        "no_unfunded_monthly_deficit",
        [p.closing_reserve_or_cash for p in financial.periods],
        Decimal(0),
        lambda a, b: a >= b,
    )
    if product.minimum_margin is not None:
        add(
            "minimum_remaining_margin",
            [p.margin_after_debt for p in financial.periods],
            product.minimum_margin,
            lambda a, b: a >= b,
        )
    if product.minimum_reserve is not None:
        add(
            "minimum_reserve",
            [p.closing_reserve_or_cash for p in financial.periods],
            product.minimum_reserve,
            lambda a, b: a >= b,
        )
    if product.minimum_debt_coverage is not None:
        values = []
        for p in financial.periods:
            debt = (
                None
                if p.existing_debt_service is None or p.new_debt_service is None
                else p.existing_debt_service + p.new_debt_service
            )
            if debt == 0:
                continue
            available = getattr(
                p, "cash_available_for_debt", getattr(p, "available_before_debt", None)
            )
            values.append(
                None if available is None or debt is None or debt <= 0 else available / debt
            )
        if values:
            add("minimum_debt_coverage", values, product.minimum_debt_coverage, lambda a, b: a >= b)
        else:
            results.append(
                {
                    "id": "minimum_debt_coverage",
                    "passed": True,
                    "status": "not_applicable_no_debt",
                    "observed": [],
                    "threshold": product.minimum_debt_coverage,
                }
            )
    return results


def variants(case, policy, candidates, scenarios, facts, calculate):
    if not candidates:
        return {"status": "not_requested", "variants": [], "maximum_compatible_among_tested": None}
    if policy is None:
        return {
            "status": "policy_required",
            "variants": [],
            "maximum_compatible_among_tested": None,
            "information_requested": [
                "Politique produit approuvée et barème ou conditions contractuelles explicitement autorisées"
            ],
        }
    product = policy.product
    results = []
    base = calculate(case)
    reader = Context(case, None)
    for candidate in candidates:
        item = {
            "parameters": candidate.model_dump(mode="json"),
            "compatible": False,
            "constraints": [],
            "assumptions": [],
            "status": "unavailable",
        }
        try:
            total_months = candidate.months + candidate.grace_months
            if (
                not product.min_amount <= candidate.principal <= product.max_amount
                or not product.min_months <= total_months <= product.max_months
            ):
                raise ValueError("Montant ou durée hors des limites du produit")
            if candidate.grace_months not in product.allowed_grace_months:
                raise ValueError("Différé non autorisé")
            raw = case.model_dump(mode="json")
            first = case.periods[0].period
            if candidate.schedule:
                if "explicit" not in product.schedules:
                    raise ValueError("Échéancier explicite non autorisé")
                expected_duration = (
                    (
                        max(p.period for p in candidate.schedule).year
                        - min(p.period for p in candidate.schedule).year
                    )
                    * 12
                    + max(p.period for p in candidate.schedule).month
                    - min(p.period for p in candidate.schedule).month
                    + 1
                )
                if expected_duration != total_months:
                    raise ValueError("Durée déclarée différente du calendrier explicite")
                loan = Loan(
                    reference=case.requested_loan.reference,
                    principal=Amount(value=candidate.principal),
                    schedule=candidate.schedule,
                )
                item["assumptions"].append(
                    "Échéancier contractuel alternatif fourni, aucune conversion en mensualité constante."
                )
            else:
                if "monthly_constant" not in product.schedules:
                    raise ValueError("Mensualités constantes non autorisées")
                if first.day not in product.allowed_due_days:
                    raise ValueError("Date initiale non autorisée par le produit")
                matches = [
                    t
                    for t in product.tariffs
                    if t.min_amount <= candidate.principal <= t.max_amount
                    and t.min_months <= total_months <= t.max_months
                ]
                if matches:
                    rate, fee = matches[0].annual_rate, matches[0].fee_per_payment
                    item["pricing_reference"] = matches[0].reference
                elif product.allow_unchanged_contract_pricing:
                    rate = case.requested_loan.annual_nominal_rate
                    fees = [
                        reader.amount(p.fees, "frais contractuels")
                        for p in case.requested_loan.schedule
                    ]
                    if rate is None or None in fees or len(set(fees)) != 1:
                        raise ValueError("Taux et frais contractuels constants à fournir")
                    fee = fees[0]
                    item["pricing_reference"] = "unchanged_contract_explicitly_authorized"
                else:
                    raise ValueError("Aucun barème fourni pour ce montant et cette durée")
                index = first.year * 12 + first.month - 1 + candidate.grace_months
                y, m = divmod(index, 12)
                start = date(y, m + 1, min(first.day, calendar.monthrange(y, m + 1)[1]))
                loan = monthly_schedule(candidate.principal, rate, candidate.months, start, fee)
                loan.reference = case.requested_loan.reference
                if candidate.grace_months:
                    if product.grace_interest_treatment != "interest_only":
                        raise ValueError("Convention d’intérêts du différé non configurée")
                    grace = []
                    for i in range(candidate.grace_months):
                        year, month = divmod(first.year * 12 + first.month - 1 + i, 12)
                        day = min(first.day, calendar.monthrange(year, month + 1)[1])
                        d = date(year, month + 1, day)
                        grace.append(
                            Payment(
                                period=d,
                                due_date=d,
                                principal=Amount(value=0),
                                interest=Amount(value=rounded(candidate.principal * rate / 12)),
                                fees=Amount(value=fee),
                            )
                        )
                    loan.schedule = grace + loan.schedule
                    loan.amortization_method = "explicit"
                    item["assumptions"].append(
                        "Différé de capital : intérêts et frais payés pendant le différé, aucun intérêt capitalisé."
                    )
            if any(
                (p.due_date or p.period).day not in product.allowed_due_days for p in loan.schedule
            ):
                raise ValueError("Jour d’échéance non autorisé")
            item.update(
                terms_before=loan_summary(case.requested_loan, reader),
                terms_after=loan_summary(loan),
                schedule=loan.model_dump(mode="json")["schedule"],
            )
            horizon = {p.period for p in case.periods}
            missing = sorted({p.period for p in loan.schedule} - horizon)
            if missing:
                item.update(
                    status="needs_explicit_projections",
                    information_requested=[
                        "Flux explicites pour " + ", ".join(str(d) for d in missing)
                    ],
                )
                results.append(item)
                continue
            raw["requested_loan"] = loan.model_dump(mode="json")
            if hasattr(case, "opening_cash"):
                disb = [
                    reader.amount(p.requested_loan_disbursement, "décaissement initial")
                    for p in case.periods
                ]
                if None in disb or case.requested_loan.principal.value is None:
                    raise ValueError("Décaissements initiaux à documenter")
                old = case.requested_loan.principal.value
                remaining = candidate.principal
                active = [i for i, v in enumerate(disb) if v > 0]
                for i in active:
                    v = (
                        remaining
                        if i == active[-1]
                        else rounded(disb[i] * candidate.principal / old)
                    )
                    remaining -= v
                    raw["periods"][i]["requested_loan_disbursement"] = {
                        "value": str(v),
                        "state": "estimated",
                        "evidence_ids": [],
                    }
                item["assumptions"].append(
                    "Financement reçu ajusté ; emplois du projet inchangés, apport nouveau non supposé disponible."
                )
            contribution = (
                reader.amount(candidate.contribution, "apport alternatif")
                if candidate.contribution
                else reader.amount(
                    case.analysis_details.funding.announced_contribution, "apport annoncé"
                )
                if case.analysis_details.funding.announced_contribution
                else None
            )
            if candidate.contribution:
                verified = {e.id for e in case.evidence if e.status == "verified"}
                if (
                    not candidate.contribution_evidence_ids
                    or not set(candidate.contribution_evidence_ids) <= verified
                ):
                    item["constraints"].append(
                        {
                            "id": "contribution_verified",
                            "passed": None,
                            "information_requested": "Disponibilité et provenance de l’apport à vérifier",
                        }
                    )
                elif (
                    hasattr(case, "opening_cash")
                    and candidate.contribution_already_in_opening_cash is False
                ):
                    opening = reader.amount(case.opening_cash, "trésorerie initiale")
                    if contribution is None or opening is None:
                        raise ValueError("Apport et trésorerie à rapprocher")
                    raw["opening_cash"] = {
                        "value": str(opening + contribution),
                        "state": "estimated",
                        "evidence_ids": [],
                    }
                    item["assumptions"].append(
                        "Apport vérifié, explicitement exclu de la trésorerie initiale, supposé disponible dès le début ; date et absence de double comptage explicitement déclarées."
                    )
                elif (
                    hasattr(case, "opening_cash")
                    and candidate.contribution_already_in_opening_cash is None
                ):
                    item["constraints"].append(
                        {
                            "id": "contribution_cash_inclusion",
                            "passed": None,
                            "information_requested": "Préciser si l’apport est déjà inclus dans la trésorerie initiale",
                        }
                    )
            need = (
                reader.amount(case.analysis_details.funding.justified_need, "besoin justifié")
                if case.analysis_details.funding.justified_need
                else None
            )
            existing_verified = case.analysis_details.funding.verified_contribution
            controlled = {e.id for e in case.evidence if e.status == "verified"}
            if candidate.contribution is None:
                contribution = (
                    reader.amount(existing_verified, "apport contrôlé")
                    if existing_verified
                    else None
                )
                contribution_controlled = bool(
                    existing_verified
                    and existing_verified.evidence_ids
                    and set(existing_verified.evidence_ids) <= controlled
                )
            else:
                contribution_controlled = bool(
                    candidate.contribution_evidence_ids
                    and set(candidate.contribution_evidence_ids) <= controlled
                )
            required_gap = None if need is None else max(Decimal(0), need - candidate.principal)
            item["constraints"].append(
                {
                    "id": "justified_need_and_funding_gap",
                    "need": need,
                    "unfunded_gap": required_gap,
                    "passed": None
                    if need is None
                    else False
                    if candidate.principal > need
                    else True
                    if required_gap == 0
                    else None
                    if contribution is None or not contribution_controlled
                    else contribution >= required_gap,
                    "notice": "Montant limité au besoin fourni ; tout complément doit être réellement disponible et contrôlé.",
                }
            )
            if product.minimum_contribution_share is not None:
                need = (
                    reader.amount(case.analysis_details.funding.justified_need, "besoin justifié")
                    if case.analysis_details.funding.justified_need
                    else None
                )
                share = None if contribution is None or not need else contribution / need
                item["constraints"].append(
                    {
                        "id": "minimum_contribution_share",
                        "observed": share,
                        "threshold": product.minimum_contribution_share,
                        "passed": None
                        if share is None
                        or (product.minimum_contribution_share > 0 and not contribution_controlled)
                        else share >= product.minimum_contribution_share,
                    }
                )
            alternative = type(case).model_validate(raw)
            result = calculate(alternative)
            item["constraints"] += constraints(result, product)
            required = set(policy.required_scenarios)
            provided = {s.id for s in scenarios}
            if required - provided:
                item["constraints"].append(
                    {
                        "id": "required_stresses",
                        "passed": None,
                        "missing": sorted(required - provided),
                    }
                )
            stress_results = []
            for s in scenarios:
                if s.id not in required:
                    continue
                stressed, notes, _ = prepare(alternative, s, facts)
                sr = calculate(stressed)
                tests = constraints(sr, product)
                stress_results.append(
                    {"scenario": s.id, "constraints": tests, "assumptions": notes}
                )
                item["constraints"] += [{**t, "scenario_id": s.id} for t in tests]
            item.update(
                status="evaluated",
                compatible=all(c["passed"] is True for c in item["constraints"]),
                scenarios=stress_results,
                before={
                    "minimum_margin": min_or_none([p.margin_after_debt for p in base.periods]),
                    "minimum_balance": base.financial_findings.minimum_balance,
                },
                after={
                    "minimum_margin": min_or_none([p.margin_after_debt for p in result.periods]),
                    "minimum_balance": result.financial_findings.minimum_balance,
                },
                input_snapshot=raw,
            )
        except ValueError as error:
            item["reason"] = str(error)
        results.append(item)
    compatible = [v for v in results if v["compatible"]]
    return {
        "status": "compatible_alternatives_found"
        if compatible
        else "no_compatible_solution_in_tested_set",
        "variants": results,
        "maximum_compatible_among_tested": max(
            (Decimal(v["parameters"]["principal"]) for v in compatible), default=None
        ),
        "notice": "Exploration bornée des candidats fournis, pas un optimum global ni un financement conseillé. Les prérequis de disponibilité de l’apport restent indépendants.",
    }


def min_or_none(values):
    return min(values) if values and None not in values else None


def loan_constraints(case, product):
    """Applicabilité contractuelle distincte des faits de solvabilité du client."""
    reader = Context(case, None)
    loan = case.requested_loan
    principal = reader.amount(loan.principal, "requested_loan.principal")
    duration = (
        (
            (loan.schedule[-1].period.year - loan.schedule[0].period.year) * 12
            + loan.schedule[-1].period.month
            - loan.schedule[0].period.month
            + 1
        )
        if loan.schedule
        else None
    )
    checks = [
        {
            "id": "product_amount",
            "observed": principal,
            "passed": None
            if principal is None
            else product.min_amount <= principal <= product.max_amount,
        },
        {
            "id": "product_duration",
            "observed": duration,
            "passed": None
            if duration is None
            else product.min_months <= duration <= product.max_months,
        },
        {
            "id": "product_calendar",
            "passed": all(
                (p.due_date or p.period).day in product.allowed_due_days for p in loan.schedule
            ),
        },
        {
            "id": "product_schedule_type",
            "observed": loan.amortization_method,
            "passed": loan.amortization_method in product.schedules,
        },
    ]
    minimum_share = product.minimum_contribution_share
    if minimum_share is not None and minimum_share > 0:
        funding = case.analysis_details.funding
        need = (
            reader.amount(funding.justified_need, "funding.justified_need")
            if funding.justified_need
            else None
        )
        value = funding.verified_contribution
        verified = {e.id for e in case.evidence if e.status == "verified"}
        controlled = bool(value and value.evidence_ids and set(value.evidence_ids) <= verified)
        contribution = reader.amount(value, "funding.verified_contribution") if value else None
        share = (
            contribution / need
            if need and need > 0 and contribution is not None and controlled
            else None
        )
        checks.append(
            {
                "id": "minimum_contribution_share",
                "observed": share,
                "threshold": minimum_share,
                "passed": None if share is None else share >= minimum_share,
            }
        )
    return checks
