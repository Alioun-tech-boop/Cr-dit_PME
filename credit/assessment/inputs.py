"""Compléments structurés : pas d'extraction ni de choix automatique de candidat."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field, model_validator, field_validator
from credit.shared.contracts import Amount, SignedAmount, Contract


class Note(Contract):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class IdentityChecks(Contract):
    subject_linked: bool | None = None
    household_confirmed: bool | None = None
    representation_confirmed: bool | None = None
    authorizations_applicable: bool | None = None
    authorizations_confirmed: bool | None = None
    contradictions: list[Note] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class RepaymentObservation(Contract):
    loan_reference: str
    as_of: date
    arrears: Amount
    days_past_due: int | None = Field(default=None, ge=0)
    restructuring_count: int | None = Field(default=None, ge=0)


class ExpenseItem(Contract):
    period: date
    category: Literal[
        "housing",
        "food",
        "health",
        "education",
        "transport",
        "utilities",
        "family_obligation",
        "other",
    ]
    frequency: Literal["recurring", "irregular", "future"]
    amount: Amount
    included_in_total: bool = True


class DatedFlow(Contract):
    period: date
    date: date
    kind: Literal[
        "income", "essential", "receipts", "necessary_outflow", "financing", "financed_use"
    ]
    amount: Amount

    @model_validator(mode="after")
    def within_period(self):
        if self.date.strftime("%Y-%m") != self.period.strftime("%Y-%m"):
            raise ValueError("Flux daté hors du mois de sa période")
        return self


class FundingPlan(Contract):
    product_id: str = "unclassified"
    justified_need: Amount | None = None
    announced_contribution: Amount | None = None
    verified_contribution: Amount | None = None
    purpose: Note | None = None
    implementation_start: date | None = None
    expected_start: date | None = None


class CommonDetails(Contract):
    as_of: date | None = None
    identity: IdentityChecks = Field(default_factory=IdentityChecks)
    funding: FundingPlan = Field(default_factory=FundingPlan)
    repayment_history_applicable: bool | None = None
    repayment_observations: list[RepaymentObservation] = Field(default_factory=list)
    projection_assumptions: list[Note] = Field(default_factory=list)
    timing_complete: bool = False
    dated_flows: list[DatedFlow] = Field(default_factory=list)


class IndividualDetails(CommonDetails):
    continuity: list[Note] = Field(default_factory=list)
    expenses: list[ExpenseItem] = Field(default_factory=list)
    expense_breakdown_complete: bool = False
    blocked_savings: Amount | None = None


class Counterparty(Contract):
    name: str
    period: date
    role: Literal["customer", "supplier"]
    flow_kind: Literal["receipt", "invoice", "order", "purchase", "payment"]
    amount: Amount


class AccountingPeriod(Contract):
    start: date
    end: date
    currency: Literal["XOF"] = "XOF"
    unit_multiplier: Literal[Decimal("1"), Decimal("1000"), Decimal("1000000")] | None = None
    basis: Literal["observed", "forecast"] = "observed"
    turnover: Amount
    operating_expenses: Amount
    cost_of_sales: Amount | None = None
    costs_definition: Literal["excluding_cost_of_sales", "including_cost_of_sales"] = (
        "excluding_cost_of_sales"
    )
    operating_result: SignedAmount | None = None
    net_result: SignedAmount | None = None
    equity: SignedAmount | None = None
    total_debt: Amount | None = None

    @field_validator("unit_multiplier", mode="before")
    @classmethod
    def explicit_unit(cls, value):
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation:
            raise ValueError("Multiplicateur d’unité comptable invalide") from None

    @model_validator(mode="after")
    def coherent(self):
        if self.end < self.start:
            raise ValueError("Période comptable inversée")
        return self


class WorkingCapital(Contract):
    as_of: date
    period_start: date | None = None
    period_end: date | None = None
    inventory: Amount
    receivables: Amount
    payables: Amount
    average_inventory: Amount | None = None
    average_receivables: Amount | None = None
    average_payables: Amount | None = None
    credit_sales: Amount | None = None
    credit_purchases: Amount | None = None
    cost_of_sales: Amount | None = None
    overdue_receivables: Amount | None = None
    overdue_payables: Amount | None = None

    @model_validator(mode="after")
    def coherent(self):
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("Début et fin de période nécessaires ensemble")
        if self.period_start and self.period_end < self.period_start:
            raise ValueError("Période BFR inversée")
        return self


class ProjectReceipt(Contract):
    period: date
    amount: Amount
    included_in_receipts: bool
    justification: Note


class Collateral(Contract):
    description: str
    declared_value: Amount
    valuation_date: date | None = None
    known_charges: Amount | None = None
    verification: Note | None = None
    realization_limits: list[Note] = Field(default_factory=list)


class BusinessDetails(CommonDetails):
    counterparties: list[Counterparty] = Field(default_factory=list)
    customer_receipts_complete: bool = False
    seasonality: Note | None = None
    dependencies: list[Note] = Field(default_factory=list)
    accounting: list[AccountingPeriod] = Field(default_factory=list)
    accounting_comparison: Literal["same_duration", "daily_rate"] = "same_duration"
    working_capital_applicable: bool | None = None
    working_capital: WorkingCapital | None = None
    equity: SignedAmount | None = None
    off_balance_commitments: Amount | None = None
    tax_arrears: Amount | None = None
    social_arrears: Amount | None = None
    project_receipts: list[ProjectReceipt] = Field(default_factory=list)
    collateral_applicable: bool | None = None
    collateral: list[Collateral] = Field(default_factory=list)

    @model_validator(mode="after")
    def accounting_periods(self):
        for previous, current in zip(self.accounting, self.accounting[1:]):
            if current.start <= previous.end:
                raise ValueError("Périodes comptables chevauchantes ou non croissantes")
        return self
