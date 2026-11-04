"""Décodage et mesures techniques, uniquement dans les processus de traitement."""

import hashlib
import io
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz
from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

from credit.documents.geometry import compose, inverse, rectangle, transform


def image_open(payload, limits):
    try:
        image = Image.open(io.BytesIO(payload))
        if image.format not in {"JPEG", "PNG"}:
            raise ValueError("format_not_supported")
        if image.width * image.height > limits["max_pixels"]:
            raise ValueError("pixel_limit_exceeded")
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("animated_image_not_supported")
        image.load()
        return image
    except Image.DecompressionBombError as exc:
        raise ValueError("pixel_limit_exceeded") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("image_decode_failed") from exc


def rgb(image):
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        result = Image.new("RGB", image.size, "white")
        image = image.convert("RGBA")
        result.paste(image, mask=image.getchannel("A"))
        return result
    return image.convert("RGB")


def quality(image, config, orientation=True):
    width, height = image.size
    gray = image.convert("L")
    gray.thumbnail((256, 256))
    pixels = list(gray.tobytes())
    w, h = gray.size
    stats = ImageStat.Stat(gray)
    ink = sum(p < config.get("ink_cutoff", 245) for p in pixels)
    laps = [
        4 * pixels[y * w + x]
        - pixels[y * w + x - 1]
        - pixels[y * w + x + 1]
        - pixels[(y - 1) * w + x]
        - pixels[(y + 1) * w + x]
        for y in range(1, h - 1)
        for x in range(1, w - 1)
    ]
    mean = sum(laps) / len(laps) if laps else 0
    variance = sum((p - mean) ** 2 for p in laps) / len(laps) if laps else 0
    band = max(1, int(min(w, h) * config["edge_band_fraction"]))
    edge = sum(
        pixels[y * w + x] < config.get("ink_cutoff", 245)
        for y in range(h)
        for x in range(w)
        if x < band or y < band or x >= w - band or y >= h - band
    )
    metrics = {
        "decoded": True,
        "width_pixels": width,
        "height_pixels": height,
        "contrast_stddev": stats.stddev[0],
        "mean_luminance": stats.mean[0],
        "laplacian_variance_at_256": variance,
        "ink_fraction": ink / len(pixels),
        "edge_ink_fraction": edge / max(1, ink),
        "orientation": {"status": "not_determined", "suggested_clockwise_rotation": None},
    }
    issues = []

    def issue(code, severity, message):
        issues.append({"code": code, "severity": severity, "message": message})

    if min(width, height) < config["min_side_blocking"]:
        issue("dimensions_unusable", "error", "Dimensions insuffisantes pour traiter cette page.")
    elif min(width, height) < config["min_side_warning"]:
        issue(
            "low_resolution",
            "warning",
            "La résolution est faible ; vérifiez la lisibilité des montants.",
        )
    if metrics["ink_fraction"] < config["blank_ink_fraction"]:
        issue(
            "blank_page",
            "error",
            "Cette page semble vide ; ajoutez une page lisible ou supprimez-la.",
        )
    if (
        stats.stddev[0] < config.get("uniform_contrast_blocking", 1)
        and metrics["ink_fraction"] >= config["blank_ink_fraction"]
    ):
        issue(
            "uniform_unusable",
            "error",
            "Cette page uniforme est inexploitable ; reprenez une image lisible.",
        )
    if stats.mean[0] < config.get("exposure_low", 25) or stats.mean[0] > config.get(
        "exposure_high", 250
    ):
        issue("exposure", "warning", "Vérifiez l’exposition et la lisibilité de la page.")
    if variance < config["blur_variance_warning"]:
        issue("blur", "warning", "Cette page est peut-être trop floue pour lire les montants.")
    if stats.stddev[0] < config["contrast_warning"]:
        issue(
            "contrast",
            "warning",
            "Le contraste ou l’exposition est insuffisant ; vérifiez les données.",
        )
    if metrics["edge_ink_fraction"] > config["edge_ink_warning"]:
        issue(
            "content_near_edge",
            "warning",
            "Vérifiez que les quatre bords du document sont visibles.",
        )
    if orientation and shutil.which("tesseract"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orientation.png"
            image.save(path)
            try:
                result = subprocess.run(
                    ["tesseract", str(path), "stdout", "--psm", "0", "-l", "osd"],
                    capture_output=True,
                    text=True,
                    timeout=config["orientation_timeout_seconds"],
                )
                match = re.search(r"Rotate: (\d+)", result.stdout)
                if result.returncode == 0 and match:
                    rotation = int(match[1])
                    metrics["orientation"] = {
                        "status": "suggestion_only",
                        "suggested_clockwise_rotation": rotation,
                    }
                    if rotation:
                        issue(
                            "orientation",
                            "warning",
                            f"Vérifiez l’orientation : rotation suggérée de {rotation} degrés.",
                        )
            except subprocess.TimeoutExpired:
                metrics["orientation"]["status"] = "timeout"
    return {
        "metrics": metrics,
        "issues": issues,
        "status": "blocked"
        if any(i["severity"] == "error" for i in issues)
        else "warnings"
        if issues
        else "pass",
    }


def render(page, maximum=4000000):
    scale = min(1.5, math.sqrt(maximum / max(1, page.rect.get_area())))
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def classify(page, config):
    area = max(1, page.rect.get_area())
    coverage = min(
        1, sum((fitz.Rect(i["bbox"]) & page.rect).get_area() for i in page.get_image_info()) / area
    )
    chars = len("".join(page.get_text().split()))
    if coverage >= config["scan_image_coverage"]:
        kind = "image_dominant"
    elif coverage >= config["mixed_image_coverage"] and chars >= config["native_text_chars"]:
        kind = "mixed"
    elif chars >= config["native_text_chars"]:
        kind = "native_text"
    elif coverage >= config["mixed_image_coverage"]:
        kind = "image_dominant"
    else:
        kind = "empty_or_unusable"
    return {
        "classification": kind,
        "image_coverage": coverage,
        "native_text_chars": chars,
        "scan_with_text_layer": coverage >= config["scan_image_coverage"] and chars > 0,
    }


def inspect(payload, limits, config):
    if not payload or len(payload) > limits["max_file_bytes"]:
        raise ValueError("file_size_limit")
    pages = []
    if payload.startswith(b"%PDF-"):
        try:
            doc = fitz.open(stream=payload, filetype="pdf")
        except Exception as exc:
            raise ValueError("pdf_decode_failed") from exc
        with doc:
            if doc.needs_pass:
                raise ValueError("encrypted_pdf_not_supported")
            if not 0 < len(doc) <= limits["max_pages"]:
                raise ValueError("page_limit_exceeded")
            for index, page in enumerate(doc):
                rotation = page.rotation
                page.set_rotation(0)
                if page.rect.get_area() * 4 > limits["max_pixels"]:
                    raise ValueError("pixel_limit_exceeded")
                for image in page.get_image_info():
                    if image["width"] * image["height"] > limits["max_pixels"]:
                        raise ValueError("pixel_limit_exceeded")
                bitmap = render(page)
                pages.append(
                    {
                        "source_page": index + 1,
                        "width": page.rect.width,
                        "height": page.rect.height,
                        "initial_rotation": rotation,
                        "coordinate_system": "unrotated_cropbox_relative_pdf_points",
                        "source_cropbox": list(page.cropbox),
                        "canonical_to_raw": [1, 0, 0, 1, 0, 0],
                        "fingerprint": hashlib.sha256(
                            bitmap.tobytes() + str(bitmap.size).encode()
                        ).hexdigest(),
                        **classify(page, config),
                        "quality": quality(bitmap, config),
                        "resolution": {
                            "render_dpi_max": 108,
                            "embedded_images": [
                                {
                                    "width_pixels": img["width"],
                                    "height_pixels": img["height"],
                                    "effective_dpi_x": 72
                                    * img["width"]
                                    / max(1, fitz.Rect(img["bbox"]).width),
                                    "effective_dpi_y": 72
                                    * img["height"]
                                    / max(1, fitz.Rect(img["bbox"]).height),
                                }
                                for img in page.get_image_info()
                            ],
                        },
                    }
                )
        media = "application/pdf"
    else:
        image = image_open(payload, limits)
        media = "image/jpeg" if image.format == "JPEG" else "image/png"
        w, h = image.size
        exif = int(image.getexif().get(274, 1))
        matrices = {
            1: [1, 0, 0, 1, 0, 0],
            2: [-1, 0, 0, 1, w, 0],
            3: [-1, 0, 0, -1, w, h],
            4: [1, 0, 0, -1, 0, h],
            5: [0, 1, 1, 0, 0, 0],
            6: [0, 1, -1, 0, h, 0],
            7: [0, -1, -1, 0, h, w],
            8: [0, -1, 1, 0, 0, w],
        }
        normalized = rgb(ImageOps.exif_transpose(image))
        q = quality(normalized, config)
        if exif != 1:
            q["issues"].append(
                {
                    "code": "exif_orientation",
                    "severity": "warning",
                    "message": "Orientation EXIF appliquée au dérivé ; original conservé.",
                }
            )
            if q["status"] == "pass":
                q["status"] = "warnings"
        pages.append(
            {
                "source_page": 1,
                "width": normalized.width,
                "height": normalized.height,
                "initial_rotation": 0,
                "coordinate_system": "original_image_pixels",
                "canonical_to_raw": inverse(matrices.get(exif, matrices[1])),
                "exif_orientation": exif,
                "fingerprint": hashlib.sha256(
                    normalized.tobytes() + str(normalized.size).encode()
                ).hexdigest(),
                "classification": "image_dominant",
                "image_coverage": 1,
                "native_text_chars": 0,
                "scan_with_text_layer": False,
                "quality": q,
                "resolution": {"declared_dpi": image.info.get("dpi")},
            }
        )
    return {
        "media_type": media,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
        "pages": pages,
    }


def build(sources, pages):
    result = fitz.open()
    mappings = []
    for order, description in enumerate(pages, 1):
        source = sources[description["source_id"]]
        meta = source["inspection"]["pages"][description["source_page"] - 1]
        w, h = meta["width"], meta["height"]
        crop = description["crop"]
        clip = fitz.Rect(crop[0] * w, crop[1] * h, crop[2] * w, crop[3] * h)
        rotation = description["rotation"]
        is_image = source["inspection"]["media_type"] != "application/pdf"
        scale = 72 / 150 if is_image else 1
        width, height = clip.width * scale, clip.height * scale
        if rotation in [90, 270]:
            width, height = height, width
        dest = result.new_page(width=width, height=height)
        source_forms = []
        if is_image:
            image = rgb(
                ImageOps.exif_transpose(
                    image_open(Path(source["path"]).read_bytes(), {"max_pixels": 20000000})
                )
            )
            # Recadrage rendu par PDF, sans réencoder ni altérer l'original.
            temp = fitz.open()
            p = temp.new_page(width=w * scale, height=h * scale)
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            p.insert_image(p.rect, stream=stream.getvalue())
            dest.show_pdf_page(
                dest.rect, temp, 0, clip=fitz.Rect([v * scale for v in clip]), rotate=-rotation
            )
            temp.close()
        else:
            with fitz.open(source["path"]) as original:
                original[description["source_page"] - 1].set_rotation(0)
                source_forms = [
                    {
                        "name": widget.field_name,
                        "value": widget.field_value,
                        "field_type": widget.field_type_string,
                        "bbox": list(widget.rect),
                    }
                    for widget in original[description["source_page"] - 1].widgets() or []
                ]
                # Aplatir uniquement les apparences dans le dérivé, jamais l'original ni les objets textuels.
                original.bake()
                # Les objets textuels et images natifs sont conservés.
                if original[description["source_page"] - 1].get_contents():
                    dest.show_pdf_page(
                        dest.rect,
                        original,
                        description["source_page"] - 1,
                        clip=clip,
                        rotate=-rotation,
                    )
        to_processing = transform(w, h, crop, rotation, scale)
        to_source = compose(inverse(to_processing), meta["canonical_to_raw"])
        mappings.append(
            {
                "processing_page": order,
                "processing_width": width,
                "processing_height": height,
                "page_id": description["id"],
                "source_id": description["source_id"],
                "source_page": description["source_page"],
                "source_sha256": source["inspection"]["sha256"],
                "processing_to_source": to_source,
                "canonical_to_processing": to_processing,
                "coordinate_system": meta["coordinate_system"],
                "crop": crop,
                "rotation": rotation,
                "source_cropbox": meta.get("source_cropbox"),
                "source_form_fields": source_forms,
            }
        )
    return result, mappings


def provenance(extraction, mappings):
    for item in extraction["evidence"] + extraction["tables"] + extraction["form_fields"]:
        mapping = mappings[item["page"] - 1]
        item["source"] = {
            **mapping,
            "bbox": rectangle(mapping["processing_to_source"], item["bbox"]),
        }
    by_id = {
        item["id"]: item
        for item in extraction["evidence"] + extraction["tables"] + extraction["form_fields"]
    }
    for field in extraction["fields"].values():
        for candidate in field["candidates"]:
            candidate["source"] = by_id[candidate["evidence_id"]]["source"]
    return extraction
