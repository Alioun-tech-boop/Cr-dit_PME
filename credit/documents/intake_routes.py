from copy import deepcopy
import json
import asyncio
from threading import BoundedSemaphore

from fastapi import Depends, HTTPException, Request, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from credit.documents.intake_contracts import NewSubmission, EditPages, ReviewInput, StructuredInput
from credit.documents import intake_service as service
from credit.documents.isolation import Runner
from credit.documents.policy import configuration
from credit.persistence import (
    SubmissionRecord,
    SourceRecord,
    DocumentRun,
    DocumentEvent,
    StructuredRecord,
    ReviewRecord,
    identifier,
)


def view(record):
    return {
        "id": record.id,
        "case_id": record.case_id,
        "case_kind": record.case_kind,
        **deepcopy(record.data),
    }


async def bounded_body(request, maximum, timeout_seconds=90):
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError:
            raise HTTPException(400, "invalid_content_length") from None
        if size < 0:
            raise HTTPException(400, "invalid_content_length")
        if size > maximum:
            raise HTTPException(413, "file_size_limit")
    payload = bytearray()
    try:
        async with asyncio.timeout(timeout_seconds):
            async for chunk in request.stream():
                if len(payload) + len(chunk) > maximum:
                    raise HTTPException(413, "file_size_limit")
                payload.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, "upload_timeout") from None
    if not payload:
        raise HTTPException(400, "empty_body")
    if length is not None and int(length) != len(payload):
        raise HTTPException(400, "incomplete_body")
    return bytes(payload)


def register_intake_routes(app, db, get_case):
    policy, quality = configuration()
    app.state.scan_runner = Runner(policy["limits"])
    upload_slots = BoundedSemaphore(policy["limits"]["concurrency"])

    @app.get("/documents/policies")
    def policies():
        p, q = configuration()
        return {
            **p,
            "quality": q,
            "notice": "Contrôles de dépôt et de lisibilité, jamais une authentification.",
        }

    def register(kind):
        base = f"/{kind}/{{case_id}}"
        path = base + "/submissions"

        def find(session, case_id, submission_id, lock=False):
            get_case(session, kind, case_id)
            query = select(SubmissionRecord).where(
                SubmissionRecord.id == submission_id,
                SubmissionRecord.case_id == case_id,
                SubmissionRecord.case_kind == kind,
            )
            if lock:
                query = query.with_for_update()
            record = session.scalar(query)
            if not record or (
                not session.info["actor"].reviewer
                and record.data.get("visibility", "analyst") != "applicant"
                and record.data.get("created_by") != session.info["actor"].id
            ):
                raise HTTPException(404, "Pièce introuvable")
            return record

        def find_run(session, record, run_id):
            run = session.get(DocumentRun, run_id)
            if not run or run.submission_id != record.id:
                raise HTTPException(404, "Traitement introuvable")
            return run

        @app.post(base + "/structured-inputs", status_code=201, name=f"{kind}_structured")
        def structured(case_id: str, body: StructuredInput, session: Session = Depends(db)):
            get_case(session, kind, case_id)
            p, _ = configuration()
            rule = p["rules"].get(body.document_type)
            if not rule or rule["policy"] != "structured_required" or kind not in rule["profiles"]:
                raise HTTPException(422, "Type non structuré ou noyau incompatible")
            missing = [key for key in rule.get("required_fields", []) if key not in body.fields]
            if missing:
                raise HTTPException(422, {"code": "structured_fields_required", "fields": missing})
            if len(json.dumps(body.model_dump(mode="json"))) > 65536:
                raise HTTPException(413, "Saisie trop volumineuse")
            record = StructuredRecord(
                id=identifier(),
                case_id=case_id,
                case_kind=kind,
                data={
                    **body.model_dump(mode="json"),
                    "created_at": service.stamp(),
                    "actor_id": session.info["actor"].id,
                    "policy_version": p["version"],
                    "status": "declared_unverified",
                    "missing_values": [
                        key
                        for key in rule.get("required_fields", [])
                        if body.fields[key] is None or body.fields[key] == ""
                    ],
                    "ready_for_scoring": False,
                },
            )
            session.add(record)
            service.commit(session)
            return {"id": record.id, **record.data}

        @app.get(base + "/structured-inputs/{input_id}", name=f"{kind}_read_structured")
        def read_structured(case_id: str, input_id: str, session: Session = Depends(db)):
            get_case(session, kind, case_id)
            record = session.get(StructuredRecord, input_id)
            if not record or record.case_id != case_id or record.case_kind != kind:
                raise HTTPException(404, "Saisie introuvable")
            return {"id": record.id, **record.data}

        @app.post(path, status_code=201, name=f"{kind}_new_submission")
        def create(case_id: str, body: NewSubmission, session: Session = Depends(db)):
            case = get_case(session, kind, case_id)
            p, q = configuration()
            return view(service.create_submission(session, case, session.info["actor"], body, p, q))

        @app.get(path, name=f"{kind}_list_submissions")
        def listing(
            case_id: str,
            session: Session = Depends(db),
            limit: int = Query(100, ge=1, le=250),
            offset: int = Query(0, ge=0, le=100000),
        ):
            get_case(session, kind, case_id)
            return [
                view(record)
                for record in session.scalars(
                    select(SubmissionRecord)
                    .where(SubmissionRecord.case_id == case_id, SubmissionRecord.case_kind == kind)
                    .order_by(SubmissionRecord.id)
                    .offset(offset)
                    .limit(limit)
                ).all()
                if session.info["actor"].reviewer
                or record.data.get("visibility") == "applicant"
                or record.data.get("created_by") == session.info["actor"].id
            ]

        @app.get(path + "/{submission_id}", name=f"{kind}_submission")
        def read(case_id: str, submission_id: str, session: Session = Depends(db)):
            return view(find(session, case_id, submission_id))

        @app.post(path + "/{submission_id}/sources", status_code=201, name=f"{kind}_source")
        async def upload(
            case_id: str, submission_id: str, request: Request, session: Session = Depends(db)
        ):
            from starlette.concurrency import run_in_threadpool

            record = find(session, case_id, submission_id, True)
            service.draft(record)
            if not upload_slots.acquire(blocking=False):
                raise HTTPException(429, "upload_busy", headers={"Retry-After": "5"})
            try:
                payload = await bounded_body(
                    request,
                    record.data["limits"]["max_file_bytes"],
                    record.data["limits"]["timeout_seconds"],
                )
                return view(
                    await run_in_threadpool(
                        service.add_source,
                        session,
                        record,
                        session.info["actor"],
                        payload,
                        app.state.scan_runner,
                    )
                )
            finally:
                upload_slots.release()

        @app.put(path + "/{submission_id}/pages", name=f"{kind}_edit_pages")
        def edit(case_id: str, submission_id: str, body: EditPages, session: Session = Depends(db)):
            record = find(session, case_id, submission_id, True)
            return view(service.edit_pages(session, record, session.info["actor"], body))

        @app.post(path + "/{submission_id}/confirm", name=f"{kind}_confirm")
        def confirm(case_id: str, submission_id: str, session: Session = Depends(db)):
            record = find(session, case_id, submission_id, True)
            return view(
                service.confirm(session, record, session.info["actor"], app.state.scan_runner)
            )

        @app.post(path + "/{submission_id}/process", name=f"{kind}_process")
        def process(case_id: str, submission_id: str, session: Session = Depends(db)):
            record = find(session, case_id, submission_id, True)
            return view(
                service.process(session, record, session.info["actor"], app.state.scan_runner)
            )

        @app.post(path + "/{submission_id}/cancel", name=f"{kind}_cancel")
        def cancel(case_id: str, submission_id: str, session: Session = Depends(db)):
            record = find(session, case_id, submission_id)
            from credit.security.access import require_staff

            require_staff(session.info["actor"])
            if not app.state.scan_runner.cancel(record.id):
                raise HTTPException(409, "Aucun traitement actif dans ce processus")
            service.audit(session, record, session.info["actor"], "cancellation_requested", {})
            service.commit(session)
            return {"id": record.id, "status": "cancellation_requested"}

        @app.post(path + "/{submission_id}/reopen", name=f"{kind}_reopen")
        def reopen(case_id: str, submission_id: str, session: Session = Depends(db)):
            record = find(session, case_id, submission_id, True)
            data = deepcopy(record.data)
            if data["processing_status"] == "running":
                raise HTTPException(409, "Traitement en cours")
            data.update(
                deposit_status="draft",
                processing_status="pending",
                ocr_status="pending",
                review_status="pending",
                revision=data["revision"] + 1,
                quality_status="pending",
                latest_run_id=None,
            )
            record.data = data
            service.audit(
                session, record, session.info["actor"], "reopened", {"revision": data["revision"]}
            )
            service.commit(session)
            return view(record)

        @app.get(path + "/{submission_id}/pages/{page_id}/image", name=f"{kind}_preview")
        def preview(case_id: str, submission_id: str, page_id: str, session: Session = Depends(db)):
            record = find(session, case_id, submission_id)
            page = next((p for p in record.data["pages"] if p["id"] == page_id), None)
            if not page:
                raise HTTPException(404, "Page introuvable")
            result = service.run_worker(
                app.state.scan_runner,
                "preview",
                {"pages": [page]},
                service.sources_for(session, record, [page]),
            )
            return Response(
                result["preview_png"],
                media_type="image/png",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )

        @app.get(path + "/{submission_id}/sources/{source_id}", name=f"{kind}_original")
        def source(
            case_id: str, submission_id: str, source_id: str, session: Session = Depends(db)
        ):
            record = find(session, case_id, submission_id)
            item = session.get(SourceRecord, source_id)
            if not item or item.submission_id != record.id:
                raise HTTPException(404, "Source introuvable")
            return Response(
                item.payload,
                media_type=item.media_type,
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Disposition": 'attachment; filename="original"',
                },
            )

        @app.get(path + "/{submission_id}/runs/{run_id}", name=f"{kind}_run")
        def read_run(case_id: str, submission_id: str, run_id: str, session: Session = Depends(db)):
            record = find(session, case_id, submission_id)
            run = find_run(session, record, run_id)
            reviews = session.scalars(
                select(ReviewRecord)
                .where(ReviewRecord.run_id == run.id)
                .order_by(ReviewRecord.created_at)
                .limit(250)
            ).all()
            return {
                "id": run.id,
                "submission_id": record.id,
                **run.data,
                "reviews": [{"id": r.id, "actor_id": r.actor_id, **r.data} for r in reviews],
                "authenticity_status": "not_assessed",
                "ready_for_scoring": False,
            }

        @app.get(path + "/{submission_id}/runs/{run_id}/pages/{page_id}", name=f"{kind}_run_page")
        def run_page(
            case_id: str,
            submission_id: str,
            run_id: str,
            page_id: str,
            session: Session = Depends(db),
        ):
            record = find(session, case_id, submission_id)
            run = find_run(session, record, run_id)
            index = next((i for i, p in enumerate(run.data["pages"]) if p["id"] == page_id), None)
            if index is None:
                raise HTTPException(404, "Page introuvable")
            result = service.run_worker(
                app.state.scan_runner,
                "render_run",
                {"page_index": index},
                {"input": {"payload": run.derivative_pdf}},
            )
            return Response(
                result["preview_png"],
                media_type="image/png",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )

        @app.post(
            path + "/{submission_id}/runs/{run_id}/reviews", status_code=201, name=f"{kind}_review"
        )
        def review(
            case_id: str,
            submission_id: str,
            run_id: str,
            body: ReviewInput,
            session: Session = Depends(db),
        ):
            record = find(session, case_id, submission_id, True)
            run = find_run(session, record, run_id)
            return service.review(
                session,
                record,
                run,
                session.info["actor"],
                body.decisions,
                body.regions,
                body.expected_review_revision,
            )

        @app.get(path + "/{submission_id}/events", name=f"{kind}_events")
        def events(
            case_id: str,
            submission_id: str,
            session: Session = Depends(db),
            limit: int = Query(100, ge=1, le=250),
            offset: int = Query(0, ge=0, le=100000),
        ):
            record = find(session, case_id, submission_id)
            items = session.scalars(
                select(DocumentEvent)
                .where(DocumentEvent.submission_id == record.id)
                .order_by(DocumentEvent.created_at)
                .offset(offset)
                .limit(limit)
            ).all()
            return [
                {
                    "id": e.id,
                    "actor_id": e.actor_id,
                    "action": e.action,
                    "data": e.data,
                    "created_at": e.created_at,
                }
                for e in items
            ]

    register("individuals")
    register("businesses")
