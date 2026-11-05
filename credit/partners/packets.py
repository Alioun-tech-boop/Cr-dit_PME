"""Présentations destinées à la banque : sélection avant rendu, jamais simple masquage."""

from copy import deepcopy
import os
from fastapi import HTTPException
from credit.persistence import SourceRecord, SubmissionRecord
from credit.partners.models import PacketFile
from credit.partners.signing import canonical, digest
from credit.printing.contracts import Presentation, PrintRequest, Section, Table
from credit.printing.presentation import build_presentation, table_section
from credit.printing.isolation import render_isolated
from credit.persistence import identifier


def info(file):
    return {
        "id": file.id,
        "category": file.category,
        "name": file.name,
        "sha256": file.sha256,
        "size": file.size,
        "media_type": file.media_type,
        "source": file.metadata_json,
    }


def add_file(session, review, category, payload, media_type="application/pdf", metadata=None):
    maximum = 25_000_000
    if not payload or len(payload) > maximum:
        raise ValueError("Taille de document bancaire non admise")
    id = identifier()
    extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}.get(
        media_type, "bin"
    )
    file = PacketFile(
        id=id,
        review_id=review.id,
        category=category,
        name=category + "-" + id + "." + extension,
        media_type=media_type,
        sha256=digest(payload),
        size=len(payload),
        payload=payload,
        metadata_json=metadata or {},
    )
    session.add(file)
    return file


def lender_model(case, report, full):
    sections = [
        Section(
            title="Synthèse",
            paragraphs=[
                report["summary"],
                "Validation interne distincte de toute décision bancaire.",
            ],
        )
    ]
    sections.append(
        table_section("Conditions analysées, en FCFA / XOF", report["financing_conditions"])
    )
    sections.append(
        table_section("Situation financière, sans probabilité de défaut", report["financial_risk"])
    )
    sections.append(
        table_section(
            "Qualification conventionnelle",
            {
                k: report["scoring"].get(k)
                for k in [
                    "criteria_score",
                    "criteria_validation_status",
                    "qualification",
                    "mandatory_review",
                ]
            },
        )
    )
    if full:
        for s in report["sections"]:
            sections.append(
                Section(
                    title=s["title"],
                    paragraphs=[s["explanation"]]
                    + s["alerts"]
                    + ["À compléter : " + m for m in s["missing_information"]],
                    tables=[
                        Table(
                            columns=["Indicateur / période", "Valeur / unité", "Formule"],
                            rows=[
                                [
                                    i["id"] + " / " + str(i.get("period") or ""),
                                    str(i["value"] if i["value"] is not None else "Non calculable")
                                    + " "
                                    + i["unit"],
                                    i["formula"],
                                ]
                                for i in s["indicators"]
                            ],
                        )
                    ],
                )
            )
        sections.append(
            table_section(
                "Projections fournies, en FCFA / XOF", report["financial_calculations"]["periods"]
            )
        )
        sections.append(
            table_section("Scénarios et comparaisons autorisés", report.get("comparisons", []))
        )
        deep = report.get("deep_analysis", {})
        sections.append(
            table_section("Seuils de rupture, hypothèses bornées", deep.get("reverse_tests", []))
        )
        sections.append(
            table_section(
                "Variantes de financement",
                [
                    {k: v for k, v in c.items() if k != "input_snapshot"}
                    for c in deep.get("financing_variants", {}).get("variants", [])
                ],
            )
        )
    sections.append(
        Section(
            title="Informations manquantes et réserves méthodologiques",
            paragraphs=report["missing_information"] + report["assumptions"],
        )
    )
    sections.append(
        table_section(
            "Suggestions, sans engagement",
            [
                {
                    k: s[k]
                    for k in [
                        "problem",
                        "action",
                        "priority",
                        "recipient",
                        "prerequisites",
                        "simulated_effect",
                        "costs_and_limits",
                        "evidence_needed",
                    ]
                }
                for s in report["suggestions"]
            ],
        )
    )
    return Presentation(
        template_id="lender_report" if full else "analysis_summary",
        title="Rapport d’analyse destiné au prêteur" if full else "Synthèse destinée au prêteur",
        audience="analyst",
        status="Analyse incomplète" if report["missing_information"] else "Analyse disponible",
        metadata={
            "Dossier": case.id,
            "Édition": "paquet-bancaire",
            "Devise": "FCFA / XOF",
            "Moteur": report["engine_version"],
        },
        missing_information=report["missing_information"],
        notices=[
            "Aucun accord bancaire, remboursement garanti ou authenticité générale des pièces attestés."
        ],
        sections=sections,
        template_version="partner-packet-v1",
    )


def build(session, case, assessment, review, source_ids):
    snapshot = deepcopy(assessment.data["input_snapshot"])
    snapshot.get("record_details", {}).pop("internal_observations", None)
    files = []
    forms = [
        ("identification", "identification"),
        ("credit_request", "credit_request"),
        (
            "income_expenses" if case.kind == "individuals" else "financial_declaration",
            "declaration",
        ),
        ("household_budget" if case.kind == "individuals" else "cashflows", "budget"),
        ("debts", "debts"),
    ]
    for template, category in forms:
        model = build_presentation(
            snapshot,
            case.kind,
            PrintRequest(template_id=template, audience="applicant"),
            {"Dossier": case.id, "Édition": review.id, "Devise": "FCFA / XOF"},
            [],
        )
        _, pdf = render_isolated(model)
        files.append(
            add_file(
                session,
                review,
                category,
                pdf,
                metadata={
                    "assessment_id": assessment.id,
                    "case_version": case.lock_version,
                    "template": template,
                },
            )
        )
    for full in [True, False]:
        model = lender_model(case, assessment.data["result"], full)
        model.metadata["Édition"] = review.id
        _, pdf = render_isolated(model)
        files.append(
            add_file(
                session,
                review,
                "lender_report" if full else "analysis_summary",
                pdf,
                metadata={"assessment_id": assessment.id, "case_version": case.lock_version},
            )
        )
    for id in source_ids:
        source = session.get(SourceRecord, id)
        submission = session.get(SubmissionRecord, source.submission_id) if source else None
        if not submission or submission.case_id != case.id or submission.case_kind != case.kind:
            raise HTTPException(404, "Justificatif introuvable dans ce dossier")
        if submission.data.get("deposit_status") != "confirmed" or (
            submission.data.get("visibility") != "applicant"
            and submission.data.get("created_by") != case.owner_id
        ):
            raise HTTPException(409, "Pièce non confirmée ou réservée aux usages internes")
        if digest(source.payload) != source.sha256:
            raise HTTPException(409, "Intégrité de la source non confirmée")
        if sum(f.size for f in files) + len(source.payload) > int(
            os.getenv("CREDIT_PARTNER_MAX_PACKET_BYTES", "50000000")
        ):
            raise HTTPException(413, "Paquet documentaire trop volumineux")
        files.append(
            add_file(
                session,
                review,
                submission.data["document_type"],
                source.payload,
                source.media_type,
                {
                    "source_id": source.id,
                    "submission_id": submission.id,
                    "submission_revision": submission.lock_version,
                    "original_sha256": source.sha256,
                    "authenticity_status": "not_assessed",
                },
            )
        )
    inventory = Presentation(
        template_id="inventory",
        title="Inventaire documentaire approuvé",
        audience="analyst",
        status="Version figée soumise à revue",
        metadata={"Dossier": case.id, "Édition": review.id},
        missing_information=[],
        notices=[
            "Les originaux restent des fichiers distincts ; les signatures PDF éventuelles ne sont pas fusionnées."
        ],
        sections=[table_section("Documents proposés à la revue", [info(f) for f in files])],
    )
    _, pdf = render_isolated(inventory)
    files.append(add_file(session, review, "inventory", pdf))
    if sum(f.size for f in files) > int(os.getenv("CREDIT_PARTNER_MAX_PACKET_BYTES", "50000000")):
        raise HTTPException(413, "Paquet documentaire trop volumineux")
    manifest = {
        "schema_version": "approved-document-set-v1",
        "case_id": case.id,
        "case_kind": case.kind,
        "case_version": case.lock_version,
        "assessment_id": assessment.id,
        "analysis_sha256": assessment.data["report_sha256"],
        "engine_version": assessment.data["engine_version"],
        "files": [info(f) for f in files],
    }
    return manifest, digest(canonical(manifest))
