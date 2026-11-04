from decimal import Decimal, localcontext
from pydantic import BaseModel

from credit.shared.contracts import Amount, SignedAmount
from credit.shared.calculation import Context
from credit.assessment.contracts import DataUse, Indicator, RuleResult, SectionResult


def ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        return (numerator / denominator).quantize(Decimal("0.00000001"))


class AnalysisContext:
    def __init__(self, case, financial):
        self.case = case
        self.financial = financial
        self.details = case.analysis_details
        self.reader = Context(case, None)
        self.evidence = {e.id: e.model_dump(mode="json") for e in case.evidence}
        self.sections = {}

    def section(self, id, title, purpose="financial"):
        section = SectionResult(
            id=id, title=title, purpose=purpose, periods=[p.period for p in self.case.periods]
        )
        self.sections[id] = section
        return section

    def use(self, section, path):
        node = self.case
        for part in path.split("."):
            node = node[int(part)] if isinstance(node, list) else getattr(node, part)

        def visit(node, path, period=None, basis=None, unit="XOF", inherited_sources=None):
            if isinstance(node, (Amount, SignedAmount)):
                section.data_used.append(
                    DataUse(
                        path=path,
                        value=node.value,
                        state=node.state,
                        period=period,
                        basis=basis,
                        unit=unit,
                        sources=[self.evidence[k] for k in node.evidence_ids]
                        or (inherited_sources or []),
                    )
                )
            elif isinstance(node, BaseModel):
                period = getattr(node, "period", getattr(node, "end", period))
                basis = getattr(node, "basis", basis)
                if hasattr(node, "unit_multiplier"):
                    unit = {
                        Decimal(1): "XOF",
                        Decimal(1000): "milliers_XOF",
                        Decimal(1000000): "millions_XOF",
                    }.get(node.unit_multiplier, "unite_inconnue")
                refs = [
                    self.evidence[k] for k in getattr(node, "evidence_ids", [])
                ] or inherited_sources
                for name in type(node).model_fields:
                    visit(getattr(node, name), path + "." + name, period, basis, unit, refs)
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    visit(value, f"{path}.{i}", period, basis, unit, inherited_sources)
            else:
                section.data_used.append(
                    DataUse(
                        path=path,
                        value=node,
                        state="unknown" if node is None else "declared",
                        period=period,
                        basis=basis,
                        sources=inherited_sources or [],
                    )
                )

        visit(node, path)

    def money(self, section, path, value, optional=False, multiplier=Decimal(1)):
        if value is None or multiplier is None:
            section.missing_information.append(
                path
                + (
                    " : unité comptable à confirmer"
                    if multiplier is None
                    else " : valeur à fournir"
                )
            )
            return None
        amount = self.reader.amount(value, path, not optional)
        if amount is None:
            section.missing_information.append(
                path + " : valeur inconnue, contradictoire ou non validée"
            )
            return None
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            converted = amount * multiplier
        if abs(converted) >= Decimal("1e22"):
            section.missing_information.append(
                path + " : montant hors limites après conversion d’unité"
            )
            return None
        return converted

    def metric(self, section, id, value, unit, formula, period=None, paths=(), reason=None):
        section.indicators.append(
            Indicator(
                id=id,
                value=value,
                unit=unit,
                formula=formula,
                period=period,
                input_paths=list(paths) or [d.path for d in section.data_used],
                unavailable_reason=reason
                or ("Données ou dénominateur positif manquants" if value is None else None),
            )
        )
        return value

    def fact(
        self, section, id, metric, operator, threshold=Decimal(0), failure="defavorable", message=""
    ):
        value = next((v.value for v in reversed(section.indicators) if v.id == metric), None)
        operators = {
            "ge": lambda x: x >= threshold,
            "gt": lambda x: x > threshold,
            "le": lambda x: x <= threshold,
            "eq": lambda x: x == threshold,
        }
        passed = None if value is None else operators[operator](value)
        section.rules.append(
            RuleResult(
                id=id,
                indicator_id=metric,
                operator=operator,
                threshold=threshold,
                observed=value,
                passed=passed,
                explanation=message,
            )
        )
        if passed is False:
            section.alerts.append(message)
            if failure == "defavorable" or section.status == "favorable":
                section.status = failure
        return passed

    def finish(self, section, explanation):
        section.missing_information = sorted(set(section.missing_information))
        if section.alerts and section.status == "favorable":
            section.status = "vigilance"
        if section.missing_information and section.status != "defavorable":
            section.status = "incomplet"
        section.explanation = explanation
        return section


from credit.shared.normalization import effective_case  # noqa: E402, F401
