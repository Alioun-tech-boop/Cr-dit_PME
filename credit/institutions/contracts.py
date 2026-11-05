from datetime import date as Date
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import Field, field_validator, model_validator
from credit.shared.contracts import Contract


class AccountCreate(Contract):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[^\s<>]+$")
    professional_name: str = Field(min_length=2, max_length=150)
    function: str = Field(min_length=2, max_length=150)
    role: Literal["bank_agent", "bank_manager"]


class AccountChange(Contract):
    expected_revision: int = Field(ge=1)
    status: Literal["active", "disabled", "deleted"] | None = None
    role: Literal["bank_agent", "bank_manager"] | None = None
    professional_name: str | None = Field(default=None, min_length=2, max_length=150)
    function: str | None = Field(default=None, min_length=2, max_length=150)


class Expected(Contract):
    expected_revision: int = Field(ge=1)


class ActivateAccount(Contract):
    token: str = Field(min_length=40, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    password_confirmation: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def match(self):
        if self.password != self.password_confirmation:
            raise ValueError("Les mots de passe doivent correspondre")
        return self


class PartnerEdit(Contract):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=3, max_length=200)
    presentation: str = Field(min_length=5, max_length=3000)
    institution_type: Literal["bank", "microfinance"]
    country: str = Field(min_length=2, max_length=2)
    activity_scope: str = Field(min_length=3, max_length=1000)


class Installment(Contract):
    date: Date
    principal: Decimal = Field(ge=0, max_digits=24, decimal_places=2)
    interest: Decimal = Field(ge=0, max_digits=24, decimal_places=2)
    fees: Decimal = Field(ge=0, max_digits=24, decimal_places=2)

    @field_validator("principal", "interest", "fees", mode="before")
    @classmethod
    def exact(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Utiliser des montants décimaux exacts")
        return value


class AgreementTerms(Contract):
    @model_validator(mode="before")
    @classmethod
    def percent_input(cls, value):
        if isinstance(value, dict) and "annual_rate_percent" in value:
            value = dict(value)
            raw = value.pop("annual_rate_percent")
            if (
                "annual_nominal_rate" in value
                or isinstance(raw, (float, bool))
                or not isinstance(raw, (str, int, Decimal))
            ):
                raise ValueError("Fournir un seul taux, en décimal exact")
            try:
                value["annual_nominal_rate"] = Decimal(raw) / Decimal(100)
            except InvalidOperation as exc:
                raise ValueError("Taux invalide") from exc
        return value

    reference: str = Field(min_length=3, max_length=100)
    product: str = Field(min_length=3, max_length=150)
    principal: Decimal = Field(gt=0, max_digits=24, decimal_places=2)
    currency: Literal["XOF"]
    annual_nominal_rate: Decimal = Field(ge=0, le=10, max_digits=12, decimal_places=10)
    months: int = Field(ge=1, le=600)
    first_due_date: Date
    fee_per_payment: Decimal = Field(ge=0, max_digits=24, decimal_places=2)
    upfront_fees: Decimal = Field(ge=0, max_digits=24, decimal_places=2)
    insurance_cost: Decimal = Field(ge=0, max_digits=24, decimal_places=2)
    disbursement_date: Date
    insurance: str = Field(min_length=3, max_length=2000)
    collateral: str = Field(min_length=3, max_length=2000)
    disbursement_conditions: str = Field(min_length=3, max_length=2000)
    payment_method: str = Field(min_length=3, max_length=1000)
    early_repayment: str = Field(min_length=3, max_length=2000)
    late_payment: str = Field(min_length=3, max_length=2000)
    validity_until: Date
    signatory_name: str = Field(min_length=2, max_length=150)
    signatory_function: str = Field(min_length=2, max_length=150)
    schedule: list[Installment] = Field(default_factory=list, max_length=600)

    @field_validator(
        "principal",
        "annual_nominal_rate",
        "fee_per_payment",
        "upfront_fees",
        "insurance_cost",
        mode="before",
    )
    @classmethod
    def exact(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Utiliser une chaîne décimale exacte")
        return value

    @model_validator(mode="after")
    def coherent(self):
        if self.disbursement_date > self.first_due_date:
            raise ValueError("Le décaissement doit précéder la première échéance")
        if self.schedule:
            dates = [x.date for x in self.schedule]
            if (
                dates != sorted(set(dates))
                or dates[0] != self.first_due_date
                or len(dates) != self.months
            ):
                raise ValueError(
                    "Dates triées, uniques et cohérentes avec le nombre d’échéances requis"
                )
            if sum(x.principal for x in self.schedule) != self.principal:
                raise ValueError("Le capital des échéances doit égaler le montant financé")
        return self


class BankDecision(Contract):
    expected_revision: int = Field(ge=1)
    decision: Literal["approved", "refused"]
    public_reason: str = Field(min_length=5, max_length=3000)
    signature_mode: Literal["detached", "unsigned"] = "detached"
    terms: AgreementTerms | None = None
    preview_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def required(self):
        if (self.decision == "approved") != (self.terms is not None):
            raise ValueError("Les conditions complètes sont requises uniquement pour un accord")
        return self
