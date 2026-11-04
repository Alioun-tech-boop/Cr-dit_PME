"""Contrôle les sorties réellement produites par la CLI sur les cinq pièces livrées."""

import json
from pathlib import Path

OUTPUT = Path("output/pdf")


def load(name):
    result = json.loads((OUTPUT / f"{name}.json").read_text())
    assert result["ready_for_scoring"] is False
    assert result["review_status"] == "pending"
    assert "extraction_is_not_authenticity_verification" in result["warnings"]
    assert result["page_count"] == 1
    for evidence in result["evidence"]:
        assert evidence["page"] == 1
        assert evidence["id"].startswith("p1:")
        assert len(evidence["bbox"]) == 4
    return result


def salary(name, method):
    result = load(name)
    field = result["fields"]["net_income"]
    assert field["status"] == "extracted_unverified"
    candidates = field["candidates"]
    assert len(candidates) == 1
    value = candidates[0]
    assert value["normalized"]["amount_as_printed"] == "280000"
    assert value["normalized"]["currency"] == "XOF"
    assert value["page"] == 1 and value["method"] == method
    assert value["evidence_id"] in {e["id"] for e in result["evidence"]}
    if method == "ocr":
        assert "page_1:ocr_requires_visual_review" in result["warnings"]
        assert not any(
            "missing" in warning or "failed" in warning for warning in result["warnings"]
        )
    return "280000 XOF, page 1, " + method


report = {"payslip_detail": salary("payslip_detail", "native")}
bank = load("bank_table")
table = bank["tables"][0]
assert table["page"] == 1
assert table["rows"][0] == ["Date", "Libellé", "Débit", "Crédit"]
records = table["structured"]["records"]
assert records[0]["cells"][3]["normalized"]["amount_as_printed"] == "280000"
assert records[1]["cells"][2]["normalized"]["amount_as_printed"] == "60000"
assert records[0]["cells"][2]["normalized"] is None
assert records[0]["cells"][3]["normalized"]["currency"] is None
report["bank_table"] = "Crédit 280000, débit 60000, page 1 ; devise des cellules à valider"
balance = load("balance_multiyear")
assert balance["tables"][0]["rows"][:2] == [
    ["Rubrique", "2026", "2025"],
    ["Total actif", "1 200", "900"],
]
assert balance["fields"]["total_assets"]["status"] == "ambiguous_requires_review"
assert "unit_scale_requires_review_amounts_remain_as_printed" in balance["warnings"]
candidates = balance["fields"]["total_assets"]["candidates"]
assert all(c["normalized"] is None for c in candidates)
cells = next(c["cells"] for c in candidates if c["method"] == "native_table")
assert [c["normalized"]["amount_as_printed"] for c in cells] == ["1200", "900"]
assert all(c["normalized"]["unit_multiplier"] is None for c in cells)
report["balance_multiyear"] = (
    "Colonnes 2026/2025 distinctes : 1200/900 ; échelle inconnue, revue requise"
)
form = load("form")
assert form["form_fields"][0]["name"] == "montant_demande"
assert form["form_fields"][0]["value"] == "150000"
assert form["form_fields"][0]["page"] == 1
assert form["form_fields"][0]["status"] == "extracted_unverified"
report["form"] = "AcroForm montant_demande=150000, page 1, aucun mapping financier automatique"
report["payslip_scan_fra"] = salary("payslip_scan_fra", "ocr")
batch = json.loads((OUTPUT / "batch/manifest_results.json").read_text())["results"]
assert len(batch) == 132 and all(item["status"] == "extracted_unverified" for item in batch)
report["batch"] = "132/132 documents sans échec"
(OUTPUT / "verification.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
print(json.dumps(report, indent=2, ensure_ascii=False))
