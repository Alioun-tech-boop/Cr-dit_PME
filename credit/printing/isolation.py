"""Génération locale isolée et bornée, sans infrastructure distribuée."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading

GATE = threading.BoundedSemaphore(int(os.getenv("CREDIT_PRINT_CONCURRENCY", "2")))


def render_isolated(model):
    max_input = int(os.getenv("CREDIT_PRINT_MAX_INPUT_BYTES", "3000000"))
    data = model.model_dump_json().encode()
    if len(data) > max_input:
        raise ValueError("print_input_limit")
    timeout = int(os.getenv("CREDIT_PRINT_TIMEOUT_SECONDS", "30"))
    if not GATE.acquire(blocking=False):
        raise ValueError("print_busy")
    try:
        with TemporaryDirectory(prefix="credit-print-") as directory:
            root = Path(directory)
            (root / "model.json").write_bytes(data)
            job = {
                "timeout": timeout,
                "max_pages": int(os.getenv("CREDIT_PRINT_MAX_PAGES", "120")),
                "memory_mb": int(os.getenv("CREDIT_PRINT_MEMORY_MB", "512")),
                "max_output": int(os.getenv("CREDIT_PRINT_MAX_OUTPUT_BYTES", "15000000")),
            }
            (root / "limits.json").write_text(json.dumps(job))
            # Aucun shell ; aucun chemin ou URL utilisateur transmis au moteur.
            completed = subprocess.run(
                [sys.executable, "-m", "credit.printing.worker", str(root)],
                capture_output=True,
                timeout=timeout + 2,
                env={
                    k: v
                    for k, v in os.environ.items()
                    if k in {"PATH", "PYTHONPATH", "LANG", "LC_ALL", "SYSTEMROOT"}
                },
            )
            if completed.returncode or not (root / "result.json").exists():
                raise ValueError("print_render_failed")
            result = json.loads((root / "result.json").read_text())
            if result.get("error"):
                raise ValueError(result["error"])
            pdf = (root / "edition.pdf").read_bytes()
            html = (root / "edition.html").read_text()
            if (
                not pdf.startswith(b"%PDF-")
                or not html
                or len(pdf) + len(html.encode()) > job["max_output"]
            ):
                raise ValueError("print_output_limit")
            return html, pdf
    except subprocess.TimeoutExpired:
        raise ValueError("print_timeout") from None
    finally:
        GATE.release()
