"""Exemples purement synthétiques v2, sans API, base ou service d'IA."""

import json
from pathlib import Path
from credit.application import CONTRACTS
from credit.financial_v2.contracts import AnalysisRequest
from credit.financial_v2.engines import IndividualAnalysisEngine, BusinessAnalysisEngine
from credit.financial_v2.policy import load_policy
from credit.assessment.reporting import render_french
from credit.printing.contracts import PrintRequest
from credit.printing.presentation import build_presentation
from credit.printing.isolation import render_isolated

ROOT = Path("examples/financial_v2")


def main():
    for name, core in [
        ("individual_control", "individuals"),
        ("individual_incomplete", "individuals"),
        ("business_profitable_cash_tension", "businesses"),
        ("business_seasonal", "businesses"),
    ]:
        raw = json.loads(Path("examples/assessments/" + name + ".json").read_text())
        raw["analysis_details"]["funding"]["product_id"] = "unclassified"
        request = AnalysisRequest.model_validate(
            {
                "mode": "demonstration",
                "policy_id": core + "-illustrative-v2",
                "scenarios": [
                    {
                        "id": "income-drop-20",
                        "name": "Baisse hypothétique des flux de 20 %",
                        "revenue_drop": ".2",
                        "rationale": "Hypothèse synthétique illustrative, non validée comme norme",
                    }
                ],
                "reverse_tests": [
                    {"parameter": "revenue_drop", "lower": "0", "upper": ".5"},
                    {"parameter": "additional_instalment", "lower": "0", "upper": "150000"},
                ],
                "financing_candidates": [
                    {"principal": "240000", "months": 3},
                    {"principal": "240000", "months": 6},
                ],
            }
        )
        case = CONTRACTS[core].model_validate(raw)
        engine = IndividualAnalysisEngine() if core == "individuals" else BusinessAnalysisEngine()
        report = engine.analyze(
            case,
            load_policy(request.policy_id),
            request.mode,
            request.facts,
            request.scenarios,
            request.reverse_tests,
            request.financing_candidates,
        )
        for suffix, value in [
            ("case", raw),
            ("request", request.model_dump(mode="json")),
            ("report", report.model_dump(mode="json")),
        ]:
            (ROOT / (name + "." + suffix + ".json")).write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n"
            )
        (ROOT / (name + ".report.md")).write_text(render_french(report) + "\n")
        for template in ["analysis_summary"] + (
            ["analysis_report"] if name == "individual_control" else []
        ):
            model = build_presentation(
                raw,
                core,
                PrintRequest(template_id=template, audience="analyst"),
                {
                    "Dossier": name,
                    "Édition": "synthétique-v2",
                    "Date d’édition": "5 novembre 2026",
                    "Devise": "FCFA / XOF",
                    "Moteur": "financial_analysis_v2",
                },
                [],
                report.model_dump(mode="json"),
            )
            model.template_version = "print-financial-v2.0.0"
            html, pdf = render_isolated(model)
            (ROOT / (name + "." + template + ".pdf")).write_bytes(pdf)
            (ROOT / (name + "." + template + ".html")).write_text(html)
        print(name, len(report.sections), "sections", report.scoring["model_status"])


if __name__ == "__main__":
    main()
