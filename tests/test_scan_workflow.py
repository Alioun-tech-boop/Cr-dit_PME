import io
import json
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from sqlalchemy.orm import Session
from credit.persistence import DocumentRun
from credit_pdf.engine import extract_pdf
from PIL import Image

from credit.documents.geometry import rectangle
from credit.documents.imaging import inspect, build, quality
from credit.documents.isolation import Runner, WorkerError
from credit.documents.policy import configuration

SCANS = Path("examples/scans")
PDFS = Path("modules/credit_pme_pdf/examples/pdf")


@pytest.fixture
def case_id(client, individual):
    return client.post("/individuals", json=individual).json()["id"]


def create(client, case_id, document_type="payslip", **extra):
    response = client.post(
        f"/individuals/{case_id}/submissions",
        json={"document_type": document_type, "role": "synthetic", "period": "2026-10-01", **extra},
    )
    assert response.status_code == 201, response.text
    return f"/individuals/{case_id}/submissions/" + response.json()["id"]


def add(client, path, filename="salary.png", payload=None):
    if payload is None:
        payload = (SCANS / filename).read_bytes()
    return client.post(
        path + "/sources", content=payload, headers={"Content-Type": "application/octet-stream"}
    )


def process(client, path):
    response = client.post(path + "/confirm")
    assert response.status_code == 200, response.text
    response = client.post(path + "/process")
    assert response.status_code == 200, response.text
    return response.json()


def test_policy_catalog_exact_coverage_and_mappings(client):
    data = client.get("/documents/policies").json()
    assert set(data["rules"]) == {p["id"] for p in client.get("/documents/catalog").json()}
    for key in [
        "identity_card",
        "payslip",
        "pension_statement",
        "rccm",
        "loan_balance",
        "data_authorization",
        "property_title",
    ]:
        assert data["rules"][key]["policy"] == "scan_required"
    for key in ["bank_statement", "annual_financials", "amortization_schedule", "proforma_invoice"]:
        assert data["rules"][key]["policy"] == "original_preferred"
    for key in ["credit_application", "household_budget", "historical_payments", "cash_forecast"]:
        assert data["rules"][key]["policy"] == "structured_required"
    assert data["quality"]["calibration"]


@pytest.mark.parametrize(
    "filename,media", [("salary.png", "image/png"), ("salary.jpg", "image/jpeg")]
)
def test_images_decode_from_content_not_mime(client, case_id, filename, media):
    path = create(client, case_id)
    response = add(client, path, filename)
    assert response.status_code == 201, response.text
    data = response.json()
    page = data["pages"][0]
    assert page["inspection"]["classification"] == "image_dominant"
    assert page["inspection"]["quality"]["metrics"]["decoded"]
    original = client.get(path + "/sources/" + page["source_id"])
    assert original.headers["content-type"] == media
    assert original.content == (SCANS / filename).read_bytes()
    assert (
        client.get(path + "/pages/" + page["id"] + "/image").headers["content-type"] == "image/png"
    )


def test_misleading_extension_and_corrupt(client, case_id):
    path = create(client, case_id)
    response = client.post(
        path + "/sources",
        content=(PDFS / "payslip_detail.pdf").read_bytes(),
        headers={"Content-Type": "image/jpeg", "Content-Disposition": 'filename="photo.jpg"'},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "scan_required"
    assert add(client, path, payload=b"\xff\xd8not-real-jpeg").status_code == 422
    assert client.get(path).json()["pages"] == []


@pytest.mark.parametrize("file", ["payslip_scan.pdf", "scan_with_ocr_layer.pdf"])
def test_scanned_pdf_accepted_with_or_without_text(client, case_id, file):
    path = create(client, case_id)
    payload = (
        (PDFS / file).read_bytes() if file == "payslip_scan.pdf" else (SCANS / file).read_bytes()
    )
    response = add(client, path, payload=payload)
    assert response.status_code == 201, response.text
    page = response.json()["pages"][0]["inspection"]
    assert page["classification"] == "image_dominant"
    assert page["scan_with_text_layer"] == (file == "scan_with_ocr_layer.pdf")


def test_native_rejected_even_with_logo(client, case_id):
    path = create(client, case_id)
    assert (
        add(client, path, payload=(SCANS / "native_with_logo.pdf").read_bytes()).status_code == 422
    )
    assert add(client, path, payload=(PDFS / "payslip_detail.pdf").read_bytes()).status_code == 422


def test_native_preferred_keeps_text(client, case_id):
    path = create(client, case_id, "bank_statement")
    assert add(client, path, payload=(PDFS / "bank_table.pdf").read_bytes()).status_code == 201
    state = process(client, path)
    assert state["processing_status"] == "completed"
    run = client.get(path + "/runs/" + state["latest_run_id"]).json()
    assert run["extraction"]["tables"][0]["rows"][1][3] == "280 000"
    assert all(e["method"] == "native" for e in run["extraction"]["evidence"])
    assert state["ocr_status"] == "not_required"
    assert state["authenticity_status"] == "not_assessed"


def test_mixed_multipage_classification_and_delete_blank(client, case_id):
    path = create(client, case_id, "bank_statement")
    response = add(client, path, payload=(SCANS / "mixed_multipage.pdf").read_bytes())
    assert response.status_code == 201, response.text
    data = response.json()
    assert [p["inspection"]["classification"] for p in data["pages"]] == [
        "native_text",
        "mixed",
        "empty_or_unusable",
    ]
    blocked = client.post(path + "/confirm")
    assert blocked.status_code == 422
    pages = [
        {"id": p["id"], "rotation": p["rotation"], "crop": p["crop"]} for p in data["pages"][:2]
    ]
    assert (
        client.put(
            path + "/pages", json={"expected_revision": data["revision"], "pages": pages}
        ).status_code
        == 200
    )
    assert client.post(path + "/confirm").status_code == 200


def test_mixed_scan_policy_threshold(client, case_id):
    path = create(client, case_id)
    with fitz.open(SCANS / "mixed_multipage.pdf") as source, fitz.open() as only:
        only.insert_pdf(source, from_page=1, to_page=1)
        response = add(client, path, payload=only.tobytes())
    assert response.status_code == 201, response.text
    assert response.json()["pages"][0]["inspection"]["classification"] == "mixed"


def test_native_exception_authorized_and_audited(client, case_id):
    path = create(
        client,
        case_id,
        exception_reason="Original numérique reçu du partenaire, exception technique de démonstration",
    )
    assert add(client, path, payload=(PDFS / "payslip_detail.pdf").read_bytes()).status_code == 201
    data = process(client, path)
    assert data["authenticity_status"] == "not_assessed"
    assert data["exception"]["actor_id"] == "agent-a"
    assert client.get(path + "/events").json()[0]["data"]["exception"]["reason"]


def test_structured_required_and_supporting_only(client, case_id):
    response = client.post(
        f"/individuals/{case_id}/submissions",
        json={"document_type": "credit_application", "role": "request", "period": "2026-10-01"},
    )
    assert response.status_code == 409
    response = client.post(
        f"/individuals/{case_id}/structured-inputs",
        json={
            "document_type": "credit_application",
            "period": "2026-10-01",
            "fields": {
                "requested_amount": "150000",
                "purpose": "Equipement synthétique",
                "duration": "12 mois",
            },
        },
    )
    assert response.status_code == 201
    item = response.json()
    assert item["ready_for_scoring"] is False
    path = create(client, case_id, "credit_application", supporting_structured_id=item["id"])
    assert add(client, path, payload=(PDFS / "form.pdf").read_bytes()).status_code == 201
    assert client.get(f"/individuals/{case_id}/structured-inputs/" + item["id"]).json() == item


def test_multi_image_order_rotation_crop_and_sources(client, case_id):
    path = create(client, case_id)
    first = add(client, path, "salary.png").json()
    second = add(client, path, "salary.jpg").json()
    pages = second["pages"]
    edits = [
        {"id": pages[1]["id"], "rotation": 90, "crop": [0.02, 0.02, 0.95, 0.8]},
        {"id": pages[0]["id"], "rotation": 180, "crop": [0, 0, 1, 1]},
    ]
    response = client.put(
        path + "/pages", json={"expected_revision": second["revision"], "pages": edits}
    )
    assert response.status_code == 200, response.text
    assert [p["id"] for p in response.json()["pages"]] == [p["id"] for p in edits]
    assert (
        client.put(
            path + "/pages", json={"expected_revision": second["revision"], "pages": edits}
        ).status_code
        == 409
    )
    assert (
        client.get(path + "/sources/" + pages[0]["source_id"]).content
        == (SCANS / "salary.png").read_bytes()
    )
    events = client.get(path + "/events").json()
    assert events[-1]["action"] == "pages_edited"
    assert events[-1]["data"]["before"][0]["id"] == first["pages"][0]["id"]
    assert client.get(path + "/pages/" + pages[1]["id"] + "/image").status_code == 200


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_geometry_matches_native_source(rotation):
    p, q = configuration()
    data = (PDFS / "payslip_detail.pdf").read_bytes()
    inspection = inspect(data, p["limits"], q)
    pages = [
        {
            "id": "p",
            "source_id": "s",
            "source_page": 1,
            "rotation": rotation,
            "crop": [0.02, 0.05, 0.9, 0.6],
        }
    ]
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "original.pdf"
        path.write_bytes(data)
        output, mappings = build({"s": {"path": str(path), "inspection": inspection}}, pages)
        try:
            with fitz.open(stream=data, filetype="pdf") as source:
                original = next(
                    word[:4] for word in source[0].get_text("words") if word[4] == "280"
                )
            derived = next(word[:4] for word in output[0].get_text("words") if word[4] == "280")
            from credit.documents.geometry import rectangle

            mapped = rectangle(mappings[0]["processing_to_source"], derived)
        finally:
            output.close()
    assert mapped == pytest.approx(original, abs=0.2)


def test_exif_mapping():
    p, q = configuration()
    data = (SCANS / "exif_salary.jpg").read_bytes()
    result = inspect(data, p["limits"], q)["pages"][0]
    assert result["exif_orientation"] == 6
    raw = Image.open(io.BytesIO(data))
    mapped = rectangle(result["canonical_to_raw"], [0, 0, result["width"], result["height"]])
    assert mapped == pytest.approx([0, 0, raw.width, raw.height])


def test_exact_duplicate_and_readable_warnings(client, case_id):
    path = create(client, case_id)
    assert add(client, path).status_code == 201
    response = add(client, path)
    assert response.status_code == 201
    issues = response.json()["pages"][1]["inspection"]["quality"]["issues"]
    assert any(i["code"] == "exact_duplicate" for i in issues)
    assert client.post(path + "/confirm").status_code == 200
    p, q = configuration()
    blurred = Image.open(SCANS / "blurred.png")
    issues = quality(blurred, q, orientation=False)["issues"]
    assert any(i["code"] == "blur" for i in issues)


def test_blank_blocking_and_crop_validation(client, case_id):
    path = create(client, case_id)
    response = add(client, path, "blank.png")
    assert response.status_code == 201
    data = response.json()
    assert data["quality_status"] == "blocked"
    assert client.post(path + "/confirm").status_code == 422
    response = client.put(
        path + "/pages",
        json={
            "expected_revision": data["revision"],
            "pages": [{"id": data["pages"][0]["id"], "rotation": 0, "crop": [0.9, 0, 0.2, 1]}],
        },
    )
    assert response.status_code == 422


def test_file_and_pixel_limits(client, case_id, monkeypatch, tmp_path):
    # Même contenu réel, seuils abaissés explicitement dans le référentiel technique.
    p, q = configuration()
    p["limits"]["max_pixels"] = 100
    file = tmp_path / "policy.json"
    file.write_text(json.dumps(p))
    monkeypatch.setenv("CREDIT_DOCUMENT_POLICY_FILE", str(file))
    path = create(client, case_id)
    assert add(client, path).status_code == 413
    response = client.post(
        path + "/sources", content=b"123", headers={"Content-Length": "26214401"}
    )
    assert response.status_code == 413


def test_actual_stream_byte_limit():
    import asyncio
    from starlette.requests import Request
    from fastapi import HTTPException
    from credit.documents.intake_routes import bounded_body

    chunks = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )

    async def receive():
        return next(chunks)

    request = Request({"type": "http", "headers": []}, receive)
    with pytest.raises(HTTPException) as error:
        asyncio.run(bounded_body(request, 5))
    assert error.value.status_code == 413


def test_french_missing_deposit_retained_then_retry(client, case_id):
    path = create(client, case_id)
    added = add(client, path).json()
    assert client.post(path + "/confirm").status_code == 200
    with patch(
        "credit.documents.intake_service.ocr_available", return_value=(False, "fra_missing")
    ):
        result = client.post(path + "/process").json()
    assert result["processing_status"] == "waiting_dependency"
    assert result["ocr_status"] == "waiting_dependency"
    assert result["ready_for_scoring"] is False
    assert (
        client.get(path + "/sources/" + added["pages"][0]["source_id"]).content
        == (SCANS / "salary.png").read_bytes()
    )
    result = client.post(path + "/process").json()
    assert result["processing_status"] == "completed", result
    run = client.get(path + "/runs/" + result["latest_run_id"]).json()
    assert run["ocr_language"] == "fra"
    assert (
        run["extraction"]["fields"]["net_income"]["candidates"][0]["normalized"][
            "amount_as_printed"
        ]
        == "280000"
    )


def test_worker_failure_is_explicit(client, case_id):
    path = create(client, case_id)
    add(client, path)
    assert client.post(path + "/confirm").status_code == 200
    with patch.object(
        client.app.state.scan_runner, "run", side_effect=WorkerError("processing_timeout")
    ):
        result = client.post(path + "/process").json()
    assert result["processing_status"] == "failed"
    assert result["processing_error"] == "processing_timeout"
    assert result["ocr_status"] == "failed"


def test_real_worker_timeout_and_concurrency():
    p, q = configuration()
    limits = {**p["limits"], "timeout_seconds": 1}
    runner = Runner(limits)
    with pytest.raises(WorkerError, match="processing_timeout"):
        runner.run("sleep_for_test", {"seconds": 3})
    runner = Runner({**limits, "concurrency": 1})
    assert runner.slots.acquire(False)
    try:
        with pytest.raises(WorkerError, match="busy"):
            runner.run("inspect", {})
    finally:
        runner.slots.release()


def test_review_keeps_raw_sources_and_no_scoring(client, case_id):
    before = client.get(f"/individuals/{case_id}").json()
    analysis = client.post(f"/individuals/{case_id}/analyses").json()
    path = create(client, case_id)
    added = add(client, path).json()
    state = process(client, path)
    run_path = path + "/runs/" + state["latest_run_id"]
    raw = client.get(run_path).json()
    assert client.get(path).json()["processing_status"] == "completed"
    candidate = raw["extraction"]["fields"]["net_income"]["candidates"][0]
    correction = {
        "decisions": {
            "net_income": {
                "value": {"amount": "279000", "currency": "XOF", "unit_multiplier": "1"},
                "evidence_ids": [candidate["evidence_id"]],
                "reason": "Correction synthétique après lecture de la source",
            }
        }
    }
    response = client.post(run_path + "/reviews", json=correction)
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["actor_id"] == "agent-a"
    assert review["extraction"]["review_history"][-1]["reviewer"] == "agent-a"
    assert client.get(run_path).json()["extraction"] == raw["extraction"]
    assert (
        client.get(path + "/sources/" + added["pages"][0]["source_id"]).content
        == (SCANS / "salary.png").read_bytes()
    )
    assert client.get(f"/individuals/{case_id}").json() == before
    assert client.post(f"/individuals/{case_id}/analyses").json()["result"] == analysis["result"]
    assert client.get(path).json()["authenticity_status"] == "not_assessed"
    assert client.get(path).json()["review_status"] == "partially_reviewed"
    assert review["ready_for_scoring"] is False
    assert client.get(run_path + "/pages/" + added["pages"][0]["id"]).status_code == 200
    assert candidate["source"]["source_id"] == added["pages"][0]["source_id"]
    assert candidate["source"]["bbox"]
    assert client.post(path + "/reopen").status_code == 200
    assert client.get(run_path).json()["reviews"][0]["id"] == review["id"]


def test_unauthorized_every_operation(client, case_id, individual):
    path = create(client, case_id)
    added = add(client, path).json()
    state = process(client, path)
    page = added["pages"][0]
    run = state["latest_run_id"]
    b = {"Authorization": "Bearer synthetic-b"}
    for route in [
        path,
        path + "/pages/" + page["id"] + "/image",
        path + "/sources/" + page["source_id"],
        path + "/runs/" + run,
        path + "/runs/" + run + "/pages/" + page["id"],
        path + "/events",
        f"/individuals/{case_id}",
        f"/individuals/{case_id}/documents",
    ]:
        assert client.get(route, headers=b).status_code == 404, route
    for suffix in ["/sources", "/confirm", "/process", "/reopen", f"/runs/{run}/reviews"]:
        response = client.post(
            path + suffix, headers=b, json={"decisions": {}} if suffix.endswith("reviews") else None
        )
        assert response.status_code == 404, (suffix, response.text)
    assert (
        client.put(
            path + "/pages", headers=b, json={"expected_revision": 2, "pages": [{"id": page["id"]}]}
        ).status_code
        == 404
    )
    other = client.post("/individuals", headers=b, json=individual).json()["id"]
    denied = client.post(
        f"/individuals/{other}/submissions",
        headers=b,
        json={
            "document_type": "payslip",
            "role": "synthetic",
            "period": "2026-10-01",
            "exception_reason": "Exception injustifiée par cet agent",
        },
    )
    assert denied.status_code == 403


def test_auth_fail_closed(client, monkeypatch):
    assert client.get("/documents/policies", headers={"Authorization": ""}).status_code == 401
    assert (
        client.get("/documents/policies", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )
    monkeypatch.delenv("CREDIT_AUTH_FILE")
    assert client.get("/documents/policies").status_code == 503
    assert client.get("/health").status_code == 200


def test_delete_last_page_retains_original(client, case_id):
    path = create(client, case_id)
    added = add(client, path).json()
    response = client.put(
        path + "/pages", json={"expected_revision": added["revision"], "pages": []}
    )
    assert response.status_code == 200
    assert response.json()["pages"] == []
    assert client.post(path + "/confirm").status_code == 409
    assert client.get(path + "/sources/" + added["pages"][0]["source_id"]).status_code == 200


def test_review_permissions_and_manual_missing_value(client, case_id, local_identities):
    path = create(client, case_id)
    add(client, path)
    state = process(client, path)
    run_path = path + "/runs/" + state["latest_run_id"]
    run = client.get(run_path).json()
    # Donnée absente : référence explicite à la zone de la page, sans créer un candidat OCR fictif.
    assert run["extraction"]["fields"]["contract_type"]["status"] == "not_found"
    correction = {
        "regions": [
            {"id": "manual:region1", "page_id": state["pages"][0]["id"], "bbox": [10, 10, 50, 30]}
        ],
        "decisions": {
            "contract_type": {
                "value": "CDI synthétique",
                "evidence_ids": ["manual:region1"],
                "reason": "Transcription humaine de démonstration sur la zone sélectionnée",
            }
        },
    }
    identities = json.loads(local_identities.read_text())
    identities["users"][1]["case_ids"] = [case_id]
    local_identities.write_text(json.dumps(identities))
    b = {"Authorization": "Bearer synthetic-b"}
    assert client.get(path, headers=b).status_code == 200
    assert client.post(run_path + "/reviews", json=correction, headers=b).status_code == 403
    reviewed = client.post(run_path + "/reviews", json=correction)
    assert reviewed.status_code == 201, reviewed.text
    data = reviewed.json()
    assert data["extraction"]["review_history"][-1]["reviewer"] == "agent-a"
    assert data["extraction"]["evidence"][-1]["source"]["source_sha256"]
    assert client.get(run_path).json()["extraction"] == run["extraction"]
    assert data["authenticity_status"] == "not_assessed"


def test_ocr_failure_warning_blocks_completion(client, case_id):
    path = create(client, case_id)
    add(client, path)
    confirmed = client.post(path + "/confirm").json()
    prepared = client.get(path + "/runs/" + confirmed["preparation_run_id"]).json()
    with Session(client.app.state.engine) as session:
        run = session.get(DocumentRun, prepared["id"])
        payload = run.derivative_pdf
    failed = extract_pdf(payload, "payslip", ocr="never")
    failed["warnings"].append("page_1:ocr_failed")
    with patch.object(
        client.app.state.scan_runner,
        "run",
        return_value={
            "derivative_pdf": payload,
            "mappings": prepared["mappings"],
            "quality": prepared["quality"],
            "extraction": failed,
        },
    ):
        response = client.post(path + "/process")
    assert response.status_code == 200
    assert response.json()["ocr_status"] == "failed"
    assert response.json()["processing_status"] == "failed"
    assert client.get(path).json()["processing_status"] == "failed"


def test_business_separate_core_and_wrong_ids(client, business, case_id):
    business_id = client.post("/businesses", json=business).json()["id"]
    response = client.post(
        f"/businesses/{business_id}/submissions",
        json={"document_type": "rccm", "role": "registration", "period": "2026-10-01"},
    )
    assert response.status_code == 201
    path = f"/businesses/{business_id}/submissions/" + response.json()["id"]
    assert add(client, path).status_code == 201
    assert (
        client.get(f"/individuals/{case_id}/submissions/" + response.json()["id"]).status_code
        == 404
    )
    assert (
        client.post(
            f"/businesses/{business_id}/submissions",
            json={"document_type": "payslip", "role": "invalid-profile", "period": "2026-10-01"},
        ).status_code
        == 422
    )


def test_edge_exposure_and_orientation_measurements():
    from PIL import ImageDraw

    _, q = configuration()
    image = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 100, 30, 800), fill="black")
    result = quality(image, q, orientation=False)
    assert any(issue["code"] == "content_near_edge" for issue in result["issues"])
    assert result["metrics"]["orientation"]["status"] == "not_determined"
    assert (
        quality(Image.new("RGB", (800, 1000), "black"), q, orientation=False)["status"] == "blocked"
    )


def test_upload_duration_limit():
    import asyncio
    from starlette.requests import Request
    from fastapi import HTTPException
    from credit.documents.intake_routes import bounded_body

    async def receive():
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"x", "more_body": False}

    request = Request({"type": "http", "headers": []}, receive)
    with pytest.raises(HTTPException) as error:
        asyncio.run(bounded_body(request, 100, 0.01))
    assert error.value.status_code == 408


def test_auth_json_and_invalid_configuration(client, local_identities, monkeypatch):
    identities = json.loads(local_identities.read_text())
    monkeypatch.delenv("CREDIT_AUTH_FILE")
    monkeypatch.setenv("CREDIT_AUTH_JSON", json.dumps(identities))
    assert client.get("/documents/policies").status_code == 200
    monkeypatch.setenv("CREDIT_AUTH_JSON", '{"users":[{}]}')
    assert client.get("/documents/policies").status_code == 503


def test_scoped_analyses_and_explicit_legacy_grant(client, case_id, local_identities):
    analysis = client.post(f"/individuals/{case_id}/analyses").json()
    b = {"Authorization": "Bearer synthetic-b"}
    assert client.get("/analyses/" + analysis["id"], headers=b).status_code == 404
    # Un ancien dossier sans propriétaire n'est jamais attribué implicitement.
    from credit.persistence import CaseRecord

    with Session(client.app.state.engine) as session:
        record = session.get(CaseRecord, case_id)
        record.owner_id = None
        session.commit()
    assert client.get(f"/individuals/{case_id}").status_code == 404
    data = json.loads(local_identities.read_text())
    data["users"][0]["case_ids"].append(case_id)
    local_identities.write_text(json.dumps(data))
    assert client.get(f"/individuals/{case_id}").status_code == 200


def test_technical_admission_and_structured_fields(client, case_id, monkeypatch, tmp_path):
    p, _ = configuration()
    p["limits"].update(max_pages=1, max_total_bytes=500000)
    file = tmp_path / "policy.json"
    file.write_text(json.dumps(p))
    monkeypatch.setenv("CREDIT_DOCUMENT_POLICY_FILE", str(file))
    path = create(client, case_id)
    response = add(client, path, payload=b"x" * 500001)
    assert response.status_code == 413
    assert add(client, path).status_code == 201
    assert add(client, path).status_code == 413
    assert (
        client.post(
            f"/individuals/{case_id}/structured-inputs",
            json={
                "document_type": "credit_application",
                "period": "2026-10-01",
                "fields": {"file": "foo.pdf"},
            },
        ).status_code
        == 422
    )


def test_missing_form_value_transcription_is_preserved(client, case_id):
    structured = client.post(
        f"/individuals/{case_id}/structured-inputs",
        json={
            "document_type": "credit_application",
            "period": "2026-10-01",
            "fields": {
                "requested_amount": None,
                "purpose": "Test synthétique",
                "duration": "12 mois",
            },
        },
    ).json()
    assert structured["missing_values"] == ["requested_amount"]
    path = create(client, case_id, "credit_application", supporting_structured_id=structured["id"])
    assert add(client, path, payload=(PDFS / "form.pdf").read_bytes()).status_code == 201
    state = process(client, path)
    run = client.get(path + "/runs/" + state["latest_run_id"]).json()
    assert run["extraction"]["form_fields"][0]["value"] == "150000"
    assert run["extraction"]["form_fields"][0]["source"]["source_id"]
    assert (
        client.get(f"/individuals/{case_id}/structured-inputs/" + structured["id"]).json()[
            "fields"
        ]["requested_amount"]
        is None
    )


def test_configured_formats_are_enforced_on_decoded_content(client, case_id, monkeypatch, tmp_path):
    policy, _ = configuration()
    policy["rules"]["payslip"]["formats"] = ["image/png"]
    file = tmp_path / "formats.json"
    file.write_text(json.dumps(policy))
    monkeypatch.setenv("CREDIT_DOCUMENT_POLICY_FILE", str(file))
    path = create(client, case_id)
    assert add(client, path, "salary.jpg").json()["detail"] == "format_not_allowed_for_document"
    assert add(client, path, "salary.png").status_code == 201
