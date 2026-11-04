from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from credit.shared.arithmetic import deterministic


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_max_length=20000)


class SignedAmount(Contract):
    @field_validator("value", mode="before")
    @classmethod
    def exact_value(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Montant : chaîne décimale ou entier exact requis, pas de flottant")
        return value

    value: Decimal | None = Field(max_digits=24, decimal_places=2)
    state: Literal["known", "unknown", "not_applicable", "estimated"] = "known"
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent(self):
        if (self.state in {"known", "estimated"}) != (self.value is not None):
            raise ValueError("État et valeur signée incohérents")
        return self


class Evidence(Contract):
    id: str
    source: str
    period: date
    currency: str = "XOF"
    collected_at: date
    status: Literal["declared", "unverified_extracted", "verified", "contradictory", "missing"]
    verification_method: str | None = None
    page: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    submission_id: str | None = None
    run_id: str | None = None
    review_id: str | None = None
    value_reference: str | None = None
    authenticity_status: Literal["not_assessed"] = "not_assessed"
    source_locations: list[dict] = Field(default_factory=list)


class Amount(Contract):
    @field_validator("value", mode="before")
    @classmethod
    def exact_value(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Montant : chaîne décimale ou entier exact requis, pas de flottant")
        return value

    value: Decimal | None = Field(max_digits=24, decimal_places=2)
    state: Literal["known", "unknown", "not_applicable", "estimated"] = "known"
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent(self):
        if self.state in ("known", "estimated"):
            if self.value is None or self.value < 0:
                raise ValueError("Montant positif ou nul, au plus deux décimales")
        elif self.value is not None:
            raise ValueError("Valeur absente requise pour inconnu/non applicable")
        return self


class Payment(Contract):
    period: date
    principal: Amount
    interest: Amount
    fees: Amount
    due_date: date | None = None


class Loan(Contract):
    reference: str
    principal: Amount
    schedule: list[Payment]
    annual_nominal_rate: Decimal | None = Field(
        default=None, ge=0, le=10, max_digits=12, decimal_places=10
    )
    description: str = "Échéancier explicite de référence"
    amortization_method: Literal["explicit", "monthly_constant"] = "explicit"

    @model_validator(mode="after")
    @deterministic
    def unique(self):
        if len({p.period for p in self.schedule}) != len(self.schedule):
            raise ValueError("Échéance dupliquée")
        values = [p.principal.value for p in self.schedule]
        if self.principal.value is not None and all(v is not None for v in values):
            if sum(values) != self.principal.value:
                raise ValueError(
                    "Le capital doit correspondre au capital restant à rembourser dans l'échéancier"
                )
        for payment in self.schedule:
            if payment.due_date and payment.due_date.strftime("%Y-%m") != payment.period.strftime(
                "%Y-%m"
            ):
                raise ValueError("Date exigible hors du mois de l’échéance")
        if self.amortization_method == "monthly_constant":
            from credit.shared.schedule import monthly_schedule

            if (
                self.principal.value is None
                or self.annual_nominal_rate is None
                or not self.schedule
            ):
                raise ValueError(
                    "Conditions mensuelles constantes incomplètes ; utiliser un échéancier explicite"
                )
            fees = [p.fees.value for p in self.schedule]
            if None in fees or len(set(fees)) != 1:
                raise ValueError("Frais constants connus nécessaires au générateur mensuel")
            generated = monthly_schedule(
                self.principal.value,
                self.annual_nominal_rate,
                len(self.schedule),
                self.schedule[0].period,
                fees[0],
            )
            if any(
                (p.period, p.principal.value, p.interest.value, p.fees.value)
                != (g.period, g.principal.value, g.interest.value, g.fees.value)
                for p, g in zip(self.schedule, generated.schedule)
            ):
                raise ValueError(
                    "Échéancier incompatible avec les conditions mensuelles constantes"
                )
        return self


class Scenario(Contract):
    name: str = "Scénario paramétrable, sans valeur normative"
    revenue_drop: Decimal = Field(default=Decimal(0), ge=0, le=1, max_digits=12, decimal_places=10)
    expense_increase: Decimal = Field(
        default=Decimal(0), ge=0, le=10, max_digits=12, decimal_places=10
    )
    delay_from: date | None = None
    delay_to: date | None = None
    delay_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=24, decimal_places=2)

    @model_validator(mode="after")
    def delay(self):
        if self.delay_amount and (
            not self.delay_from or not self.delay_to or self.delay_to <= self.delay_from
        ):
            raise ValueError("Le retard exige deux périodes croissantes")
        return self


class BaseCase(Contract):
    name: str
    data_classification: Literal["real", "synthetic"] = "real"
    currency: Literal["XOF"] = "XOF"
    evidence: list[Evidence]
    missing_information: list[str] = Field(default_factory=list)
    existing_loans: list[Loan]
    requested_loan: Loan

    @model_validator(mode="after")
    def references(self):
        ids = [e.id for e in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Preuve dupliquée")
        if any(e.currency != self.currency for e in self.evidence):
            raise ValueError("Conversion explicite requise : seule XOF est acceptée")
        refs = [x.reference for x in self.existing_loans] + [self.requested_loan.reference]
        if len(refs) != len(set(refs)):
            raise ValueError("Dette comptée deux fois")

        nodes = 0

        def walk(node):
            nonlocal nodes
            nodes += 1
            if nodes > 30000:
                raise ValueError("Dossier trop complexe")
            if isinstance(node, (Amount, SignedAmount)):
                if not set(node.evidence_ids) <= set(ids):
                    raise ValueError("Référence de preuve inconnue")
            elif isinstance(node, BaseModel):
                if hasattr(node, "evidence_ids") and not set(node.evidence_ids) <= set(ids):
                    raise ValueError("Référence de preuve inconnue")
                for key in type(node).model_fields:
                    walk(getattr(node, key))
            elif isinstance(node, (list, dict)):
                if len(node) > 1000:
                    raise ValueError("Collection trop volumineuse")
                for item in node.values() if isinstance(node, dict) else node:
                    walk(item)

        walk(self)
        details = getattr(self, "analysis_details", None)
        if details is not None and details.as_of is not None:
            if any(p.basis == "observed" and p.period > details.as_of for p in self.periods):
                raise ValueError(
                    "Flux observé postérieur à la date de référence : déclarer une prévision"
                )
            if any(p.period > details.as_of for p in getattr(self, "income_history", [])):
                raise ValueError("Historique de revenus postérieur à la date de référence")
            if any(p.as_of > details.as_of for p in details.repayment_observations):
                raise ValueError("Historique de remboursement postérieur à la date de référence")
            if any(
                p.basis == "observed" and p.end > details.as_of
                for p in getattr(details, "accounting", [])
            ):
                raise ValueError("Compte observé postérieur à la date de référence")
        return self
