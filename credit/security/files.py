"""Analyse antivirus facultative : aucun résultat absent ne signifie « sain »."""

import os
import shutil
import subprocess
from fastapi import HTTPException


def antimalware(payload):
    executable = shutil.which("clamscan")
    required = os.getenv("CREDIT_ANTIMALWARE_REQUIRED", "false").lower() == "true"
    if not executable:
        if required:
            raise HTTPException(503, "Analyse antimalware requise mais indisponible")
        return {"status": "not_scanned", "engine": None}
    try:
        result = subprocess.run(
            [executable, "--no-summary", "--stdout", "-"],
            input=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            env={"PATH": os.getenv("PATH", "/usr/bin:/bin")},
        )
    except (OSError, subprocess.TimeoutExpired):
        if required:
            raise HTTPException(503, "Analyse antimalware indisponible") from None
        return {"status": "scan_failed", "engine": "clamav"}
    if result.returncode == 1:
        raise HTTPException(422, "Menace détectée : dépôt refusé")
    if result.returncode != 0:
        if required:
            raise HTTPException(503, "Analyse antimalware indisponible")
        return {"status": "scan_failed", "engine": "clamav"}
    return {
        "status": "no_threat_detected",
        "engine": "clamav",
        "notice": "Aucune garantie d’innocuité ou d’authenticité",
    }
