"""Éditions privées immuables, modèle de présentation filtré et journal métier."""

import base64
from copy import deepcopy
from datetime import timezone
import hashlib
from io import BytesIO
import os
from pathlib import Path
from sqlalchemy import select, func
from fastapi import HTTPException
from PIL import Image

from credit.assessment.application import canonical_hash
from credit.persistence import (
    AssessmentRecord,
    CaseRecord,
    DocumentRecord,
    PrintEdition,
    PrintEvent,
    PrintPublication,
    SubmissionRecord,
    identifier,
    now,
)
from credit.printing.catalog import ANALYSIS_TEMPLATES
from credit.printing.contracts import Presentation
from credit.printing.presentation import build_presentation, french_date
from credit.printing.isolation import render_isolated


def audience_allowed(actor, audience):
    if audience == "analyst" and not actor.reviewer:
        raise HTTPException(403, "Version analyste réservée aux agents habilités à la revue")


def document_inventory(session, case, actor):
    results = []
    for s in session.scalars(
        select(SubmissionRecord).where(
            SubmissionRecord.case_id == case.id, SubmissionRecord.case_kind == case.kind
        )
    ).all():
        if (
            not actor.reviewer
            and s.data.get("visibility", "analyst") != "applicant"
            and s.data.get("created_by") != actor.id
        ):
            continue
        results.append(
            {
                "Référence": s.id,
                "Type": s.data["document_type"],
                "Période": s.data["period"],
                "Dépôt": s.data["deposit_status"],
                "Transcription": s.data["review_status"],
                "Authenticité": "Non évaluée",
            }
        )
    for s in session.scalars(
        select(DocumentRecord).where(
            DocumentRecord.case_id == case.id, DocumentRecord.case_kind == case.kind
        )
    ).all():
        if not actor.reviewer:
            continue
        results.append(
            {
                "Référence": s.id,
                "Type": s.document_type,
                "Période": s.period.isoformat(),
                "Transcription": "Extrait non contrôlé",
                "Authenticité": "Non évaluée",
            }
        )
    return results


def brand(model):
    model.platform_name = os.getenv("CREDIT_PRINT_PLATFORM_NAME", "Crédit PME")[:100]
    path = os.getenv("CREDIT_PRINT_LOGO_FILE")
    if path:
        # Chemin configuré par l’administrateur, jamais par le corps d’une requête.
        payload = Path(path).read_bytes()
        if len(payload) > 500000:
            raise ValueError("print_logo_limit")
        with Image.open(BytesIO(payload)) as image:
            if image.format not in {"PNG", "JPEG"} or image.width * image.height > 1000000:
                raise ValueError("print_logo_invalid")
            image.load()
            out = BytesIO()
            image.convert("RGB").save(out, format="PNG")
            model.logo_png = base64.b64encode(out.getvalue()).decode()
    return model


def prepare(session, case, request, actor, edition_id=None, version=0):
    audience_allowed(actor, request.audience)
    analysis = None
    if request.assessment_id:
        analysis = session.get(AssessmentRecord, request.assessment_id)
        if not analysis or analysis.case_id != case.id or analysis.case_kind != case.kind:
            raise HTTPException(404, "Analyse introuvable dans ce dossier")
    if request.template_id == "simulation_report" and (not analysis or not analysis.parent_id):
        raise ValueError("Le rapport de simulation exige une analyse de simulation historisée")
    if request.template_id in ANALYSIS_TEMPLATES and not analysis:
        # Brouillon explicite autorisé pour les rapports sans analyse, sauf simulation.
        snapshot = deepcopy(case.payload)
    else:
        snapshot = deepcopy(analysis.data["input_snapshot"] if analysis else case.payload)
    parent = (
        session.get(AssessmentRecord, analysis.parent_id)
        if analysis and analysis.parent_id
        else None
    )
    publication = (
        session.scalars(
            select(PrintPublication)
            .where(PrintPublication.assessment_id == analysis.id)
            .order_by(PrintPublication.created_at.desc(), PrintPublication.id.desc())
        ).first()
        if analysis
        else None
    )
    metadata = {
        "Dossier": case.id,
        "Noyau": "Particulier" if case.kind == "individuals" else "Entreprise / PME",
        "Édition": edition_id or "Aperçu non émis",
        "Version de l’édition": str(version),
        "Date d’édition": french_date(now()),
        "Langue": "fr",
        "Public": "Analyste / prêteur habilité" if request.audience == "analyst" else "Demandeur",
        "Analyse": analysis.id if analysis else "Non disponible / champs du dossier",
        "Date de l’analyse": french_date(analysis.created_at) if analysis else "Non disponible",
        "Instantané SHA256": canonical_hash(snapshot),
        "Version du modèle": "print-1.0.0",
        "Devise": "XOF / FCFA",
    }
    if request.audience == "analyst":
        metadata["Auteur de la génération"] = actor.id
        if analysis:
            metadata["Moteur"] = analysis.data["engine_version"]
            metadata["Règles / politique"] = str(analysis.data["result"].get("versions", {}))
    model = build_presentation(
        snapshot,
        case.kind,
        request,
        metadata,
        document_inventory(session, case, actor),
        analysis.data["result"] if analysis else None,
        publication.data if publication else {},
        parent.data["result"] if parent else None,
        analysis.data["simulation"] if analysis else None,
        analysis.data["human_validations"] if analysis else None,
    )
    if analysis and analysis.data["engine_version"] == "financial_analysis_v2":
        model.template_version = "print-financial-v2.0.0"
        model.metadata["Version du modèle"] = model.template_version
    model = brand(model)
    # Aucun instantané complet n'est transmis au renderer : seul ce contrat l'est.
    return model, {
        "input_snapshot": snapshot,
        "input_sha256": canonical_hash(snapshot),
        "case_updated_at": case.updated_at.replace(tzinfo=timezone.utc).isoformat(),
        "assessment_sha256": analysis.data["report_sha256"] if analysis else None,
        "publication_id": publication.id if publication else None,
        "engine_versions": deepcopy(analysis.data["result"].get("versions", {}))
        if analysis
        else {},
        "language": request.language,
        "template_version": model.template_version,
    }


def audit(session, item, actor, action, data=None):
    session.add(PrintEvent(edition_id=item.id, actor_id=actor.id, action=action, data=data or {}))


def create_edition(session, case, request, actor, idempotency_key=None):
    # Verrou par dossier et contrainte UNIQUE : deux requêtes n’émettent pas la même version.
    session.execute(select(CaseRecord.id).where(CaseRecord.id == case.id).with_for_update())
    if idempotency_key:
        audience_allowed(actor, request.audience)
        previous = session.scalars(
            select(PrintEdition).where(
                PrintEdition.case_id == case.id,
                PrintEdition.audience == request.audience,
                PrintEdition.data["idempotency_key"].as_string() == idempotency_key,
            )
        ).first()
        if previous:
            current = case.payload
            if request.assessment_id:
                analysis = session.get(AssessmentRecord, request.assessment_id)
                if not analysis or analysis.case_id != case.id:
                    raise HTTPException(404, "Analyse introuvable")
                current = analysis.data["input_snapshot"]
            if previous.data.get("request_sha256") != canonical_hash(
                request.model_dump(mode="json")
            ) or previous.data["input_sha256"] != canonical_hash(current):
                raise HTTPException(
                    409, "Clé d’idempotence réutilisée avec des données différentes"
                )
            return previous
    version = (
        session.scalar(
            select(func.max(PrintEdition.version)).where(
                PrintEdition.case_id == case.id,
                PrintEdition.template_id == request.template_id,
                PrintEdition.audience == request.audience,
            )
        )
        or 0
    ) + 1
    eid = identifier()
    model, private = prepare(session, case, request, actor, eid, version)
    item = PrintEdition(
        id=eid,
        case_id=case.id,
        case_kind=case.kind,
        template_id=request.template_id,
        audience=request.audience,
        version=version,
        assessment_id=request.assessment_id,
        status="pending",
        author_id=actor.id,
        data={
            **private,
            "idempotency_key": idempotency_key,
            "request_sha256": canonical_hash(request.model_dump(mode="json")),
            "presentation": model.model_dump(mode="json"),
            "pdf_sha256": None,
            "html_sha256": None,
            "error": None,
        },
    )
    session.add(item)
    session.flush()
    audit(session, item, actor, "generation_requested")
    session.commit()
    if request.generate_now:
        process(session, item, actor)
    return item


def process(session, item, actor):
    session.refresh(item, with_for_update=True)
    if item.status != "pending":
        raise HTTPException(
            409, "Cette édition n’est pas en attente ; créer une nouvelle version en cas d’échec"
        )
    item.status = "processing"
    audit(session, item, actor, "generation_started")
    session.commit()
    try:
        html, pdf = render_isolated(Presentation.model_validate(item.data["presentation"]))
        if not pdf or not html:
            raise ValueError("print_render_failed")
        item.pdf_content = pdf
        item.html_content = html
        item.data = {
            **item.data,
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
            "completed_at": now().isoformat(),
        }
        item.status = "completed"
        audit(session, item, actor, "generation_completed", {"pdf_sha256": item.data["pdf_sha256"]})
    except Exception as exc:
        code = (
            str(exc)
            if str(exc)
            in {
                "print_timeout",
                "print_busy",
                "print_input_limit",
                "print_output_limit",
                "print_page_limit",
            }
            else "print_render_failed"
        )
        item.pdf_content = None
        item.html_content = None
        item.status = "failed"
        item.data = {**item.data, "error": code}
        audit(session, item, actor, "generation_failed", {"code": code})
    session.commit()


def view(item):
    return {
        "id": item.id,
        "case_id": item.case_id,
        "case_kind": item.case_kind,
        "template_id": item.template_id,
        "audience": item.audience,
        "version": item.version,
        "assessment_id": item.assessment_id,
        "status": item.status,
        "created_at": item.created_at,
        "author_id": item.author_id,
        "document_status": item.data["presentation"]["status"],
        "missing_information": item.data["presentation"]["missing_information"],
        "template_version": item.data["template_version"],
        "input_sha256": item.data["input_sha256"],
        "pdf_sha256": item.data["pdf_sha256"],
        "html_sha256": item.data["html_sha256"],
        "error": item.data["error"],
    }
