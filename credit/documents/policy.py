import json
import os
from pathlib import Path

from credit_pdf.catalog import CATALOG

ROOT = Path(__file__).parent


def configuration():
    policy = json.loads(
        Path(os.getenv("CREDIT_DOCUMENT_POLICY_FILE", ROOT / "policies.v1.json")).read_text()
    )
    quality = json.loads(
        Path(os.getenv("CREDIT_QUALITY_FILE", ROOT / "quality.v1.json")).read_text()
    )
    if set(policy["rules"]) != set(CATALOG):
        raise ValueError("Le référentiel doit couvrir exactement le catalogue")
    for rule in policy["rules"].values():
        if (
            not isinstance(rule["profiles"], list)
            or not rule["profiles"]
            or not set(rule["profiles"]) <= {"individuals", "businesses"}
            or not isinstance(rule["formats"], list)
            or not rule["formats"]
            or not set(rule["formats"])
            <= {"image/jpeg", "image/png", "application/pdf", "application/json"}
            or not isinstance(rule["native_exception_allowed"], bool)
        ):
            raise ValueError("Règle documentaire invalide")
        if rule["policy"] not in {"scan_required", "original_preferred", "structured_required"}:
            raise ValueError("Politique inconnue")
    limits = policy["limits"]
    for key, maximum in {
        "max_file_bytes": 26214400,
        "max_total_bytes": 104857600,
        "max_pages": 100,
        "max_pixels": 20000000,
        "timeout_seconds": 300,
        "concurrency": 8,
        "memory_mb": 2048,
    }.items():
        if not 0 < limits[key] <= maximum:
            raise ValueError("Limite technique invalide : " + key)
    if not 0 < quality["mixed_scan_min_coverage"] <= quality["scan_image_coverage"] <= 1:
        raise ValueError("Seuils de couverture invalides")
    return policy, quality
