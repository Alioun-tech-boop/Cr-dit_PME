"""PDF -> preuves textuelles, tableaux, champs et candidats métier.

Tous les candidats sont non vérifiés. Les règles ne lisent pas des scans comme
une autorité administrative et n'alimentent pas automatiquement un score.
"""
import csv
import hashlib
import io
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fitz
import pdfplumber

from . import __version__
from .catalog import CATALOG

MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 100
MAX_PIXELS = 20_000_000


class ExtractionError(ValueError):
    pass


def fold(text):
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower().replace("’", "'")


def normalize_money(raw):
    """Valeur imprimée uniquement : ni unité implicite, ni taux de change."""
    match = re.search(r"(?<![\w])[-−]?\s*\(?\d[\d\s\u00a0\u202f.,]*\)?", raw)
    if not match:
        return None
    token = re.sub(r"\s", "", match.group()).replace("−", "-").rstrip(".,")
    negative = token.startswith("(") and token.endswith(")")
    token = token.strip("()")
    # Un séparateur suivi de trois chiffres est ambigu (1,234 / 1.234).
    if re.fullmatch(r"-?\d+[.,]\d{3}", token):
        return {"amount_as_printed": None, "ambiguous": True, "raw_number": token,
                "reason": "decimal_or_thousands_separator"}
    if "," in token and "." in token:
        return {"amount_as_printed": None, "ambiguous": True, "raw_number": token,
                "reason": "mixed_separators"}
    if token.count(",") > 1 or token.count(".") > 1:
        return {"amount_as_printed": None, "ambiguous": True, "raw_number": token,
                "reason": "multiple_separators"}
    token = token.replace(",", ".")
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    if negative:
        value = -value
    currency = None
    if re.search(r"\b(?:FCFA|F\s*CFA|XOF)\b", raw, re.I):
        currency = "XOF"
    elif re.search(r"\bEUR\b|€", raw):
        currency = "EUR"
    elif re.search(r"\bUSD\b|\$", raw):
        currency = "USD"
    return {"amount_as_printed": str(value), "currency": currency,
            "ambiguous": False, "unit_multiplier": None}


def normalize_value(raw, kind):
    if kind == "money":
        return normalize_money(raw)
    if kind == "date":
        token = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4})\b", raw)
        if not token:
            return None
        text = token.group()
        fmt = "%Y-%m-%d" if re.match(r"\d{4}-", text) else "%d/%m/%Y"
        if fmt != "%Y-%m-%d":
            text = re.sub(r"[.-]", "/", text)
        try:
            value = datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            return None
        return {"value": value, "convention": "ISO_or_day_month_year_requires_review"}
    if kind == "rate":
        m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", raw)
        return {"percent": m.group(1).replace(",", ".")} if m else None
    if kind == "currency":
        if re.search(r"\b(?:FCFA|XOF|F\s*CFA)\b", raw, re.I):
            return "XOF"
        return raw.strip() or None
    return raw.strip() or None


def native_lines(page):
    words = sorted(page.get_text("words"), key=lambda w: (w[1], w[0]))
    groups = []
    for w in words:
        if not groups or abs(groups[-1][0][1] - w[1]) > 3:
            groups.append([w])
        else:
            groups[-1].append(w)
    lines = []
    for group in groups:
        group.sort(key=lambda w: w[0])
        text = group[0][4]
        for before, after in zip(group, group[1:]):
            text += ("  " if after[0] - before[2] > 12 else " ") + after[4]
        lines.append({"text": text,
                      "bbox": [min(w[0] for w in group), min(w[1] for w in group),
                               max(w[2] for w in group), max(w[3] for w in group)],
                      "method": "native", "ocr_confidence": None})
    return lines


def ocr_lines(page, lang):
    executable = shutil.which("tesseract")
    if not executable:
        return [], "ocr_unavailable_tesseract_missing"
    languages = subprocess.run([executable, "--list-langs"], capture_output=True,
                               text=True, timeout=10)
    available = set(languages.stdout.splitlines()[1:])
    if not set(lang.split("+")).issubset(available):
        return [], "ocr_languages_missing:" + lang
    scale = 2.0
    if page.rect.width * page.rect.height * scale ** 2 > MAX_PIXELS:
        return [], "ocr_pixel_limit"
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    with tempfile.TemporaryDirectory(prefix="credit_pdf_") as tmp:
        path = Path(tmp) / "page.png"
        pix.save(path)
        try:
            result = subprocess.run([executable, str(path), "stdout", "-l", lang,
                                     "--psm", "3", "tsv"], capture_output=True,
                                    text=True, timeout=45)
        except subprocess.TimeoutExpired:
            return [], "ocr_timeout"
    if result.returncode != 0:
        return [], "ocr_failed"
    groups = {}
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        if row.get("level") != "5" or not row.get("text", "").strip():
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        groups.setdefault(key, []).append(row)
    lines = []
    for group in groups.values():
        x0 = min(int(w["left"]) for w in group)
        y0 = min(int(w["top"]) for w in group)
        x1 = max(int(w["left"]) + int(w["width"]) for w in group)
        y1 = max(int(w["top"]) + int(w["height"]) for w in group)
        lines.append({"text": " ".join(w["text"] for w in group),
                      "bbox": [x0 / scale, y0 / scale, x1 / scale, y1 / scale],
                      "method": "ocr",
                      "ocr_confidence": round(sum(float(w["conf"]) for w in group) / len(group), 2)})
    return lines, None


def classification(text):
    text = fold(text)
    ranked = []
    for key, profile in CATALOG.items():
        title = fold(profile["title"])
        # Titres entiers seulement : aucun pseudo modèle prédictif.
        if re.search(r"(?<!\w)" + re.escape(title) + r"(?!\w)", text):
            ranked.append({"document_type": key, "basis": "exact_title_phrase",
                           "matched_title": profile["title"]})
    return ranked


TABLE_HEADERS = {
    "transaction_date": ("date", "date operation", "date d'operation", "date opération"),
    "value_date": ("date valeur", "date de valeur"),
    "description": ("libelle", "libellé", "designation", "désignation", "description"),
    "debit": ("debit", "débit", "sortie", "décaissement"),
    "credit": ("credit", "crédit", "entree", "entrée", "encaissement"),
    "balance": ("solde",),
    "due_date": ("echeance", "échéance", "date echeance", "date d'échéance"),
    "principal": ("capital", "principal", "amortissement"),
    "interest": ("interets", "intérêts"),
    "fees": ("frais",),
    "instalment": ("mensualite", "mensualité", "total échéance"),
    "outstanding": ("capital restant du", "capital restant dû", "crd"),
    "counterparty": ("client", "fournisseur", "contrepartie"),
    "quantity": ("quantite", "quantité", "effectif"),
    "unit_price": ("prix unitaire", "pu"),
    "amount": ("montant", "total", "valeur"),
    "loan_id": ("identifiant crédit", "identifiant du crédit", "numero de pret", "numéro de prêt"),
    "borrower_id": ("identifiant client", "identifiant emprunteur"),
    "payment_date": ("date paiement", "date du paiement", "date de remboursement"),
    "payment_amount": ("montant payé", "montant reçu"),
    "days_past_due": ("jours de retard", "retard"),
    "decision": ("decision", "décision"),
    "year": ("annee", "année", "exercice"),
}


def structure_table(table):
    """Mapping prudent des en-têtes explicites. Les tableaux bruts sont conservés."""
    mapping = None
    header_index = None
    for i, row in enumerate(table["rows"][:4]):
        current = []
        for column, cell in enumerate(row):
            key = next((key for key, aliases in TABLE_HEADERS.items()
                        if cell and fold(cell.strip()) in [fold(a) for a in aliases]), None)
            if key:
                current.append({"column": column, "key": key, "header": cell})
        if len(current) >= 2:
            mapping, header_index = current, i
            break
    if not mapping:
        return {"status": "raw_table_requires_mapping", "columns": [], "records": []}
    records = []
    for index, row in enumerate(table["rows"][header_index+1:], header_index+1):
        cells = []
        for column in mapping:
            raw = row[column["column"]] if column["column"] < len(row) else None
            key = column["key"]
            if key in {"transaction_date", "due_date", "payment_date", "value_date"}:
                kind = "date"
            elif key in {"debit", "credit", "balance", "principal", "interest", "fees",
                         "instalment", "outstanding", "amount", "unit_price", "payment_amount"}:
                kind = "money"
            else:
                kind = "text"
            cells.append({**column, "raw": raw,
                          "normalized": normalize_value(raw, kind) if raw else None,
                          "status": "extracted_unverified" if raw else "not_found"})
        records.append({"row": index, "cells": cells})
    return {"status": "header_candidates_require_review", "columns": mapping, "records": records}


def extract_fields(profile, lines, tables):
    fields = {}
    for field in profile["fields"]:
        candidates = []
        aliases = sorted(field.aliases, key=len, reverse=True)
        for line in lines:
            for alias in aliases:
                # Début de ligne pour ne pas interpréter une mention narrative.
                match = re.match(r"^\s*" + re.escape(fold(alias)) + r"\s*(?::|=|\||\s)\s*(.*)$", fold(line["text"]))
                if not match or not match.group(1).strip():
                    continue
                raw = line["text"][match.start(1):].strip()
                normalized = normalize_value(raw, field.kind)
                candidate = {"raw": raw, "normalized": normalized,
                             "evidence_id": line["id"], "page": line["page"],
                             "bbox": line["bbox"], "method": line["method"],
                             "status": "extracted_unverified"}
                if field.kind == "money":
                    values = re.findall(r"-?\(?\d[\d\s\u00a0\u202f.,]*\)?", raw)
                    candidate["multiple_values_possible"] = len(values) > 1 or bool(re.search(r"\d\s{2,}\d", raw))
                    if candidate["multiple_values_possible"]:
                        candidate["normalized"] = None
                candidates.append(candidate)
                break
        # Préserve les colonnes distinctes, surtout N / N-1 des états financiers.
        for table in tables:
            for index, row in enumerate(table["rows"]):
                if len(row) < 2 or not row[0]:
                    continue
                if fold(row[0].strip().rstrip(":")) not in [fold(a) for a in aliases]:
                    continue
                cells = []
                for column, value in enumerate(row[1:], 1):
                    if value:
                        cells.append({"column": column, "raw": value,
                                      "normalized": normalize_value(value, field.kind)})
                if cells:
                    candidates.append({"raw": " | ".join(c["raw"] for c in cells),
                                       "normalized": cells[0]["normalized"] if len(cells) == 1 else None,
                                       "cells": cells, "table_id": table["id"], "row": index,
                                       "evidence_id": table["id"], "page": table["page"],
                                       "bbox": table["bbox"], "method": "native_table",
                                       "status": "extracted_unverified"})
        status = "not_found" if not candidates else "extracted_unverified"
        if len(candidates) > 1 or any(c.get("multiple_values_possible") or
                (isinstance(c.get("normalized"), dict) and c["normalized"].get("ambiguous")) or
                len(c.get("cells", [])) > 1 for c in candidates):
            status = "ambiguous_requires_review"
        fields[field.key] = {"kind": field.kind, "status": status, "candidates": candidates}
    return fields


def extract_pdf(data, document_type=None, *, ocr="auto", lang="fra", password=None):
    if not data or len(data) > MAX_BYTES:
        raise ExtractionError("empty_or_file_too_large")
    if not data.startswith(b"%PDF-"):
        raise ExtractionError("invalid_pdf_signature")
    if document_type and document_type not in CATALOG:
        raise ExtractionError("unknown_document_type")
    if ocr not in {"auto", "always", "never"}:
        raise ExtractionError("invalid_ocr_mode")
    if not re.fullmatch(r"[A-Za-z_]+(?:\+[A-Za-z_]+)*", lang):
        raise ExtractionError("invalid_ocr_language")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ExtractionError("unreadable_pdf") from exc
    try:
        if doc.needs_pass and not doc.authenticate(password or ""):
            raise ExtractionError("password_required_or_invalid")
        if not 0 < len(doc) <= MAX_PAGES:
            raise ExtractionError("page_limit_exceeded")
        pages, lines, forms, tables, warnings = [], [], [], [], []
        try:
            plumber = pdfplumber.open(io.BytesIO(data), password=password)
        except Exception:
            plumber = None
            warnings.append("native_table_reader_unavailable")
        try:
            for i, page in enumerate(doc, 1):
                current = native_lines(page)
                image_area = sum(fitz.Rect(image["bbox"]).get_area() for image in page.get_image_info())
                has_big_image = image_area > page.rect.get_area() * 0.30
                needs_ocr = ocr == "always" or (ocr == "auto" and
                            (sum(len(l["text"]) for l in current) < 60 or has_big_image))
                if needs_ocr:
                    found, warning = ocr_lines(page, lang)
                    if warning:
                        warnings.append(f"page_{i}:{warning}")
                    if found:
                        existing = {fold(l["text"]) for l in current}
                        current += [l for l in found if fold(l["text"]) not in existing]
                        warnings.append(f"page_{i}:ocr_requires_visual_review")
                for index, line in enumerate(current):
                    line.update(id=f"p{i}:l{index + 1}", page=i)
                lines.extend(current)
                page_text = "\n".join(l["text"] for l in current)
                pages.append({"page": i, "width": page.rect.width, "height": page.rect.height,
                              "text": page_text, "evidence_ids": [l["id"] for l in current],
                              "type_candidates": classification(page_text),
                              "needs_review": needs_ocr or not bool(current)})
                for index, widget in enumerate(page.widgets() or [], 1):
                    forms.append({"id": f"p{i}:f{index}", "page": i,
                                  "name": widget.field_name, "value": widget.field_value,
                                  "field_type": widget.field_type_string,
                                  "bbox": list(widget.rect), "status": "extracted_unverified"})
                    if widget.field_type_string == "Signature":
                        warnings.append("signature_present_not_validated")
                if plumber:
                    try:
                        for index, table in enumerate(plumber.pages[i-1].find_tables(), 1):
                            item = {"id": f"p{i}:t{index}", "page": i,
                                    "bbox": list(table.bbox), "rows": table.extract(),
                                    "status": "extracted_unverified"}
                            item["structured"] = structure_table(item)
                            tables.append(item)
                    except Exception:
                        warnings.append(f"page_{i}:native_table_extraction_failed")
        finally:
            if plumber:
                plumber.close()
        text = "\n".join(p["text"] for p in pages)
        candidates = classification(text)
        selected = document_type
        if not selected and len(candidates) == 1:
            selected = candidates[0]["document_type"]
        if not selected:
            warnings.append("document_type_requires_selection")
        if len(candidates) > 1:
            warnings.append("multiple_document_types_or_mentions_manual_routing_required")
        unit_hints = re.findall(r".{0,25}(?:milliers|millions|milliards|FCFA|XOF|USD|EUR).{0,25}", text, re.I)
        if re.search(r"milliers|millions|milliards", text, re.I):
            warnings.append("unit_scale_requires_review_amounts_remain_as_printed")
        if any(l["method"] == "ocr" for l in lines):
            warnings.append("ocr_tables_preserved_as_lines_no_certified_cell_reconstruction")
        fields = extract_fields(CATALOG[selected], lines, tables) if selected else {}
        warnings.extend(["extraction_is_not_authenticity_verification",
                         "not_found_means_label_not_detected_not_document_absence",
                         "no_automatic_credit_scoring_or_training_ingestion"])
        return {"schema_version": "credit-pme.pdf.v1", "engine_version": __version__,
                "document_sha256": hashlib.sha256(data).hexdigest(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "document_type": selected, "type_selection": "explicit" if document_type else "title_heuristic",
                "type_candidates": candidates, "page_count": len(pages),
                "pages": pages, "evidence": lines, "tables": tables, "form_fields": forms,
                "fields": fields, "unit_hints": unit_hints,
                "warnings": sorted(set(warnings)), "review_status": "pending",
                "ready_for_scoring": False}
    finally:
        doc.close()
