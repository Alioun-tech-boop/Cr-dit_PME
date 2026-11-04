from datetime import date
from decimal import Decimal

from pydantic import Field

from credit.shared.contracts import Contract
from credit.individuals.results import IndividualPeriodResult
from credit.businesses.results import BusinessPeriodResult
from credit.shared.scoring import ScoringResult


class FinancialFindings(Contract):
    deficit_periods: list[date]
    negative_balance_periods: list[date]
    minimum_balance: Decimal | None
    minimum_balance_date: date | None
    income_variability_cv: Decimal | None = None
    observations: list[str]


class AnalysisResult(Contract):
    status: str
    analysis_type: str
    periods: list[IndividualPeriodResult] | list[BusinessPeriodResult]
    financial_findings: FinancialFindings
    documentary_quality: dict[str, object]
    information_requested: list[str]
    assumptions: dict[str, object]
    scoring: ScoringResult = Field(default_factory=ScoringResult)
    recommendation: str | None = None
    lender_decision: str | None = None
