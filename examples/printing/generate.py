"""Exemples exclusivement synthétiques, générés sans recalcul dans les gabarits."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from credit.printing.presentation import build_presentation
from credit.printing.contracts import PrintRequest
from credit.printing.isolation import render_isolated
from credit.assessment.engines import IndividualAnalysisEngine
from credit.assessment.policy import load_policy
from credit.assessment.simulation import prepare_simulation, SimulationSpec
from credit.assessment.reporting import compare_financial
from credit.individuals.contracts import IndividualCase

ROOT = Path(__file__).parent
INPUT = ROOT.parent / "assessments"


def load(name):
    case = json.loads((INPUT / (name + ".json")).read_text())
    case["record_details"] = {
        "address": "Adresse fictive, secteur Exemple, Ouagadougou",
        "telephone": "+226 00 00 00 00",
        "email": "synthese@example.invalid",
        "applicant_comments": "Déclaration synthétique : étude des échéances, aucune donnée réelle.",
        "internal_observations": "Observation interne synthétique, absente de toute version demandeur.",
    }
    if name.startswith("business"):
        case["record_details"].update(
            representatives=[{"name": "Aïssata Société Exemple", "role": "Gérante"}],
            rccm="RCCM-SYNTHETIQUE",
            ifu="IFU-SYNTHETIQUE",
        )
    return case


if __name__ == "__main__":
    individual = load("individual_control")
    individual["missing_information"] = []
    (ROOT / "individual_complete.json").write_text(
        json.dumps(individual, ensure_ascii=False, indent=2) + "\n"
    )
    missing = load("individual_incomplete")
    (ROOT / "individual_missing.json").write_text(
        json.dumps(missing, ensure_ascii=False, indent=2) + "\n"
    )
    business = load("business_profitable_cash_tension")
    (ROOT / "business_tables.json").write_text(
        json.dumps(business, ensure_ascii=False, indent=2) + "\n"
    )
    long = load("individual_control")
    long["name"] = "Élodie Françoise Ouedraogo — dossier synthétique à nom long " + (
        "Famille Exemple " * 15
    )
    long["record_details"]["applicant_comments"] = (
        "Commentaire synthétique long : les revenus, les charges et les pièces restent à rapprocher. "
        * 75
    ) + " FIN DU COMMENTAIRE LONG."
    (ROOT / "individual_long.json").write_text(
        json.dumps(long, ensure_ascii=False, indent=2) + "\n"
    )
    ind_report = json.loads((INPUT / "individual_control.report.json").read_text())
    biz_report = json.loads((INPUT / "business_profitable_cash_tension.report.json").read_text())
    engine = IndividualAnalysisEngine()
    case = IndividualCase.model_validate(individual)
    policy = load_policy("individuals-illustrative-v1", "individuals", "demonstration", "synthetic")
    spec = SimulationSpec(kind="lower_amount", principal="192000")
    prepared = prepare_simulation(case, spec, policy)
    sim_report = engine.analyze(
        prepared["case"], policy, "demonstration", include_suggestions=False
    ).model_dump(mode="json")
    sim_report["comparisons"] = [
        {
            "kind": spec.kind,
            "terms": prepared["terms"],
            **compare_financial(engine.calculate(case), engine.calculate(prepared["case"])),
        }
    ]
    jobs = [
        ("individual_fields", individual, "individuals", "complete_file", None, "applicant"),
        ("individual_incomplete", missing, "individuals", "household_budget", None, "applicant"),
        (
            "individual_summary",
            individual,
            "individuals",
            "analysis_summary",
            ind_report,
            "analyst",
        ),
        ("business_financial", business, "businesses", "financial_declaration", None, "applicant"),
        ("business_report", business, "businesses", "analysis_report", biz_report, "analyst"),
        ("improvement_plan", business, "businesses", "improvement_plan", biz_report, "analyst"),
        ("individual_long", long, "individuals", "identification", None, "applicant"),
        (
            "simulation",
            prepared["case"].model_dump(mode="json"),
            "individuals",
            "simulation_report",
            sim_report,
            "analyst",
        ),
        (
            "applicant_analysis",
            individual,
            "individuals",
            "analysis_report",
            ind_report,
            "applicant",
        ),
    ]
    manifest = []
    for name, data, core, template, report, audience in jobs:
        model = build_presentation(
            data,
            core,
            PrintRequest(template_id=template, audience=audience),
            {
                "Dossier": "SYNTHETIQUE-" + name,
                "Édition": "EXEMPLE-" + name,
                "Date d’édition": "4 novembre 2026",
                "Devise": "XOF / FCFA",
                "Version du modèle": "print-1.0.0",
            },
            [],
            report,
            parent=ind_report if name == "simulation" else None,
            simulation=spec.model_dump(mode="json") if name == "simulation" else None,
        )
        html, pdf = render_isolated(model)
        (ROOT / (name + ".html")).write_text(html)
        (ROOT / (name + ".pdf")).write_bytes(pdf)
        manifest.append(
            {
                "name": name,
                "template": template,
                "core": core,
                "audience": audience,
                "bytes": len(pdf),
            }
        )
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("9 PDF et 9 aperçus HTML générés dans examples/printing/.")
