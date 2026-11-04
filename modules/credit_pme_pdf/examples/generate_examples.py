"""Pièces 100 % synthétiques, sans personnes ni institutions réelles."""
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
import fitz

from credit_pdf.catalog import CATALOG, public_catalog


def make_pdf(title, lines=(), table=None, form=False):
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(595, 842))
    c.setTitle("SPECIMEN SYNTHETIQUE - " + title)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, 805, "SPECIMEN SYNTHETIQUE - AUCUNE VALEUR OFFICIELLE")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 780, title)
    c.setFont("Helvetica", 10)
    y = 750
    for line in lines:
        c.drawString(40, y, line)
        y -= 22
    if table:
        widths = [120] + [100] * (len(table[0])-1)
        t = Table(table, colWidths=widths)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                               ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))
        w, h = t.wrap(520, y)
        t.drawOn(c, 40, y-h-10)
    if form:
        c.acroForm.textfield(name="montant_demande", value="150000", x=40, y=350,
                            width=180, height=24, forceBorder=True)
    c.showPage()
    c.save()
    return stream.getvalue()


def scanned_pdf(data):
    native = fitz.open(stream=data, filetype="pdf")
    pix = native[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    result = fitz.open()
    page = result.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    value = result.tobytes()
    result.close()
    native.close()
    return value


def main():
    root = Path(__file__).resolve().parent
    pdfs = root / "pdf"
    pdfs.mkdir(exist_ok=True)
    manifest = []
    for key, profile in CATALOG.items():
        specific = next(f for f in profile["fields"] if f.key not in
                        {"subject_name", "document_date", "period", "currency", "reference"})
        values = {"text": "SPECIMEN-001", "money": "250 000 FCFA",
                  "date": "04/11/2026", "rate": "8,5 %", "currency": "XOF"}
        data = make_pdf(profile["title"], ["Raison sociale: ENTREPRISE SPECIMEN",
                        "Date du document: 04/11/2026", "Devise: XOF",
                        specific.aliases[0] + ": " + values[specific.kind]])
        (pdfs / f"{key}.pdf").write_bytes(data)
        manifest.append({"path": f"pdf/{key}.pdf", "document_type": key})
    salary = make_pdf("Bulletin de salaire", ["Nom du salarié: PERSONNE SPECIMEN",
                     "Période: octobre 2026", "Salaire brut: 350 000 FCFA",
                     "Net à payer: 280 000 FCFA", "Retenue prêt: 20 000 FCFA"])
    (pdfs / "payslip_detail.pdf").write_bytes(salary)
    (pdfs / "payslip_scan.pdf").write_bytes(scanned_pdf(salary))
    statement = make_pdf("Relevé bancaire", ["Solde initial: 100 000 FCFA"],
                        [["Date", "Libellé", "Débit", "Crédit"],
                         ["01/10/2026", "Versement", "", "280 000"],
                         ["02/10/2026", "Loyer", "60 000", ""]])
    (pdfs / "bank_table.pdf").write_bytes(statement)
    annual = make_pdf("Bilan", ["Montants en milliers de FCFA"],
                      [["Rubrique", "2026", "2025"], ["Total actif", "1 200", "900"],
                       ["Capitaux propres", "500", "400"]])
    (pdfs / "balance_multiyear.pdf").write_bytes(annual)
    (pdfs / "form.pdf").write_bytes(make_pdf("Demande de crédit", form=True))
    (root / "manifest.json").write_text(json.dumps({"documents": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    docs = root.parent / "docs"
    (docs / "catalog.json").write_text(json.dumps(public_catalog(), ensure_ascii=False, indent=2), encoding="utf-8")
    with (docs / "coverage.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["document_type", "document", "famille", "destination", "champs_recherches", "niveau"])
        for p in CATALOG.values():
            writer.writerow([p["id"], p["title"], p["family"], p["target"],
                             " | ".join(f.key for f in p["fields"]),
                             "Texte/tableaux/formulaires/OCR; candidats à valider"])
    print(f"{len(CATALOG)} profils et {len(CATALOG)+5} PDF synthétiques générés")


if __name__ == "__main__":
    main()
