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


def verification_qr(url):
    from urllib.parse import urlparse
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or len(url) > 500:
        raise ValueError("invalid_verification_url")
    widget = QrCodeWidget(url)
    x, y, right, bottom = widget.getBounds()
    drawing = Drawing(110, 110, transform=[110 / (right - x), 0, 0, 110 / (bottom - y), 0, 0])
    drawing.add(widget)
    return drawing


def html_document(model: Presentation):
    e = escape
    fragments = [
        f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(model.title)}</title><style>{CSS}</style></head><body>',
        '<nav class="tools">Aperçu imprimable — utilisez la commande Imprimer du navigateur (Ctrl+P). Aucune impression automatique.</nav>',
    ]
    if model.verification_url:
        from reportlab.graphics import renderSVG

        qr = base64.b64encode(
            renderSVG.drawToString(verification_qr(model.verification_url)).encode()
        ).decode()
        fragments.append(
            '<p>Vérification du statut : <a href="'
            + e(model.verification_url)
            + '">'
            + e(model.verification_url)
            + '</a></p><img alt="QR de vérification, pas une signature" src="data:image/svg+xml;base64,'
            + qr
            + '">'
        )
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
    """Compose le PDF final avec le moteur LaTeX institutionnel."""
    from credit.printing.latex import latex_pdf_document

    return latex_pdf_document(model, max_pages)
