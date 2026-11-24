import json
import os
from pathlib import Path
import resource
import sys


def main():
    os.umask(0o077)
    root = Path(sys.argv[1])
    from credit.security.worker import harden

    harden(root)
    limits = json.loads((root / "limits.json").read_text())
    resource.setrlimit(resource.RLIMIT_AS, (limits["memory_mb"] * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (limits["timeout"],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["max_output"],) * 2)

    def denied(*args, **kwargs):
        raise PermissionError("network_disabled")

    sys.addaudithook(
        lambda event, args: denied()
        if event in {"socket.__new__", "socket.connect", "socket.getaddrinfo"}
        else None
    )
    from credit.printing.contracts import Presentation
    from credit.printing.render import html_document
    from credit.printing.latex import latex_pdf_document

    try:
        model = Presentation.model_validate_json((root / "model.json").read_text())
        html = html_document(model)
        pdf = latex_pdf_document(model, limits["max_pages"])
        (root / "edition.html").write_text(html)
        (root / "edition.pdf").write_bytes(pdf)
        result = {"status": "completed"}
    except Exception as exc:
        known = {
            "print_page_limit", "latex_engine_unavailable", "latex_compile_failed",
            "latex_output_invalid", "print_timeout",
        }
        result = {"error": str(exc) if str(exc) in known else "print_render_failed"}
    (root / "result.json").write_text(json.dumps(result))


if __name__ == "__main__":
    main()
