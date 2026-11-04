from fastapi import Depends, HTTPException, Query, Header
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from credit.persistence import PrintEdition, AssessmentRecord, PrintPublication, SubmissionRecord
from credit.printing.catalog import templates
from credit.printing.contracts import PrintRequest, Publication, ReturnedDocument
from credit.printing.render import html_document
from credit.printing import service

HTML_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def register_print_routes(app, db, get_case):
    def register(core):
        path = f"/{core}/{{case_id}}/print"

        @app.get(path + "/templates", name="print_templates_" + core)
        def catalog(case_id: str, session: Session = Depends(db)):
            get_case(session, core, case_id)
            return templates(core)

        @app.post(path + "/preview", response_class=HTMLResponse, name="print_preview_" + core)
        def preview(case_id: str, request: PrintRequest, session: Session = Depends(db)):
            case = get_case(session, core, case_id)
            try:
                model, _ = service.prepare(session, case, request, session.info["actor"])
                if len(model.model_dump_json()) > 3000000:
                    raise ValueError("print_input_limit")
                return HTMLResponse(html_document(model), headers=HTML_HEADERS)
            except (ValueError, OSError):
                raise HTTPException(
                    422, "Modèle, analyse ou configuration de rendu invalide"
                ) from None

        @app.post(path + "/preflight", name="print_preflight_" + core)
        def preflight(case_id: str, request: PrintRequest, session: Session = Depends(db)):
            case = get_case(session, core, case_id)
            try:
                model, _ = service.prepare(session, case, request, session.info["actor"])
                return {
                    "status": model.status,
                    "missing_information": model.missing_information,
                    "audience": model.audience,
                    "notices": model.notices,
                }
            except (ValueError, OSError):
                raise HTTPException(
                    422, "Modèle, analyse ou configuration de rendu invalide"
                ) from None

        @app.post(path + "/editions", status_code=201, name="print_generate_" + core)
        def generate(
            case_id: str,
            request: PrintRequest,
            session: Session = Depends(db),
            idempotency_key: str | None = Header(default=None, max_length=128),
        ):
            case = get_case(session, core, case_id)
            try:
                return service.view(
                    service.create_edition(
                        session, case, request, session.info["actor"], idempotency_key
                    )
                )
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, "Génération concurrente : réessayer") from None
            except (ValueError, OSError):
                session.rollback()
                raise HTTPException(
                    422, "Modèle, analyse ou configuration de rendu invalide"
                ) from None

        @app.get(path + "/editions", name="print_versions_" + core)
        def versions(
            case_id: str,
            session: Session = Depends(db),
            limit: int = Query(100, ge=1, le=250),
            offset: int = Query(0, ge=0, le=100000),
        ):
            get_case(session, core, case_id)
            query = select(PrintEdition).where(
                PrintEdition.case_id == case_id, PrintEdition.case_kind == core
            )
            if not session.info["actor"].reviewer:
                query = query.where(PrintEdition.audience == "applicant")
            items = session.scalars(
                query.order_by(PrintEdition.version.desc(), PrintEdition.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            latest = dict(
                ((t, a), v)
                for t, a, v in session.execute(
                    select(
                        PrintEdition.template_id,
                        PrintEdition.audience,
                        func.max(PrintEdition.version),
                    )
                    .where(PrintEdition.case_id == case_id)
                    .group_by(PrintEdition.template_id, PrintEdition.audience)
                )
            )
            latest_source = dict(
                ((t, a, aid), v)
                for t, a, aid, v in session.execute(
                    select(
                        PrintEdition.template_id,
                        PrintEdition.audience,
                        PrintEdition.assessment_id,
                        func.max(PrintEdition.version),
                    )
                    .where(PrintEdition.case_id == case_id)
                    .group_by(
                        PrintEdition.template_id, PrintEdition.audience, PrintEdition.assessment_id
                    )
                )
            )
            result = []
            for item in items:
                key = (item.template_id, item.audience)
                source = (*key, item.assessment_id)
                result.append(
                    {
                        **service.view(item),
                        "is_latest": item.version == latest[key],
                        "is_latest_for_source": item.version == latest_source[source],
                    }
                )
            return result

    register("individuals")
    register("businesses")

    def find(session, eid):
        item = session.get(PrintEdition, eid)
        if not item:
            raise HTTPException(404, "Édition introuvable")
        get_case(session, item.case_kind, item.case_id)
        service.audience_allowed(session.info["actor"], item.audience)
        return item

    @app.get("/print-editions/{edition_id}")
    def status(edition_id: str, session: Session = Depends(db)):
        return service.view(find(session, edition_id))

    @app.get("/print-editions/{edition_id}/model")
    def model(edition_id: str, session: Session = Depends(db)):
        return find(session, edition_id).data["presentation"]

    @app.post("/print-editions/{edition_id}/process")
    def process(edition_id: str, session: Session = Depends(db)):
        item = find(session, edition_id)
        service.process(session, item, session.info["actor"])
        return service.view(item)

    @app.get("/print-editions/{edition_id}/preview", response_class=HTMLResponse)
    def preview_edition(edition_id: str, session: Session = Depends(db)):
        item = find(session, edition_id)
        if item.status != "completed":
            raise HTTPException(409, "Édition non terminée")
        service.audit(session, item, session.info["actor"], "preview_opened")
        session.commit()
        return HTMLResponse(item.html_content, headers=HTML_HEADERS)

    @app.get("/print-editions/{edition_id}/pdf")
    def download(edition_id: str, session: Session = Depends(db)):
        item = find(session, edition_id)
        if item.status != "completed" or not item.pdf_content:
            raise HTTPException(409, "PDF indisponible : génération non terminée ou en échec")
        service.audit(
            session,
            item,
            session.info["actor"],
            "pdf_downloaded",
            {"pdf_sha256": item.data["pdf_sha256"]},
        )
        session.commit()
        return Response(
            item.pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="credit-pme-{item.id}-v{item.version}.pdf"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/print-editions/{edition_id}/events")
    def events(edition_id: str, session: Session = Depends(db)):
        item = find(session, edition_id)
        if not session.info["actor"].reviewer:
            raise HTTPException(403, "Historique interne réservé à la revue")
        from credit.persistence import PrintEvent

        return [
            {
                "id": e.id,
                "actor_id": e.actor_id,
                "action": e.action,
                "date": e.created_at,
                "data": e.data,
            }
            for e in session.scalars(
                select(PrintEvent)
                .where(PrintEvent.edition_id == item.id)
                .order_by(PrintEvent.created_at)
            ).all()
        ]

    @app.post("/assessments/{assessment_id}/print-publication", status_code=201)
    def publish(assessment_id: str, request: Publication, session: Session = Depends(db)):
        analysis = session.get(AssessmentRecord, assessment_id)
        if not analysis:
            raise HTTPException(404, "Analyse introuvable")
        get_case(session, analysis.case_kind, analysis.case_id)
        service.audience_allowed(session.info["actor"], "analyst")
        item = PrintPublication(
            assessment_id=analysis.id,
            actor_id=session.info["actor"].id,
            data=request.model_dump(mode="json"),
        )
        session.add(item)
        session.commit()
        return {
            "id": item.id,
            "assessment_id": analysis.id,
            "created_at": item.created_at,
            "author_id": item.actor_id,
            **item.data,
        }

    @app.post("/print-editions/{edition_id}/returned-documents", status_code=201)
    def returned(edition_id: str, request: ReturnedDocument, session: Session = Depends(db)):
        item = find(session, edition_id)
        submission = session.get(SubmissionRecord, request.submission_id)
        if (
            not submission
            or submission.case_id != item.case_id
            or submission.case_kind != item.case_kind
        ):
            raise HTTPException(404, "Pièce retournée introuvable dans ce dossier")
        service.audit(
            session,
            item,
            session.info["actor"],
            "returned_document_linked",
            request.model_dump(mode="json"),
        )
        session.commit()
        return {
            "edition_id": item.id,
            "submission_id": submission.id,
            "authenticity_status": "not_assessed",
        }
