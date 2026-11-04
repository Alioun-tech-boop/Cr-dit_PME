"""Worker éphémère : aucun accès à la base ; limites de ressources et de durée côté parent."""

import json
import os
import resource
import sys
from pathlib import Path


def document_quality(document, config):
    import hashlib
    from credit.documents.imaging import quality, render

    values = []
    seen = set()
    for index, page in enumerate(document, 1):
        image = render(page)
        value = quality(image, config, orientation=False)
        digest = hashlib.sha256(image.tobytes() + str(image.size).encode()).hexdigest()
        if digest in seen:
            value["issues"].append(
                {
                    "code": "exact_duplicate",
                    "severity": "warning",
                    "message": "Cette page est identique à une page déjà ajoutée.",
                }
            )
            if value["status"] == "pass":
                value["status"] = "warnings"
        seen.add(digest)
        value["page_number"] = index
        for issue in value["issues"]:
            issue["message"] = f"Page {index} : " + issue["message"]
        values.append(value)
    return values


def main():
    job = json.loads(Path(sys.argv[1]).read_text())
    limits = job["limits"]
    resource.setrlimit(resource.RLIMIT_AS, (limits["memory_mb"] * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (limits["timeout_seconds"],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2,) * 2)
    from credit.documents.imaging import inspect, build, render, provenance
    from credit_pdf.engine import extract_pdf
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = limits["max_pixels"]
    args = job["parameters"]
    root = Path(sys.argv[2]).parent
    if job["operation"] == "inspect":
        return inspect(Path(job["sources"]["input"]["path"]).read_bytes(), limits, args["quality"])
    if job["operation"] == "sleep_for_test":
        import time

        time.sleep(args["seconds"])
        return {}
    if job["operation"] == "render_run":
        import fitz

        with fitz.open(job["sources"]["input"]["path"]) as document:
            render(document[args["page_index"]]).save(root / "preview.png")
        return {"preview_png": "preview.png"}
    document, mappings = build(job["sources"], args["pages"])
    try:
        if job["operation"] == "preview":
            page = document[args.get("page_index", 0)]
            render(page).save(root / "preview.png")
            return {"preview_png": "preview.png"}
        payload = document.tobytes(garbage=4, deflate=True)
        (root / "derivative.pdf").write_bytes(payload)
        if job["operation"] == "prepare":
            return {
                "derivative_pdf": "derivative.pdf",
                "mappings": mappings,
                "quality": document_quality(document, args["quality"]),
            }
        extracted = extract_pdf(payload, args["document_type"], ocr="auto", lang="fra")
        from credit.documents.geometry import rectangle

        for mapping in mappings:
            for index, field in enumerate(mapping.get("source_form_fields", []), 1):
                extracted["form_fields"].append(
                    {
                        "id": f"p{mapping['processing_page']}:source_form_{index}",
                        "page": mapping["processing_page"],
                        "bbox": rectangle(mapping["canonical_to_processing"], field["bbox"]),
                        "name": field["name"],
                        "value": field["value"],
                        "field_type": field["field_type"],
                        "status": "extracted_unverified",
                    }
                )
                if field["field_type"] == "Signature":
                    extracted["warnings"].append("signature_present_not_validated")
        extracted = provenance(extracted, mappings)
        return {
            "derivative_pdf": "derivative.pdf",
            "extraction": extracted,
            "mappings": mappings,
            "quality": document_quality(document, args["quality"]),
        }
    finally:
        document.close()


if __name__ == "__main__":
    os.umask(0o077)
    try:
        answer = main()
    except ValueError as exc:
        # Les seules ValueError exposées sont les codes contrôlés des modules.
        allowed = {
            "file_size_limit",
            "format_not_supported",
            "pixel_limit_exceeded",
            "animated_image_not_supported",
            "image_decode_failed",
            "pdf_decode_failed",
            "encrypted_pdf_not_supported",
            "page_limit_exceeded",
            "empty_or_file_too_large",
            "invalid_pdf_signature",
            "unreadable_pdf",
            "password_required_or_invalid",
        }
        answer = {"error": str(exc) if str(exc) in allowed else "document_processing_failed"}
    except Exception:
        answer = {"error": "document_processing_failed"}
    Path(sys.argv[2]).write_text(json.dumps(answer, ensure_ascii=False))
