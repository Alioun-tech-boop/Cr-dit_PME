"""Extraction en amont des noyaux financiers ; aucune sélection de candidats."""

from credit_pdf.engine import extract_pdf

from credit.persistence import DocumentRecord


def extract_and_store(session, case, payload, document_type, role, period, ocr):
    result = extract_pdf(payload, document_type=document_type, ocr=ocr, lang="fra")
    record = DocumentRecord(
        case_id=case.id,
        case_kind=case.kind,
        document_type=document_type,
        role=role,
        period=period,
        document_sha256=result["document_sha256"],
        original_pdf=payload,
        extraction=result,
    )
    session.add(record)
    session.commit()
    return record
