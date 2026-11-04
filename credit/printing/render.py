"""Deux rendus du même contrat, sans accès au dossier ni calcul métier."""

import base64
from html import escape
from io import BytesIO
from pathlib import Path
import re

from credit.printing.contracts import Presentation

CSS = """
@page {size:A4; margin:19mm 16mm 20mm;}
*{box-sizing:border-box}body{font-family:Arial,sans-serif;font-size:10pt;line-height:1.4;color:#171717;margin:24px auto;max-width:185mm;padding:0 6mm}
h1{font-size:22pt}h2{font-size:14pt;border-bottom:1px solid #555;padding-bottom:3mm;break-after:avoid}h3{break-after:avoid}
table{width:100%;border-collapse:collapse;margin:4mm 0;table-layout:fixed}thead{display:table-header-group}tr{break-inside:avoid}th,td{border:1px solid #888;padding:2mm;vertical-align:top;text-align:left;overflow-wrap:anywhere;white-space:pre-wrap}th{background:#eee}p{white-space:pre-wrap;overflow-wrap:anywhere;orphans:3;widows:3}
.metadata{font-size:9pt}.status{border:2px solid #333;padding:3mm;font-weight:bold}img{max-height:17mm;max-width:40mm}.signature{margin-top:12mm;min-height:24mm;border-top:1px solid #555}.tools{padding:4mm;border:1px solid #aaa}footer{font-size:8pt;border-top:1px solid #888;margin-top:8mm}
@media print{body{margin:0;max-width:none;padding:0}.tools{display:none}a{color:inherit;text-decoration:none}h2{break-after:avoid}}
"""


def html_document(model: Presentation):
    e = escape
    fragments = [
        f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(model.title)}</title><style>{CSS}</style></head><body>',
        '<nav class="tools">Aperçu imprimable — utilisez la commande Imprimer du navigateur (Ctrl+P). Aucune impression automatique.</nav>',
    ]
    if model.logo_png:
        fragments.append(
            f'<img alt="Logo configuré de la plateforme" src="data:image/png;base64,{model.logo_png}">'
        )
    fragments += [
        f'<header><p>{e(model.platform_name)}</p><h1>{e(model.title)}</h1><p class="status">{e(model.status)}</p></header>'
    ]
    fragments.append(
        '<div class="metadata">'
        + "".join(f"<p><strong>{e(k)}</strong> : {e(v)}</p>" for k, v in model.metadata.items())
        + "</div>"
    )
    fragments += [f"<p><strong>{e(n)}</strong></p>" for n in model.notices]
    for s in model.sections:
        fragments.append(f"<section><h2>{e(s.title)}</h2>")
        fragments += [f"<p>{e(p)}</p>" for p in s.paragraphs]
        for t in s.tables:
            if not t.rows:
                continue
            fragments.append(
                "<table><thead><tr>"
                + "".join(f"<th>{e(c)}</th>" for c in t.columns)
                + "</tr></thead><tbody>"
            )
            for row in t.rows:
                fragments.append("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>")
            fragments.append("</tbody></table>")
        fragments.append("</section>")
    if model.signatures:
        fragments.append(
            '<div class="signature">Lieu et date : ____________________<br>Signature manuscrite éventuelle : ____________________<br>Zone volontairement vierge — aucune signature recueillie ni certifiée.</div>'
        )
    fragments.append(
        "<footer>Édition conservée — aucun partage automatique. Pour la pagination garantie, utiliser le PDF téléchargé.</footer></body></html>"
    )
    return "".join(fragments)


def chunks(text, size=800):
    text = str(text)
    # Longues chaînes et commentaires restent tous présents ; pas de troncature silencieuse.
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def pdf_document(model: Presentation, max_pages=120):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        LongTable,
        TableStyle,
        Image,
        KeepTogether,
    )

    fontdir = Path(reportlab.__file__).parent / "fonts"
    if "CreditSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("CreditSans", str(fontdir / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("CreditSans-Bold", str(fontdir / "VeraBd.ttf")))
        pdfmetrics.registerFontFamily(
            "CreditSans",
            normal="CreditSans",
            bold="CreditSans-Bold",
            italic="CreditSans",
            boldItalic="CreditSans-Bold",
        )
    body = ParagraphStyle(
        "body",
        fontName="CreditSans",
        fontSize=9,
        leading=12,
        spaceAfter=5,
        wordWrap="CJK",
        alignment=TA_LEFT,
    )
    cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=10, spaceAfter=0)
    head = ParagraphStyle(
        "head",
        parent=body,
        fontName="CreditSans-Bold",
        fontSize=13,
        leading=17,
        spaceBefore=12,
        spaceAfter=7,
        keepWithNext=True,
    )
    title = ParagraphStyle("title", parent=head, fontSize=20, leading=24)

    def p(text, style=body):
        # Les utilisateurs ne peuvent pas injecter le mini-HTML de ReportLab.
        clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text))
        return Paragraph(escape(clean).replace("\n", "<br/>"), style)

    def paragraphs(text, style=body):
        return [p(v, style) for v in chunks(text, 1600)]

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.saved = []

        def showPage(self):
            if len(self.saved) >= max_pages:
                raise ValueError("print_page_limit")
            self.saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            count = len(self.saved)
            for state in self.saved:
                self.__dict__.update(state)
                self.setFont("CreditSans", 7)
                self.setFillColor(colors.black)
                self.drawString(16 * mm, 285 * mm, model.platform_name[:70])
                self.drawRightString(194 * mm, 285 * mm, "Dossier " + model.metadata["Dossier"])
                self.line(16 * mm, 16 * mm, 194 * mm, 16 * mm)
                self.drawString(16 * mm, 12 * mm, "Édition " + model.metadata["Édition"])
                self.drawRightString(194 * mm, 12 * mm, f"Page {self._pageNumber} / {count}")
                super().showPage()
            super().save()

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
        title=model.title,
        author=model.platform_name,
        pageCompression=1,
    )
    story = []
    if model.logo_png:
        image = Image(BytesIO(base64.b64decode(model.logo_png)))
        image._restrictSize(40 * mm, 17 * mm)
        story += [image, Spacer(1, 4 * mm)]
    story += [p(model.title, title), p(model.status, head)]
    for key, value in model.metadata.items():
        story += paragraphs(key + " : " + value)
    for notice in model.notices:
        story += paragraphs(notice)
    for section in model.sections:
        story.append(p(section.title, head))
        for text in section.paragraphs:
            story += paragraphs(text)
        for table in section.tables:
            if not table.rows:
                continue
            data = [[p(c, cell) for c in table.columns]]
            for row in table.rows:
                split = [chunks(c) for c in row]
                for i in range(max(map(len, split))):
                    data.append([p(parts[i] if i < len(parts) else "", cell) for parts in split])
            weights = (
                [0.38, 0.62]
                if len(table.columns) == 2
                else [1 / len(table.columns)] * len(table.columns)
            )
            widths = [doc.width * w for w in weights]
            rendered = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
            rendered.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story += [rendered, Spacer(1, 3 * mm)]
    if model.signatures:
        story.append(
            KeepTogether(
                [
                    Spacer(1, 10 * mm),
                    p("Lieu et date : ____________________"),
                    p("Signature manuscrite éventuelle : ____________________"),
                    p("Zone volontairement vierge — aucune signature recueillie ni certifiée."),
                    Spacer(1, 12 * mm),
                ]
            )
        )
    doc.build(story, canvasmaker=NumberedCanvas)
    return output.getvalue()
