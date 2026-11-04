from copy import deepcopy
import calendar
from datetime import date
from decimal import Decimal
from typing import Literal, Any

from pydantic import Field
from credit.shared.contracts import Contract, Scenario, Payment
from credit.shared.schedule import monthly_schedule, rounded


class SimulationSpec(Contract):
    kind: Literal[
        "stress", "lower_amount", "extend_term", "calendar", "existing_restructure", "startup_delay"
    ]
    scenario: Scenario | None = None
    principal: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=2)
    months: int | None = Field(default=None, gt=0, le=600)
    schedule: list[Payment] | None = None
    existing_reference: str | None = None
    documented_schedule_evidence_ids: list[str] = Field(default_factory=list)
    startup_delay_periods: int | None = Field(default=None, ge=1, le=60)
    # Validées par le contrat du noyau avant toute exécution ; aucune prolongation d'une moyenne.
    future_periods: list[dict[str, Any]] = Field(default_factory=list, max_length=600)
    projection_assumptions: list[str] = Field(default_factory=list, max_length=100)


def loan_summary(loan, reader=None):
    def get(payment):
        values = [
            reader.amount(getattr(payment, k), "conditions." + k, k == "principal")
            if reader
            else Decimal(0)
            if k != "principal" and getattr(payment, k).state == "not_applicable"
            else getattr(payment, k).value
            for k in ["principal", "interest", "fees"]
        ]
        return None if None in values else sum(values)

    totals = [get(p) for p in loan.schedule]
    principal = reader.amount(loan.principal, "capital demandé") if reader else loan.principal.value
    complete = all(v is not None for v in totals)
    total = sum(totals) if complete else None
    return {
        "principal": principal,
        "payment_count": len(totals),
        "first_due": loan.schedule[0].period.isoformat() if loan.schedule else None,
        "last_due": loan.schedule[-1].period.isoformat() if loan.schedule else None,
        "first_instalment": totals[0] if totals else None,
        "maximum_instalment": max(totals) if totals and complete else None,
        "total_repayment": total,
        "total_credit_cost": None if total is None or principal is None else total - principal,
        "annual_nominal_rate": loan.annual_nominal_rate,
        "method": loan.amortization_method,
        "duration_months": len(totals) if loan.amortization_method == "monthly_constant" else None,
        "fee_treatment": "Frais séparés, maintenus selon le contrat explicite ; aucun taux effectif réglementaire.",
    }


def change_loan(case, policy, principal, months):
    old = case.requested_loan
    from credit.shared.calculation import Context

    reader = Context(case, None)
    if reader.amount(old.principal, "capital demandé") is None or any(
        reader.amount(getattr(p, k), "conditions." + k, k == "principal") is None
        for p in old.schedule
        for k in ["principal", "interest", "fees"]
    ):
        raise ValueError("Valider les valeurs et preuves des conditions du prêt avant recalcul")
    if not policy:
        raise ValueError(
            "Politique produit applicable nécessaire à une nouvelle condition de financement"
        )
    if case.analysis_details.funding.product_id != policy.product.id:
        raise ValueError("Produit non couvert par cette politique")
    if (
        old.amortization_method != "monthly_constant"
        or "monthly_constant" not in policy.product.schedules
    ):
        raise ValueError(
            "Échéancier irrégulier : fournir un calendrier autorisé explicite, sans le convertir en prêt mensuel constant"
        )
    if (
        old.annual_nominal_rate is None
        or not old.schedule
        or any(p.fees.value is None for p in old.schedule)
    ):
        raise ValueError("Taux, première échéance et frais connus nécessaires")
    if len({p.fees.value for p in old.schedule}) != 1:
        raise ValueError("Frais irréguliers : proposition contractuelle explicite requise")
    if not policy.product.min_months <= months <= policy.product.max_months:
        raise ValueError("Durée hors des limites du produit")
    if (
        old.schedule[0].due_date or old.schedule[0].period
    ).day not in policy.product.allowed_due_days:
        raise ValueError("Date non autorisée par le produit")
    loan = monthly_schedule(
        principal,
        old.annual_nominal_rate,
        months,
        old.schedule[0].period,
        old.schedule[0].fees.value,
    )
    due_day = (old.schedule[0].due_date or old.schedule[0].period).day
    for index, payment in enumerate(loan.schedule):
        if index < len(old.schedule) and old.schedule[index].due_date is not None:
            payment.due_date = old.schedule[index].due_date
        else:
            payment.due_date = date(
                payment.period.year,
                payment.period.month,
                min(due_day, calendar.monthrange(payment.period.year, payment.period.month)[1]),
            )
        if payment.due_date.day not in policy.product.allowed_due_days:
            raise ValueError("Date proposée non autorisée par le produit")
    return loan.model_copy(
        update={
            "reference": old.reference,
            "amortization_method": "monthly_constant",
            "description": "Simulation conditionnelle, non contractuelle, sur copie du dossier",
        }
    )


def prepare_simulation(case, spec, policy=None):
    raw = case.model_dump(mode="json")
    notes = []
    terms = None
    if spec.future_periods:
        if not spec.projection_assumptions:
            raise ValueError("Hypothèses explicites nécessaires pour les nouvelles périodes")
        old_dates = {p["period"] for p in raw["periods"]}
        end = max(old_dates)
        if any(
            p.get("period", "") <= end or p.get("basis", "forecast") != "forecast"
            for p in spec.future_periods
        ):
            raise ValueError("Les périodes ajoutées doivent être futures et prévisionnelles")
        raw["periods"] += deepcopy(spec.future_periods)
        raw["analysis_details"]["projection_assumptions"] += [
            {"text": s, "evidence_ids": []} for s in spec.projection_assumptions
        ]
        notes.extend(spec.projection_assumptions)
    if spec.kind in {"lower_amount", "extend_term"}:
        principal = (
            spec.principal if spec.kind == "lower_amount" else case.requested_loan.principal.value
        )
        months = spec.months if spec.kind == "extend_term" else len(case.requested_loan.schedule)
        if principal is None or months is None:
            raise ValueError("Montant ou durée de simulation manquant")
        if spec.kind == "lower_amount" and principal >= case.requested_loan.principal.value:
            raise ValueError("La simulation doit réduire le montant")
        if spec.kind == "extend_term" and months <= len(case.requested_loan.schedule):
            raise ValueError("La simulation doit allonger la durée")
        new = change_loan(case, policy, principal, months)
        terms = {"before": loan_summary(case.requested_loan), "after": loan_summary(new)}
        raw["requested_loan"] = new.model_dump(mode="json")
        if hasattr(case, "opening_cash") and spec.kind == "lower_amount":
            old = case.requested_loan.principal.value
            known = [p.requested_loan_disbursement.value for p in case.periods]
            if any(v is None for v in known) or not old:
                raise ValueError("Décaissements du financement à documenter")
            remaining = principal
            active = [i for i, v in enumerate(known) if v > 0]
            for i in active:
                value = remaining if i == active[-1] else rounded(known[i] * principal / old)
                remaining -= value
                raw["periods"][i]["requested_loan_disbursement"]["value"] = str(value)
                raw["periods"][i]["requested_loan_disbursement"]["state"] = "estimated"
            notes.append(
                "Crédit reçu réduit ; emplois des fonds inchangés. Tout besoin résiduel doit être financé par un apport réel vérifié ou un projet redimensionné."
            )
        horizon = {p["period"] for p in raw["periods"]}
        beyond = [p.period.isoformat() for p in new.schedule if p.period.isoformat() not in horizon]
        if beyond:
            return {
                "status": "needs_explicit_projections",
                "case": None,
                "terms": terms,
                "assumptions": notes,
                "missing_information": [
                    "Flux explicites pour les échéances : " + ", ".join(beyond)
                ],
                "input_snapshot": raw,
            }
    elif spec.kind in {"calendar", "existing_restructure"}:
        if not policy or "explicit" not in policy.product.schedules:
            raise ValueError("Échéancier explicite non autorisé par une politique applicable")
        if not spec.schedule:
            raise ValueError("Échéancier explicite nécessaire")
        if any(
            (p.due_date or p.period).day not in policy.product.allowed_due_days
            for p in spec.schedule
        ):
            raise ValueError("Jour d’échéance non autorisé par le produit")
        selected = raw["requested_loan"]
        if spec.kind == "existing_restructure":
            if not spec.documented_schedule_evidence_ids or not set(
                spec.documented_schedule_evidence_ids
            ) <= {e.id for e in case.evidence}:
                raise ValueError("Échéancier de restructuration documenté requis")
            selected = next(
                (
                    loan
                    for loan in raw["existing_loans"]
                    if loan["reference"] == spec.existing_reference
                ),
                None,
            )
            if selected is None:
                raise ValueError("Dette existante inconnue")
        first_date = min(p.period for p in spec.schedule)
        last_date = max(p.period for p in spec.schedule)
        calendar_months = (
            (last_date.year - first_date.year) * 12 + last_date.month - first_date.month + 1
        )
        if not policy.product.min_months <= calendar_months <= policy.product.max_months:
            raise ValueError("Échéancier explicite hors des limites calendaires du produit")
        selected["schedule"] = [p.model_dump(mode="json") for p in spec.schedule]
        selected["amortization_method"] = "explicit"
        notes.append(
            "Calendrier alternatif explicitement fourni ; accord du prêteur et faisabilité des dates à confirmer."
        )
    elif spec.kind == "startup_delay":
        if not hasattr(case, "opening_cash") or not spec.startup_delay_periods:
            raise ValueError(
                "Retard de démarrage réservé à un projet entreprise avec nombre de périodes"
            )
        receipts = case.analysis_details.project_receipts
        if not receipts:
            raise ValueError(
                "Recettes du projet identifiées séparément nécessaires ; ne pas décaler tout le chiffre d’affaires"
            )
        dates = [p["period"] for p in raw["periods"]]
        moves = []
        for receipt in receipts:
            if not receipt.included_in_receipts:
                continue
            value = receipt.amount.value
            if value is None:
                raise ValueError("Recette du projet inconnue")
            index = dates.index(receipt.period.isoformat())
            target = index + spec.startup_delay_periods
            if target >= len(dates):
                return {
                    "status": "needs_explicit_projections",
                    "case": None,
                    "terms": None,
                    "assumptions": [],
                    "missing_information": [
                        "Périodes futures explicites nécessaires pour recevoir les recettes déplacées"
                    ],
                    "input_snapshot": raw,
                }
            moves.append((index, target, value))
        changes = {i: Decimal(0) for i in range(len(dates))}
        for i, j, v in moves:
            changes[i] -= v
            changes[j] += v
        for i, change in changes.items():
            value = raw["periods"][i]["receipts"]["value"]
            if value is None:
                raise ValueError("Encaissement de période inconnu")
            updated = Decimal(value) + change
            if updated < 0:
                raise ValueError("Recettes du projet supérieures aux encaissements inclus")
            raw["periods"][i]["receipts"]["value"] = str(updated)
            raw["periods"][i]["receipts"]["state"] = "estimated"
        for receipt in raw["analysis_details"]["project_receipts"]:
            if receipt["included_in_receipts"]:
                receipt["period"] = dates[
                    dates.index(receipt["period"]) + spec.startup_delay_periods
                ]
        notes.append(
            f"Recettes de projet seulement décalées de {spec.startup_delay_periods} périodes ; pas de ventes futures garanties."
        )
    elif spec.kind == "stress":
        if spec.scenario is None:
            raise ValueError("Hypothèses de stress nécessaires")
        # Le noyau applique le stress aux agrégats ; aucun original n'est changé.
        notes.append(spec.scenario.model_dump_json())
    alternative = type(case).model_validate(raw)
    return {
        "status": "available",
        "case": alternative,
        "terms": terms,
        "assumptions": notes,
        "missing_information": [],
        "input_snapshot": raw,
    }
