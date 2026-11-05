from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess

from fastapi import HTTPException
from sqlalchemy import select, func
import os
from credit.security.files import antimalware
from sqlalchemy.orm.exc import StaleDataError
from credit_pdf.review import apply_review

from credit.documents.isolation import WorkerError
from credit.persistence import (
    DocumentEvent,
    DocumentRun,
    SourceRecord,
    SubmissionRecord,
    StructuredRecord,
    ReviewRecord,
    identifier,
)


PIPELINE_VERSION = "scan-pipeline-1"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def commit(session):
    try:
        session.commit()
    except StaleDataError:
        session.rollback()
        raise HTTPException(409, "Le dossier documentaire a été modifié ; rechargez-le.") from None


def audit(session, submission, actor, action, detail):
    session.add(
        DocumentEvent(
            submission_id=submission.id, actor_id=actor.id, action=action, data=deepcopy(detail)
        )
    )


def create_submission(session, case, actor, body, policy, quality, idempotency_key=None):
    if idempotency_key:
        for previous in session.scalars(
            select(SubmissionRecord).where(SubmissionRecord.case_id == case.id)
        ):
            if (
                previous.data.get("_operation_key") == idempotency_key
                and previous.data.get("created_by") == actor.id
            ):
                if previous.data.get("_request") != body.model_dump(mode="json"):
                    raise HTTPException(409, "Clé de dépôt incompatible")
                return previous
    if body.visibility == "analyst" and not actor.reviewer:
        raise HTTPException(403, "Classification interne réservée aux analystes")
    if session.scalar(
        select(func.count())
        .select_from(SubmissionRecord)
        .where(SubmissionRecord.case_id == case.id)
    ) >= int(os.getenv("CREDIT_MAX_DOCUMENTS_PER_CASE", "500")):
        raise HTTPException(429, "Quota de pièces atteint")
    rule = policy["rules"].get(body.document_type)
    if not rule or case.kind not in rule["profiles"]:
        raise HTTPException(422, "Type documentaire incompatible avec ce noyau")
    if rule["policy"] == "structured_required":
        structured = (
            session.get(StructuredRecord, body.supporting_structured_id)
            if body.supporting_structured_id
            else None
        )
        if (
            not structured
            or structured.case_id != case.id
            or structured.case_kind != case.kind
            or structured.data["document_type"] != body.document_type
        ):
            raise HTTPException(
                409,
                "structured_required : saisissez ou importez les champs structurés avant de joindre un justificatif.",
            )
    elif body.supporting_structured_id:
        raise HTTPException(422, "Rattachement structuré réservé à structured_required")
    if body.exception_reason and (
        not rule["native_exception_allowed"] or not actor.native_exception
    ):
        raise HTTPException(403, "Habilitation nécessaire pour une exception de PDF natif")
    data = {
        **body.model_dump(mode="json"),
        "policy_version": policy["version"],
        "policy": deepcopy(rule),
        "limits": deepcopy(policy["limits"]),
        "quality_config": deepcopy(quality),
        "created_at": stamp(),
        "processing_version": PIPELINE_VERSION,
        "created_by": actor.id,
        "visibility": body.visibility,
        "revision": 1,
        "pages": [],
        "source_bytes": 0,
        "deposit_status": "draft",
        "quality_status": "pending",
        "processing_status": "pending",
        "ocr_status": "pending",
        "review_status": "pending",
        "authenticity_status": "not_assessed",
        "ready_for_scoring": False,
        "latest_run_id": None,
        "exception": {"actor_id": actor.id, "reason": body.exception_reason, "date": stamp()}
        if body.exception_reason
        else None,
    }
    if idempotency_key:
        data.update(_operation_key=idempotency_key, _request=body.model_dump(mode="json"))
    record = SubmissionRecord(id=identifier(), case_id=case.id, case_kind=case.kind, data=data)
    session.add(record)
    session.flush()
    audit(
        session,
        record,
        actor,
        "created",
        {"document_type": body.document_type, "policy": rule, "exception": data["exception"]},
    )
    commit(session)
    return record


def draft(record):
    if record.data["deposit_status"] != "draft":
        raise HTTPException(
            409, "Dépôt confirmé : réouvrez une nouvelle révision avant modification."
        )


def run_worker(runner, operation, args, sources=None):
    try:
        return runner.run(operation, args, sources)
    except WorkerError as exc:
        code = str(exc)
        status = (
            429
            if code == "busy"
            else 413
            if code in {"file_size_limit", "pixel_limit_exceeded", "page_limit_exceeded"}
            else 504
            if code == "processing_timeout"
            else 422
        )
        raise HTTPException(status, code) from None


def enforce_scan(data, inspection):
    if data["policy"]["policy"] != "scan_required":
        return
    if data["exception"]:
        return
    invalid = [
        p["source_page"]
        for p in inspection["pages"]
        if p["image_coverage"] < data["quality_config"]["mixed_scan_min_coverage"]
        and p["quality"]["status"] != "blocked"
    ]
    if invalid:
        raise HTTPException(
            422,
            {
                "code": "scan_required",
                "pages": invalid,
                "message": "Fournissez une photographie, une image scanner ou un PDF numérisé. Le PDF natif ne sera pas rasterisé pour contourner cette politique.",
            },
        )


def add_source(session, record, actor, payload, runner, idempotency_key=None):
    sha = hashlib.sha256(payload).hexdigest()
    previous = record.data.get("_upload_keys", {}).get(idempotency_key) if idempotency_key else None
    if previous:
        if previous != sha:
            raise HTTPException(409, "Clé de fichier incompatible")
        return record
    draft(record)
    data = deepcopy(record.data)
    if data["source_bytes"] + len(payload) > data["limits"]["max_total_bytes"]:
        raise HTTPException(413, "Limite cumulée des originaux dépassée")
    malware = antimalware(payload)
    inspected = run_worker(
        runner,
        "inspect",
        {"quality": data["quality_config"], "limits": data["limits"]},
        {"input": {"payload": payload}},
    )
    inspected["malware"] = malware
    rule = data["policy"]
    allowed_formats = (
        rule.get("supporting_formats", ["image/jpeg", "image/png", "application/pdf"])
        if rule["policy"] == "structured_required"
        else rule["formats"]
    )
    if inspected["media_type"] not in allowed_formats:
        raise HTTPException(422, "format_not_allowed_for_document")
    enforce_scan(data, inspected)
    if len(data["pages"]) + len(inspected["pages"]) > data["limits"]["max_pages"]:
        raise HTTPException(413, "page_limit_exceeded")
    previous = {p["inspection"]["fingerprint"] for p in data["pages"]}
    source = SourceRecord(
        id=identifier(),
        submission_id=record.id,
        sha256=inspected["sha256"],
        media_type=inspected["media_type"],
        payload=payload,
        inspection=inspected,
    )
    data.setdefault("security_checks", []).append(
        {
            "source_id": source.id,
            "sha256": source.sha256,
            "format_status": "accepted",
            "antimalware": malware,
            "authenticity_status": "not_assessed",
        }
    )
    added = []
    for meta in inspected["pages"]:
        page = {
            "id": identifier(),
            "source_id": source.id,
            "source_page": meta["source_page"],
            "rotation": meta["initial_rotation"],
            "crop": [0, 0, 1, 1],
            "inspection": deepcopy(meta),
        }
        if meta["fingerprint"] in previous:
            page["inspection"]["quality"]["issues"].append(
                {
                    "code": "exact_duplicate",
                    "severity": "warning",
                    "message": "Cette page est identique à une page déjà ajoutée (empreinte du rendu).",
                }
            )
            if page["inspection"]["quality"]["status"] == "pass":
                page["inspection"]["quality"]["status"] = "warnings"
        previous.add(meta["fingerprint"])
        added.append(page)
    if idempotency_key:
        data["_upload_keys"] = {**data.get("_upload_keys", {}), idempotency_key: sha}
        data["_upload_revisions"] = {
            **data.get("_upload_revisions", {}),
            idempotency_key: data["revision"] + 1,
        }
    data["pages"] += added
    data["source_bytes"] += len(payload)
    data["revision"] += 1
    data["quality_status"] = quality_status([p["inspection"]["quality"] for p in data["pages"]])
    session.add(source)
    record.data = data
    audit(
        session,
        record,
        actor,
        "source_added",
        {
            "source_id": source.id,
            "sha256": source.sha256,
            "media_type": source.media_type,
            "pages": added,
            "revision": data["revision"],
        },
    )
    commit(session)
    return record


def edit_pages(session, record, actor, body):
    draft(record)
    data = deepcopy(record.data)
    if body.expected_revision != data["revision"]:
        raise HTTPException(409, "Révision périmée")
    current = {p["id"]: p for p in data["pages"]}
    ids = [p.id for p in body.pages]
    if len(ids) != len(set(ids)) or not set(ids) <= set(current):
        raise HTTPException(422, "Pages inconnues ou dupliquées")
    before = deepcopy(data["pages"])
    data["pages"] = [
        {**current[p.id], "rotation": p.rotation, "crop": list(p.crop)} for p in body.pages
    ]
    data["revision"] += 1
    data["quality_status"] = "pending"
    record.data = data
    audit(
        session,
        record,
        actor,
        "pages_edited",
        {"before": before, "after": data["pages"], "revision": data["revision"]},
    )
    commit(session)
    return record


def sources_for(session, record, pages=None):
    ids = {p["source_id"] for p in (pages if pages is not None else record.data["pages"])}
    sources = session.scalars(
        select(SourceRecord).where(
            SourceRecord.submission_id == record.id, SourceRecord.id.in_(ids)
        )
    ).all()
    if len(sources) != len(ids):
        raise HTTPException(409, "Source manquante")
    return {s.id: {"payload": s.payload, "inspection": s.inspection} for s in sources}


def quality_status(values):
    return (
        "blocked"
        if any(v["status"] == "blocked" for v in values)
        else "warnings"
        if any(v["status"] == "warnings" for v in values)
        else "pass"
    )


def confirm(session, record, actor, runner):
    draft(record)
    data = deepcopy(record.data)
    if not data["pages"]:
        raise HTTPException(409, "Ajoutez au moins une page")
    prepared = run_worker(
        runner,
        "prepare",
        {"pages": data["pages"], "quality": data["quality_config"], "limits": data["limits"]},
        sources_for(session, record),
    )
    data["quality_status"] = quality_status(prepared["quality"])
    data["quality_result"] = prepared["quality"]
    if data["quality_status"] == "blocked":
        record.data = data
        audit(session, record, actor, "quality_blocked", {"quality": prepared["quality"]})
        commit(session)
        raise HTTPException(422, {"code": "quality_blocked", "pages": prepared["quality"]})
    run = DocumentRun(
        id=identifier(),
        submission_id=record.id,
        derivative_pdf=prepared["derivative_pdf"],
        data={
            "stage": "preparation",
            "revision": data["revision"],
            "pages": deepcopy(data["pages"]),
            "created_at": stamp(),
            "processing_version": PIPELINE_VERSION,
            "mappings": prepared["mappings"],
            "quality": prepared["quality"],
            "derivative_sha256": hashlib.sha256(prepared["derivative_pdf"]).hexdigest(),
        },
    )
    session.add(run)
    data["deposit_status"] = "confirmed"
    data["confirmed_at"] = stamp()
    data["preparation_run_id"] = run.id
    record.data = data
    audit(
        session,
        record,
        actor,
        "confirmed",
        {"revision": data["revision"], "preparation_run_id": run.id},
    )
    commit(session)
    return record


def ocr_available():
    executable = shutil.which("tesseract")
    if not executable:
        return False, "tesseract_missing"
    try:
        result = subprocess.run(
            [executable, "--list-langs"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "tesseract_unavailable"
    return (
        (True, None)
        if result.returncode == 0 and "fra" in result.stdout.splitlines()[1:]
        else (False, "fra_missing")
    )


def process(session, record, actor, runner):
    data = deepcopy(record.data)
    if data["deposit_status"] != "confirmed":
        raise HTTPException(409, "Confirmez les pages avant traitement")
    if data["processing_status"] == "completed" and data.get("latest_run_id"):
        existing = session.get(DocumentRun, data["latest_run_id"])
        if existing and existing.data["revision"] == data["revision"]:
            return record
    if data["processing_status"] == "running":
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(data["processing_started_at"])
        ).total_seconds()
        if age < data["limits"]["timeout_seconds"] + 10:
            raise HTTPException(409, "Traitement déjà en cours")
    needs_ocr = any(
        p["inspection"]["classification"] in ["image_dominant", "mixed"]
        or p["inspection"]["native_text_chars"] < 60
        for p in data["pages"]
    )
    available, error = ocr_available() if needs_ocr else (True, None)
    if not available:
        data.update(
            processing_status="waiting_dependency",
            ocr_status="waiting_dependency",
            processing_error=error,
        )
        record.data = data
        audit(session, record, actor, "ocr_waiting", {"error": error, "language": "fra"})
        commit(session)
        return record
    data.update(
        processing_status="running",
        ocr_status="running" if needs_ocr else "not_required",
        processing_started_at=stamp(),
    )
    record.data = data
    audit(
        session,
        record,
        actor,
        "processing_started",
        {"revision": data["revision"], "language": "fra"},
    )
    commit(session)
    # Ne pas muter le dictionnaire JSON déjà commité (SQLAlchemy ne suit pas ses mutations internes).
    data = deepcopy(record.data)
    try:
        result = runner.run(
            "extract",
            {
                "pages": data["pages"],
                "quality": data["quality_config"],
                "document_type": data["document_type"],
                "task_key": record.id,
                "limits": data["limits"],
            },
            sources_for(session, record),
        )
    except WorkerError as exc:
        data.update(
            processing_status="failed",
            ocr_status="failed" if needs_ocr else "not_required",
            processing_error=str(exc),
        )
        record.data = data
        audit(session, record, actor, "processing_failed", {"error": str(exc)})
        commit(session)
        return record
    extraction = result["extraction"]
    failed = any(
        any(
            code in w
            for code in [
                "ocr_failed",
                "ocr_timeout",
                "ocr_unavailable",
                "ocr_languages_missing",
                "ocr_pixel_limit",
            ]
        )
        for w in extraction["warnings"]
    )
    for index, page in enumerate(data["pages"], 1):
        if page["inspection"]["native_text_chars"] < 60 and page["inspection"][
            "classification"
        ] in ["image_dominant", "mixed"]:
            if not any(e["page"] == index and e["method"] == "ocr" for e in extraction["evidence"]):
                failed = True
                extraction["warnings"].append(f"page_{index}:ocr_no_text_detected")
    run = DocumentRun(
        id=identifier(),
        submission_id=record.id,
        derivative_pdf=result["derivative_pdf"],
        data={
            "stage": "extraction",
            "revision": data["revision"],
            "created_at": stamp(),
            "processing_version": PIPELINE_VERSION,
            "pages": deepcopy(data["pages"]),
            "mappings": result["mappings"],
            "extraction": extraction,
            "quality": result["quality"],
            "derivative_sha256": hashlib.sha256(result["derivative_pdf"]).hexdigest(),
            "engine_version": extraction["engine_version"],
            "quality_config": data["quality_config"],
            "policy_version": data["policy_version"],
            "ocr_language": "fra",
        },
    )
    session.add(run)
    data.update(
        processing_status="failed" if failed else "completed",
        ocr_status="failed" if failed else "completed" if needs_ocr else "not_required",
        latest_run_id=run.id,
        review_status="pending",
        processing_error="ocr_failed" if failed else None,
    )
    record.data = data
    audit(
        session,
        record,
        actor,
        "processed",
        {
            "run_id": run.id,
            "revision": data["revision"],
            "processing_status": data["processing_status"],
        },
    )
    commit(session)
    return record


def review(session, record, run, actor, decisions, regions=None, expected_review_revision=0):
    if not actor.reviewer:
        raise HTTPException(403, "Habilitation de revue requise")
    if (
        run.data.get("revision") != record.data["revision"]
        or record.data.get("latest_run_id") != run.id
    ):
        raise HTTPException(409, "Extraction périmée : relancer et revoir la version courante")
    if expected_review_revision != record.data.get("review_revision", 0):
        raise HTTPException(409, "Revue périmée : recharger la révision courante")
    if run.data["stage"] != "extraction":
        raise HTTPException(409, "Aucune extraction à revoir")
    if len(json.dumps(decisions)) > 65536:
        raise HTTPException(413, "Revue trop volumineuse")
    previous = session.scalars(
        select(ReviewRecord)
        .where(ReviewRecord.run_id == run.id)
        .order_by(ReviewRecord.created_at.desc())
    ).first()
    initial = deepcopy(previous.data["extraction"] if previous else run.data["extraction"])
    from credit.documents.geometry import rectangle

    existing_ids = {
        item["id"] for item in initial["evidence"] + initial["tables"] + initial["form_fields"]
    }
    for region in regions or []:
        mapping = next((m for m in run.data["mappings"] if m["page_id"] == region.page_id), None)
        x0, y0, x1, y1 = region.bbox
        if (
            not mapping
            or region.id in existing_ids
            or not (
                0 <= x0 < x1 <= mapping["processing_width"]
                and 0 <= y0 < y1 <= mapping["processing_height"]
            )
        ):
            raise HTTPException(422, "Zone source invalide, inconnue ou dupliquée")
        existing_ids.add(region.id)
        initial["evidence"].append(
            {
                "id": region.id,
                "page": mapping["processing_page"],
                "bbox": list(region.bbox),
                "text": "",
                "method": "human_selected_region",
                "status": "source_reference_not_ocr",
                "actor_id": actor.id,
                "created_at": stamp(),
                "processing_version": PIPELINE_VERSION,
                "source": {
                    **mapping,
                    "bbox": rectangle(mapping["processing_to_source"], region.bbox),
                },
            }
        )
    try:
        reviewed = apply_review(initial, decisions, actor.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    item = ReviewRecord(
        id=identifier(),
        run_id=run.id,
        actor_id=actor.id,
        data={
            "decisions": deepcopy(decisions),
            "extraction": reviewed,
            "created_at": stamp(),
            "processing_version": PIPELINE_VERSION,
            "authenticity_status": "not_assessed",
            "ready_for_scoring": False,
        },
    )
    session.add(item)
    data = {**record.data, "review_revision": record.data.get("review_revision", 0) + 1}
    if record.data["latest_run_id"] == run.id:
        data["review_status"] = "partially_reviewed"
    record.data = data
    audit(
        session,
        record,
        actor,
        "reviewed",
        {"review_id": item.id, "run_id": run.id, "fields": list(decisions)},
    )
    commit(session)
    return {"id": item.id, "run_id": run.id, "actor_id": actor.id, **item.data}
