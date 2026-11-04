import hashlib
import json
from pathlib import Path

import fitz
import pytest

from credit.printing.catalog import CATALOG
from credit.printing.contracts import PrintRequest
from credit.printing.presentation import build_presentation, amount, french_date
from credit.printing.render import html_document, pdf_document
from credit.printing.isolation import render_isolated

ROOT = Path("examples/assessments")


def payload(name="individual_control"):
    case = json.loads((ROOT / (name + ".json")).read_text())
    case["record_details"] = {
        "address": "Secteur synthétique, Ouagadougou",
        "telephone": "+226 00 00 00 00",
        "applicant_comments": "Échéance et trésorerie — François, née à Bobo-Dioulasso.",
        "internal_observations": "SECRET_INTERNE_A_NE_PAS_COMMUNIQUER",
    }
    if name.startswith("business"):
        case["record_details"]["representatives"] = [{"name": "Aïssata Exemple", "role": "Gérante"}]
    return case


def model(
    template="identification",
    core="individuals",
    audience="analyst",
    report=None,
    publication=None,
    case=None,
):
    return build_presentation(
        case
        or payload(
            "individual_control" if core == "individuals" else "business_profitable_cash_tension"
        ),
        core,
        PrintRequest(template_id=template, audience=audience),
        {"Dossier": "cas-synthetique", "Édition": "edition-synthetique"},
        [],
        report,
        publication,
    )


def text(pdf):
    with fitz.open(stream=pdf, filetype="pdf") as document:
        return "\n".join(p.get_text() for p in document)


def create(client, core="individuals", name=None):
    name = name or (
        "individual_control" if core == "individuals" else "business_profitable_cash_tension"
    )
    r = client.post("/" + core, json=payload(name))
    assert r.status_code == 201, r.text
    return f"/{core}/" + r.json()["id"]


def assessment(client, path, monkeypatch):
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "true")
    core = path.split("/")[1]
    r = client.post(
        path + "/assessments",
        json={"mode": "demonstration", "policy_id": core + "-illustrative-v1"},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize(
    "core,template",
    [
        (core, t)
        for core, templates in CATALOG.items()
        for t in templates
        if t != "simulation_report"
    ],
)
def test_all_templates_real_pdf_and_same_presentation(core, template):
    name = "individual_control" if core == "individuals" else "business_profitable_cash_tension"
    report = json.loads((ROOT / (name + ".report.json")).read_text())
    m = model(template, core, report=report)
    html, pdf = render_isolated(m)
    extracted = text(pdf)
    assert m.title in " ".join(extracted.split())
    assert m.title in html
    assert "Page 1 /" in extracted and "cas-synthetique" in extracted
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1000
    assert "accord de crédit" in extracted
    if template == "financial_declaration":
        assert "Déclaration financière issue des champs saisis" in extracted
    if template == "analysis_report":
        for section in report["sections"]:
            assert section["title"] in extracted
        assert "ILLUSTRATIF" in extracted


def test_values_accents_zero_unknown_and_dates():
    case = payload()
    case["mobilizable_reserve"] = {"value": "0", "state": "known", "evidence_ids": ["synthetic"]}
    case["periods"][0]["essential_expenses"] = {
        "value": None,
        "state": "unknown",
        "evidence_ids": [],
    }
    m = model("household_budget", case=case)
    extracted = text(pdf_document(m))
    assert "0,00 XOF / FCFA" in extracted and "Inconnu" in extracted
    assert "février 2026" in extracted
    assert "Brouillon" in extracted
    assert amount({"state": "not_applicable", "value": None}) == "Non applicable"
    assert "Estimé" in amount({"state": "estimated", "value": "3"})
    assert french_date("2026-02-01") == "1 février 2026"


def test_no_html_or_reportlab_markup_injection():
    case = payload()
    case["name"] = '<script>alert("x")</script><img src="file:///etc/passwd">'
    case["record_details"]["applicant_comments"] = (
        '<a href="https://bad.invalid">NE_PAS_CHARGER</a>'
    )
    m = model(case=case)
    html, pdf = render_isolated(m)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '<img src="file:' not in html
    assert "NE_PAS_CHARGER" in text(pdf)
    assert not fitz.open(stream=pdf, filetype="pdf")[0].get_links()


def test_applicant_projection_removes_internal_data_before_rendering():
    report = json.loads((ROOT / "individual_control.report.json").read_text())
    m = model("analysis_report", audience="applicant", report=report)
    serialized = m.model_dump_json()
    assert "SECRET_INTERNE" not in serialized
    assert "minimum_margin_income" not in serialized
    assert "capacity_margin" not in serialized
    assert "sources" not in serialized and "100.00" not in serialized
    assert "non communiqués" in html_document(m)
    released = model(
        "analysis_report",
        audience="applicant",
        report=report,
        publication={"financial_results": True, "suggestions": True},
    )
    assert "70\u202f000,00" in released.model_dump_json()
    assert "capacity_margin" not in released.model_dump_json()
    assert "SECRET_INTERNE" not in released.model_dump_json()


def test_no_score_fabricated_without_analysis_or_grid():
    m = model("analysis_report")
    assert "Analyse incomplète" == m.status
    assert "Aucune analyse disponible" in html_document(m)
    assert "100 /" not in text(pdf_document(m))


def test_print_does_not_call_financial_engine(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Les gabarits ne calculent pas")

    monkeypatch.setattr("credit.assessment.engines.IndividualAnalysisEngine.analyze", forbidden)
    m = model(
        "analysis_report", report=json.loads((ROOT / "individual_control.report.json").read_text())
    )
    assert "Rapport détaillé" in text(pdf_document(m))


def test_api_versions_frozen_and_authorized(client):
    path = create(client)
    body = {"template_id": "identification", "audience": "analyst"}
    pre = client.post(path + "/print/preflight", json=body)
    assert pre.status_code == 200
    assert client.post(path + "/print/preview", json=body).status_code == 200
    assert len(client.get(path + "/print/templates").json()) == 11
    edition = client.post(path + "/print/editions", json=body).json()
    assert edition["status"] == "completed", edition
    url = "/print-editions/" + edition["id"]
    original = client.get(url + "/pdf").content
    assert hashlib.sha256(original).hexdigest() == edition["pdf_sha256"]
    assert "SECRET_INTERNE" in text(original)
    case = client.get(path).json()["data"]
    case["name"] = "NOM_MODIFIÉ_APRÈS_ÉDITION"
    client.put(path, json=case, headers={"If-Match": str(client.get(path).json()["version"])})
    assert client.get(url + "/pdf").content == original
    second = client.post(path + "/print/editions", json=body).json()
    assert second["version"] == 2 and second["input_sha256"] != edition["input_sha256"]
    versions = client.get(path + "/print/editions").json()
    assert versions[0]["is_latest"] and not versions[1]["is_latest"]
    assert "NOM_MODIFIÉ" in text(client.get("/print-editions/" + second["id"] + "/pdf").content)
    other = {"Authorization": "Bearer synthetic-b"}
    for endpoint in [
        url,
        url + "/model",
        url + "/pdf",
        url + "/preview",
        path + "/print/editions",
        path + "/print/templates",
    ]:
        assert client.get(endpoint, headers=other).status_code == 404
    actions = [e["action"] for e in client.get(url + "/events").json()]
    assert "pdf_downloaded" in actions and "generation_completed" in actions


def test_pending_processing_and_failure_states(client, monkeypatch):
    path = create(client)
    r = client.post(
        path + "/print/editions", json={"template_id": "identification", "generate_now": False}
    )
    edition = r.json()
    url = "/print-editions/" + edition["id"]
    assert edition["status"] == "pending"
    assert client.get(url + "/pdf").status_code == 409

    def failure(*args):
        raise ValueError("print_timeout")

    monkeypatch.setattr("credit.printing.service.render_isolated", failure)
    r = client.post(url + "/process")
    assert r.json()["status"] == "failed" and r.json()["error"] == "print_timeout"
    assert client.get(url + "/pdf").status_code == 409
    assert client.get(url + "/preview").status_code == 409
    assert client.post(url + "/process").status_code == 409


def test_requester_and_analyst_access_and_publication(client, monkeypatch, local_identities):
    path = create(client)
    a = assessment(client, path, monkeypatch)
    internal = client.post(
        path + "/print/editions",
        json={"template_id": "analysis_report", "audience": "analyst", "assessment_id": a["id"]},
    ).json()
    registry = json.loads(local_identities.read_text())
    registry["users"][1]["case_ids"] = [path.split("/")[-1]]
    local_identities.write_text(json.dumps(registry))
    other = {"Authorization": "Bearer synthetic-b"}
    assert (
        client.get("/print-editions/" + internal["id"] + "/pdf", headers=other).status_code == 403
    )
    assert (
        client.post(
            path + "/print/editions",
            headers=other,
            json={
                "template_id": "analysis_report",
                "audience": "analyst",
                "assessment_id": a["id"],
            },
        ).status_code
        == 403
    )
    body = {"template_id": "analysis_report", "assessment_id": a["id"]}
    public = client.post(path + "/print/editions", json=body, headers=other).json()
    assert (
        "non communiqués"
        in client.get("/print-editions/" + public["id"] + "/preview", headers=other).text
    )
    assert (
        client.post(
            "/assessments/" + a["id"] + "/print-publication",
            headers=other,
            json={"financial_results": True, "justification": "Accord de communication"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/assessments/" + a["id"] + "/print-publication",
            json={
                "financial_results": True,
                "suggestions": True,
                "justification": "Communication des constats au demandeur",
            },
        ).status_code
        == 201
    )
    released = client.post(path + "/print/editions", json=body, headers=other).json()
    m = client.get("/print-editions/" + released["id"] + "/model", headers=other).json()
    assert "70\u202f000,00" in json.dumps(m, ensure_ascii=False)
    assert "SECRET_INTERNE" not in json.dumps(m) and "capacity_margin" not in json.dumps(m)
    assert len(client.get(path + "/print/editions", headers=other).json()) == 2


def test_institution_boundary_even_with_case_grant(client, local_identities):
    path = create(client)
    registry = json.loads(local_identities.read_text())
    registry["users"][1]["case_ids"] = [path.split("/")[-1]]
    registry["users"][1]["institution_id"] = "AUTRE_INSTITUTION"
    local_identities.write_text(json.dumps(registry))
    assert (
        client.get(
            path + "/print/templates", headers={"Authorization": "Bearer synthetic-b"}
        ).status_code
        == 404
    )
    assert client.get(path, headers={"Authorization": "Bearer synthetic-b"}).status_code == 404


def test_cross_case_assessment_and_applicability_rejected(client, monkeypatch):
    first = create(client)
    second = create(client)
    a = assessment(client, first, monkeypatch)
    assert (
        client.post(
            second + "/print/editions",
            json={"template_id": "analysis_report", "assessment_id": a["id"]},
        ).status_code
        == 404
    )
    for t in ["working_capital", "nonsense", "simulation_report"]:
        assert client.post(first + "/print/editions", json={"template_id": t}).status_code == 422


def test_simulation_report_before_after_and_terms(client, monkeypatch):
    path = create(client)
    a = assessment(client, path, monkeypatch)
    simulated = client.post(
        "/assessments/" + a["id"] + "/simulations",
        json={"specification": {"kind": "stress", "scenario": {"revenue_drop": ".20"}}},
    ).json()
    body = {
        "template_id": "simulation_report",
        "audience": "analyst",
        "assessment_id": simulated["id"],
    }
    ed = client.post(path + "/print/editions", json=body).json()
    assert ed["status"] == "completed", ed
    txt = text(client.get("/print-editions/" + ed["id"] + "/pdf").content)
    assert "70 000,00" in txt.replace("\u202f", " ") and "-30 000,00" in txt.replace("\u202f", " ")
    assert "Coût total" in txt and "Situation" not in txt  # valeurs conservées sans recalcul
    assert simulated["id"] in txt and a["id"] != simulated["id"]


def test_real_worker_limits(monkeypatch):
    m = model()
    monkeypatch.setenv("CREDIT_PRINT_MAX_INPUT_BYTES", "20")
    with pytest.raises(ValueError, match="print_input_limit"):
        render_isolated(m)
    monkeypatch.setenv("CREDIT_PRINT_MAX_INPUT_BYTES", "3000000")
    monkeypatch.setenv("CREDIT_PRINT_MAX_PAGES", "1")
    m = model(
        "analysis_report", report=json.loads((ROOT / "individual_control.report.json").read_text())
    )
    with pytest.raises(ValueError, match="print_page_limit"):
        render_isolated(m)


def test_long_text_and_repeated_headers_no_truncation():
    from credit.printing.contracts import Section, Table

    m = model()
    long = "Françoise et Aïssata vérifient les échéances à Ouagadougou. " * 90
    m.sections = [
        Section(
            title="Tableau long",
            tables=[
                Table(
                    columns=["Référence répétée", "Commentaire complet"],
                    rows=[[str(i), long] for i in range(12)],
                )
            ],
        )
    ]
    pdf = pdf_document(m)
    with fitz.open(stream=pdf, filetype="pdf") as d:
        assert len(d) > 3
        assert all("Page " in p.get_text() for p in d)
        assert sum("Référence répétée" in p.get_text() for p in d) >= len(d) - 1
        assert sum(p.get_text().count("Françoise") for p in d) == 90 * 12
        for page in d:
            assert all(
                0 <= b[0] < b[2] <= page.rect.width + 1 and 0 <= b[1] < b[3] <= page.rect.height + 1
                for b in page.get_text("blocks")
            )


def test_branding_and_controlled_logo(monkeypatch, tmp_path):
    from PIL import Image
    from credit.printing.service import brand

    logo = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), "gray").save(logo)
    monkeypatch.setenv("CREDIT_PRINT_PLATFORM_NAME", "Plateforme synthétique Épargne")
    monkeypatch.setenv("CREDIT_PRINT_LOGO_FILE", str(logo))
    m = brand(model())
    assert m.logo_png and "Plateforme synthétique" in text(pdf_document(m))
    monkeypatch.setenv("CREDIT_PRINT_LOGO_FILE", "https://example.invalid/logo.svg")
    with pytest.raises(OSError):
        brand(model())


def test_raw_extraction_not_printed_as_verified():
    case = payload()
    case["evidence"][0]["status"] = "unverified_extracted"
    m = model("income_expenses", case=case)
    assert "Extrait non contrôlé" in html_document(m)
    assert "Contrôlé (sans authentification)" not in html_document(m)


def test_returned_document_separate_and_same_case(client):
    path = create(client)
    other = create(client)
    edition = client.post(path + "/print/editions", json={"template_id": "identification"}).json()
    before = client.get("/print-editions/" + edition["id"] + "/pdf").content

    def submit(path):
        r = client.post(
            path + "/submissions",
            json={
                "document_type": "payslip",
                "role": "retour_signe_synthetique",
                "period": "2026-02-01",
            },
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    sid = submit(path)
    url = "/print-editions/" + edition["id"] + "/returned-documents"
    assert (
        client.post(
            url, json={"submission_id": submit(other), "description": "Pièce externe"}
        ).status_code
        == 404
    )
    returned = client.post(
        url, json={"submission_id": sid, "description": "Retour distinct à vérifier"}
    ).json()
    assert returned["authenticity_status"] == "not_assessed"
    assert client.get("/print-editions/" + edition["id"] + "/pdf").content == before
    assert any(
        e["action"] == "returned_document_linked"
        for e in client.get("/print-editions/" + edition["id"] + "/events").json()
    )


def test_worker_timeout_and_concurrency_errors(monkeypatch):
    import credit.printing.isolation as isolation
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("synthetic", 1)

    monkeypatch.setattr(isolation.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="print_timeout"):
        isolation.render_isolated(model())
    assert isolation.GATE.acquire(blocking=False)
    assert isolation.GATE.acquire(blocking=False)
    try:
        with pytest.raises(ValueError, match="print_busy"):
            isolation.render_isolated(model())
    finally:
        isolation.GATE.release()
        isolation.GATE.release()


def test_comment_starting_with_date_is_not_truncated():
    from credit.printing.presentation import scalar

    assert (
        scalar("2026-02-01 — commentaire complet à conserver")
        == "2026-02-01 — commentaire complet à conserver"
    )


def test_applicant_incomplete_analysis_remains_labelled_without_internal_leak():
    case = payload()
    case["missing_information"] = []
    report = json.loads((ROOT / "individual_control.report.json").read_text())
    report["missing_information"] = ["CONTROLE_INTERNE_CONFIDENTIEL"]
    m = model("analysis_report", audience="applicant", report=report, case=case)
    assert m.status == "Analyse incomplète"
    assert "CONTROLE_INTERNE_CONFIDENTIEL" not in m.model_dump_json()
    assert m.missing_information


def test_reconstructed_cashflows_financial_declaration_uses_available_fields():
    case = payload("business_profitable_cash_tension")
    case["mode"] = "reconstructed_cashflows"
    case["analysis_details"]["accounting"] = []
    m = model("financial_declaration", "businesses", case=case)
    html = html_document(m)
    assert "Encaissements d’exploitation" in html
    assert "100\u202f000,00 XOF / FCFA" in html
    assert "sans compte de résultat reconstitué" in html
    assert "certifié" in text(pdf_document(m))


def test_incomplete_simulation_still_identifies_illustrative_policy():
    report = {
        "status": "needs_explicit_projections",
        "terms": {"total_credit_cost": "0"},
        "policy_snapshot": {"validation_status": "illustrative_not_validated"},
        "missing_information": ["Projections futures à fournir"],
    }
    m = model("simulation_report", report=report)
    assert m.status == "Analyse incomplète"
    assert any("ILLUSTRATIF" in notice for notice in m.notices)
    assert "ILLUSTRATIF" in text(pdf_document(m))
