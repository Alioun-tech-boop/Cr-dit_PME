import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import fitz

from credit_pdf.catalog import CATALOG, FAMILIES, public_catalog
from credit_pdf.engine import (MAX_BYTES, ExtractionError, classification, extract_pdf,
                               normalize_money, normalize_value)
from credit_pdf.review import apply_review
from credit_pdf.server import make_server
from examples.generate_examples import make_pdf, scanned_pdf


class EngineTests(unittest.TestCase):
    def pdf(self, title="Bulletin de salaire", lines=("Net à payer: 250 000 FCFA",), **kwargs):
        return make_pdf(title, lines, **kwargs)

    def test_salary_amount(self):
        r = extract_pdf(self.pdf(), "payslip", ocr="never")
        c = r["fields"]["net_income"]["candidates"][0]
        self.assertEqual(c["normalized"]["amount_as_printed"], "250000")
        self.assertEqual(c["normalized"]["currency"], "XOF")
        self.assertEqual(c["page"], 1)
        self.assertEqual(len(c["bbox"]), 4)
        self.assertIn(c["evidence_id"], [e["id"] for e in r["evidence"]])
        self.assertFalse(r["ready_for_scoring"])

    def test_auto_classification(self):
        self.assertEqual(extract_pdf(self.pdf(), ocr="never")["document_type"], "payslip")

    def test_unknown_classification_not_guessed(self):
        r = extract_pdf(self.pdf("Document inconnu", ("Valeur: 100",)), ocr="never")
        self.assertIsNone(r["document_type"])
        self.assertEqual(r["fields"], {})

    def test_mixed_types_not_merged(self):
        a = fitz.open(stream=self.pdf(), filetype="pdf")
        b = fitz.open(stream=self.pdf("Bilan"), filetype="pdf")
        a.insert_pdf(b)
        r = extract_pdf(a.tobytes(), ocr="never")
        a.close(); b.close()
        self.assertIsNone(r["document_type"])
        self.assertEqual(r["page_count"], 2)
        self.assertTrue(any("multiple_document_types" in x for x in r["warnings"]))

    def test_missing_not_zero(self):
        r = extract_pdf(self.pdf(lines=("Employeur: SOCIETE SPECIMEN",)), "payslip", ocr="never")
        self.assertEqual(r["fields"]["net_income"]["status"], "not_found")
        self.assertEqual(r["fields"]["net_income"]["candidates"], [])

    def test_conflicting_values_preserved(self):
        r = extract_pdf(self.pdf(lines=("Net à payer: 250 000", "Net à payer: 280 000")), "payslip", ocr="never")
        self.assertEqual(r["fields"]["net_income"]["status"], "ambiguous_requires_review")
        self.assertEqual(len(r["fields"]["net_income"]["candidates"]), 2)

    def test_ambiguous_thousands(self):
        self.assertTrue(normalize_money("1,234 FCFA")["ambiguous"])
        self.assertTrue(normalize_money("1.234 FCFA")["ambiguous"])

    def test_mixed_separators(self):
        self.assertTrue(normalize_money("1.234,56 EUR")["ambiguous"])

    def test_decimal_negative_zero(self):
        self.assertEqual(normalize_money("-12,50 EUR")["amount_as_printed"], "-12.50")
        self.assertEqual(normalize_money("(25 000) FCFA")["amount_as_printed"], "-25000")
        self.assertEqual(normalize_money("0 FCFA")["amount_as_printed"], "0")

    def test_date_validation(self):
        self.assertEqual(normalize_value("04/11/2026", "date")["value"], "2026-11-04")
        self.assertIsNone(normalize_value("31/02/2026", "date"))

    def test_unit_not_implicitly_multiplied(self):
        r = extract_pdf(self.pdf("Bilan", ("Montants en milliers de FCFA", "Total actif: 1 200")), "balance_sheet", ocr="never")
        self.assertTrue(any("unit_scale" in x for x in r["warnings"]))
        self.assertEqual(r["fields"]["total_assets"]["candidates"][0]["normalized"]["amount_as_printed"], "1200")

    def test_statement_table_and_mapping(self):
        data = self.pdf("Relevé bancaire", (), table=[
            ["Date", "Libellé", "Débit", "Crédit"],
            ["04/11/2026", "Salaire", "", "250 000"],
            ["05/11/2026", "Loyer", "60 000", ""]])
        r = extract_pdf(data, "bank_statement", ocr="never")
        self.assertTrue(r["tables"])
        structured = r["tables"][0]["structured"]
        self.assertEqual(len(structured["records"]), 2)
        cells = structured["records"][0]["cells"]
        value = next(c for c in cells if c["key"] == "credit")
        self.assertEqual(value["normalized"]["amount_as_printed"], "250000")

    def test_multiyear_columns_preserved(self):
        r = extract_pdf(self.pdf("Bilan", (), table=[
            ["Rubrique", "2026", "2025"], ["Total actif", "1 200", "900"]]),
            "balance_sheet", ocr="never")
        field = r["fields"]["total_assets"]
        self.assertEqual(field["status"], "ambiguous_requires_review")
        table_candidate = next(c for c in field["candidates"] if "cells" in c)
        self.assertEqual(len(table_candidate["cells"]), 2)
        self.assertIsNone(table_candidate["normalized"])

    def test_widely_spaced_values_not_concatenated(self):
        r = extract_pdf(self.pdf("Bilan", (), table=[
            ["Rubrique", "2026", "2025"], ["Total actif", "500 000", "600 000"]]),
            "balance_sheet", ocr="never")
        for c in r["fields"]["total_assets"]["candidates"]:
            if c["method"] == "native":
                self.assertIsNone(c["normalized"])

    def test_acroform_extracted(self):
        r = extract_pdf(self.pdf("Demande de crédit", (), form=True), "credit_application", ocr="never")
        self.assertEqual(r["form_fields"][0]["name"], "montant_demande")
        self.assertEqual(r["form_fields"][0]["value"], "150000")

    def test_bad_pdf(self):
        for data in (b"", b"hello", b"%PDF-invalid"):
            with self.assertRaises(ExtractionError):
                extract_pdf(data)

    def test_size_limit(self):
        with patch("credit_pdf.engine.MAX_BYTES", 20):
            with self.assertRaises(ExtractionError):
                extract_pdf(self.pdf())

    def test_page_limit(self):
        with patch("credit_pdf.engine.MAX_PAGES", 0):
            with self.assertRaises(ExtractionError):
                extract_pdf(self.pdf())

    def test_encrypted_pdf(self):
        d = fitz.open(stream=self.pdf(), filetype="pdf")
        data = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="test-secret")
        d.close()
        with self.assertRaisesRegex(ExtractionError, "password"):
            extract_pdf(data)
        self.assertEqual(extract_pdf(data, "payslip", password="test-secret", ocr="never")["page_count"], 1)

    def test_ocr_missing_reported(self):
        data = scanned_pdf(self.pdf())
        with patch("credit_pdf.engine.shutil.which", return_value=None):
            r = extract_pdf(data, "payslip")
        self.assertTrue(any("tesseract_missing" in x for x in r["warnings"]))
        self.assertEqual(r["fields"]["net_income"]["status"], "not_found")

    def test_ocr_missing_language(self):
        data = scanned_pdf(self.pdf())
        r = extract_pdf(data, "payslip", lang="language_that_does_not_exist")
        self.assertTrue(any("ocr_languages_missing" in x or "tesseract_missing" in x for x in r["warnings"]))

    def test_real_ocr_eng(self):
        import shutil
        if not shutil.which("tesseract"):
            self.skipTest("Tesseract unavailable")
        r = extract_pdf(scanned_pdf(self.pdf()), "payslip", lang="eng")
        self.assertTrue(any(e["method"] == "ocr" for e in r["evidence"]))
        self.assertTrue(r["fields"]["net_income"]["candidates"])
        self.assertFalse(r["ready_for_scoring"])

    def test_invalid_options(self):
        for kwargs in ({"document_type": "not_a_profile"}, {"ocr": "bad"}, {"lang": "../../evil"}):
            with self.assertRaises(ExtractionError):
                extract_pdf(self.pdf(), **kwargs)

    def test_hash_deterministic(self):
        data = self.pdf()
        a = extract_pdf(data, "payslip", ocr="never")
        b = extract_pdf(data, "payslip", ocr="never")
        self.assertEqual(a["document_sha256"], b["document_sha256"])
        self.assertEqual(a["fields"], b["fields"])

    def test_review_preserves_original(self):
        r = extract_pdf(self.pdf(), "payslip", ocr="never")
        before = copy.deepcopy(r)
        candidate = r["fields"]["net_income"]["candidates"][0]
        reviewed = apply_review(r, {"net_income": {"value": "250000", "reason": "Lecture du montant sur la page",
                                "evidence_ids": [candidate["evidence_id"]]}}, "agent-test")
        self.assertEqual(r, before)
        self.assertEqual(reviewed["fields"], before["fields"])
        self.assertEqual(len(reviewed["review_history"]), 1)
        self.assertFalse(reviewed["ready_for_scoring"])

    def test_review_invalid_evidence(self):
        r = extract_pdf(self.pdf(), "payslip", ocr="never")
        with self.assertRaises(ValueError):
            apply_review(r, {"net_income": {"value": "1", "reason": "X", "evidence_ids": ["fake"]}}, "agent")

    def test_catalog_unique_fields(self):
        self.assertEqual(len(CATALOG), len(public_catalog()))
        for profile in CATALOG.values():
            self.assertIn(profile["family"], FAMILIES)
            keys = [f.key for f in profile["fields"]]
            self.assertEqual(len(keys), len(set(keys)), profile["id"])

    def test_cli_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, out = Path(tmp)/"test.pdf", Path(tmp)/"result.json"
            path.write_bytes(self.pdf())
            p = subprocess.run([sys.executable, "-m", "credit_pdf", "extract", str(path),
                                "--type", "payslip", "--ocr", "never", "--output", str(out)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(out.read_text())["document_type"], "payslip")

    def test_batch_isolation_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"valid.pdf").write_bytes(self.pdf())
            (root/"bad.pdf").write_bytes(b"bad")
            (root/"manifest.json").write_text(json.dumps({"documents": [
                {"path": "valid.pdf", "document_type": "payslip"}, {"path": "bad.pdf"}]}))
            p = subprocess.run([sys.executable, "-m", "credit_pdf", "batch", str(root/"manifest.json"),
                                "--ocr", "never", "--output-dir", str(root/"out")], capture_output=True)
            self.assertEqual(p.returncode, 1)
            results = json.loads((root/"out/manifest_results.json").read_text())["results"]
            self.assertEqual([r["status"] for r in results], ["extracted_unverified", "failed"])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"CREDIT_PDF_API_TOKEN": "test-token"}):
            self.server = make_server(port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, data=None, token=True, content_type="application/pdf"):
        headers = {"Content-Type": content_type}
        if token:
            headers["Authorization"] = "Bearer test-token"
        return urlopen(Request(self.url + path, data=data, headers=headers), timeout=10)

    def test_health_catalog(self):
        with self.request("/health") as r:
            self.assertEqual(json.load(r)["status"], "ok")
        with self.request("/catalog") as r:
            self.assertEqual(len(json.load(r)), len(CATALOG))

    def test_auth(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/catalog", token=False)
        self.assertEqual(caught.exception.code, 401)

    def test_upload_pdf(self):
        with self.request("/extract?type=payslip&ocr=never", make_pdf("Bulletin de salaire", ["Net à payer: 250 000 FCFA"])) as r:
            self.assertEqual(json.load(r)["fields"]["net_income"]["candidates"][0]["normalized"]["amount_as_printed"], "250000")

    def test_invalid_upload(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/extract", b"bad")
        self.assertEqual(caught.exception.code, 422)

    def test_wrong_content_type(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/extract", b"bad", content_type="text/plain")
        self.assertEqual(caught.exception.code, 415)

    def test_no_remote_binding(self):
        with self.assertRaises(ValueError):
            make_server("0.0.0.0")


class ProfileCoverageTests(unittest.TestCase):
    """Smoke tests synthétiques par profil, pas des mesures de précision terrain."""


def profile_test(key):
    def test(self):
        profile = CATALOG[key]
        values = {"money": "250 000 FCFA", "date": "04/11/2026", "text": "SPECIMEN-001", "rate": "8 %", "currency": "XOF"}
        pdf = make_pdf(profile["title"], [field.aliases[0] + ": " + values[field.kind] for field in profile["fields"]])
        result = extract_pdf(pdf, key, ocr="never")
        self.assertEqual(result["document_type"], key)
        for field in profile["fields"]:
            self.assertTrue(result["fields"][field.key]["candidates"], key + ":" + field.key)
        self.assertTrue(result["pages"][0]["text"])
        self.assertFalse(result["ready_for_scoring"])
    return test


for _key in CATALOG:
    setattr(ProfileCoverageTests, "test_profile_" + _key, profile_test(_key))


if __name__ == "__main__":
    unittest.main()
