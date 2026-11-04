"""Génère uniquement des pièces synthétiques pour les contrôles de dépôt."""

from pathlib import Path
import io

import fitz
from PIL import Image, ImageFilter

ROOT = Path(__file__).parent
PDFS = ROOT.parents[1] / "modules/credit_pme_pdf/examples/pdf"
with fitz.open(PDFS / "payslip_detail.pdf") as pdf:
    page = pdf[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    image.save(ROOT / "salary.png")
    image.save(ROOT / "salary.jpg", quality=95)
    image.filter(ImageFilter.GaussianBlur(8)).save(ROOT / "blurred.png")
    rotated = image.rotate(90, expand=True)
    exif = Image.Exif()
    exif[274] = 6
    rotated.save(ROOT / "exif_salary.jpg", exif=exif, quality=95)
Image.new("RGB", (800, 1100), "white").save(ROOT / "blank.png")
with fitz.open() as pdf:
    page = pdf.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=str(ROOT / "salary.png"))
    page.insert_text(
        (40, 160), "Net a payer: 280 000 FCFA - couche OCR synthetique non verifiee", render_mode=3
    )
    pdf.save(ROOT / "scan_with_ocr_layer.pdf")
with fitz.open() as pdf:
    page = pdf.new_page(width=595, height=842)
    page.insert_text((40, 80), "Document natif synthetique avec texte et montant: 280000 XOF")
    page = pdf.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(0, 0, 595, 500), filename=str(ROOT / "salary.png"))
    page.insert_text(
        (40, 700), "Annotation native synthetique : verifier les montants et les bords"
    )
    page = pdf.new_page(width=595, height=842)
    pdf.save(ROOT / "mixed_multipage.pdf")
with fitz.open() as pdf:
    page = pdf.new_page(width=595, height=842)
    page.insert_text(
        (40, 80), "Rapport natif synthetique avec un petit logo et des chiffres 123456"
    )
    stream = io.BytesIO()
    Image.new("RGB", (100, 100), "gray").save(stream, format="PNG")
    page.insert_image(fitz.Rect(20, 20, 60, 60), stream=stream.getvalue())
    pdf.save(ROOT / "native_with_logo.pdf")
print("Pièces synthétiques générées dans", ROOT)
