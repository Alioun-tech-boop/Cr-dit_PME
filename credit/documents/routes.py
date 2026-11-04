from credit_pdf.catalog import public_catalog
from credit_pdf.engine import MAX_BYTES
from fastapi import Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from credit.documents.contracts import DocumentMetadata, DocumentResult
from credit.persistence import DocumentRecord


def metadata(record):
    return DocumentMetadata(
        **{
            key: getattr(record, key)
            for key in (
                "id",
                "case_id",
                "case_kind",
                "document_type",
                "role",
                "period",
                "document_sha256",
                "created_at",
            )
        }
    )


async def read_pdf(request):
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/pdf"
    ):
        raise HTTPException(415, "application_pdf_required")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            count = int(length)
        except ValueError:
            raise HTTPException(400, "invalid_content_length") from None
        if count < 0:
            raise HTTPException(400, "invalid_content_length")
        if count > MAX_BYTES:
            raise HTTPException(413, "file_too_large")
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > MAX_BYTES:
            raise HTTPException(413, "file_too_large")
        payload.extend(chunk)
    if not payload:
        raise HTTPException(400, "empty_pdf")
    if length is not None and len(payload) != int(length):
        raise HTTPException(400, "incomplete_body")
    return bytes(payload)


def register_document_routes(app, db, get_case):
    # Même accès local que les dossiers existants, sans serveur HTTP intermédiaire.

    @app.get("/documents/catalog")
    def catalog(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return public_catalog()

    def register(kind):
        path = f"/{kind}/{{case_id}}/documents"

        @app.post(path, name=f"legacy_upload_{kind}")
        def upload(case_id: str, session: Session = Depends(db)):
            get_case(session, kind, case_id)
            raise HTTPException(
                410,
                "Dépôt direct retiré : utilisez /submissions, gérez les pages puis confirmez et traitez.",
            )

        @app.get(path, response_model=list[DocumentMetadata], name=f"list_{kind}_documents")
        def list_documents(
            case_id: str,
            response: Response,
            session: Session = Depends(db),
            limit: int = Query(100, ge=1, le=250),
            offset: int = Query(0, ge=0, le=100000),
        ):
            get_case(session, kind, case_id)
            records = session.scalars(
                select(DocumentRecord)
                .where(DocumentRecord.case_id == case_id, DocumentRecord.case_kind == kind)
                .order_by(DocumentRecord.created_at)
                .offset(offset)
                .limit(limit)
            ).all()
            response.headers["Cache-Control"] = "no-store"
            return [metadata(record) for record in records]

        @app.get(
            path + "/{document_id}", response_model=DocumentResult, name=f"read_{kind}_document"
        )
        def get_document(
            case_id: str, document_id: str, response: Response, session: Session = Depends(db)
        ):
            get_case(session, kind, case_id)
            record = session.get(DocumentRecord, document_id)
            if record is None or record.case_id != case_id or record.case_kind != kind:
                raise HTTPException(404, "Document introuvable")
            response.headers["Cache-Control"] = "no-store"
            return DocumentResult(**metadata(record).model_dump(), extraction=record.extraction)

    register("individuals")
    register("businesses")
