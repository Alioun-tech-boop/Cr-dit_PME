"""Compatibilité des lectures v0.1 ; le dépôt direct a été retiré au profit des brouillons."""

from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session
from credit.persistence import DocumentRecord


def test_catalog(client):
    response = client.get("/documents/catalog")
    assert response.status_code == 200
    assert len(response.json()) == 132
    assert response.headers["cache-control"] == "no-store"


def test_direct_upload_cannot_bypass_scan_policy(client, individual):
    case_id = client.post("/individuals", json=individual).json()["id"]
    response = client.post(
        f"/individuals/{case_id}/documents",
        content=Path("modules/credit_pme_pdf/examples/pdf/payslip_detail.pdf").read_bytes(),
        headers={"content-type": "application/pdf"},
    )
    assert response.status_code == 410
    assert client.get(f"/individuals/{case_id}/documents").json() == []


def test_historical_documents_still_readable_and_protected(client, individual):
    case_id = client.post("/individuals", json=individual).json()["id"]
    with Session(client.app.state.engine) as session:
        record = DocumentRecord(
            case_id=case_id,
            case_kind="individuals",
            document_type="payslip",
            role="historical",
            period=date(2026, 10, 1),
            document_sha256="0" * 64,
            original_pdf=b"old-synthetic",
            extraction={"ready_for_scoring": False, "warnings": ["historical_unverified"]},
        )
        session.add(record)
        session.commit()
        document_id = record.id
    path = f"/individuals/{case_id}/documents/{document_id}"
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["extraction"]["warnings"] == ["historical_unverified"]
    assert client.get(path, headers={"Authorization": "Bearer synthetic-b"}).status_code == 404
    assert client.get(f"/analyses/{document_id}").status_code == 404
