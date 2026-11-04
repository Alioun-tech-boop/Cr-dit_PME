import argparse
import getpass
import json
import sys
from pathlib import Path

from .catalog import public_catalog
from .engine import MAX_BYTES, ExtractionError, extract_pdf
from .review import apply_review


def write_json(value, path=None):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
        target.chmod(0o600)
    else:
        print(text)


def main():
    parser = argparse.ArgumentParser(description="Extraction PDF Crédit PME — données non vérifiées")
    sub = parser.add_subparsers(dest="command", required=True)
    cat = sub.add_parser("catalog")
    cat.add_argument("--output")
    ext = sub.add_parser("extract")
    ext.add_argument("pdf")
    ext.add_argument("--type")
    ext.add_argument("--ocr", choices=["auto", "always", "never"], default="auto")
    ext.add_argument("--lang", default="fra")
    ext.add_argument("--password-prompt", action="store_true")
    ext.add_argument("--output", required=True)
    batch = sub.add_parser("batch")
    batch.add_argument("manifest", help="JSON {documents:[{path,document_type}]}")
    batch.add_argument("--output-dir", required=True)
    batch.add_argument("--ocr", choices=["auto", "always", "never"], default="auto")
    batch.add_argument("--lang", default="fra")
    review = sub.add_parser("review")
    review.add_argument("extraction")
    review.add_argument("decisions")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--output", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "catalog":
            write_json(public_catalog(), args.output)
        elif args.command == "extract":
            path = Path(args.pdf)
            if path.stat().st_size > MAX_BYTES:
                raise ExtractionError("file_too_large")
            password = getpass.getpass("Mot de passe PDF : ") if args.password_prompt else None
            write_json(extract_pdf(path.read_bytes(), args.type, ocr=args.ocr,
                                   lang=args.lang, password=password), args.output)
        elif args.command == "batch":
            manifest_path = Path(args.manifest).resolve()
            items = json.loads(manifest_path.read_text(encoding="utf-8"))["documents"]
            results = []
            for index, item in enumerate(items):
                # Les chemins du manifeste sont relatifs au manifeste.
                try:
                    path = manifest_path.parent / item["path"]
                    if path.stat().st_size > MAX_BYTES:
                        raise ExtractionError("file_too_large")
                    result = extract_pdf(path.read_bytes(), item.get("document_type"),
                                         ocr=args.ocr, lang=args.lang)
                    name = f"document_{index+1:04d}.json"
                    write_json(result, Path(args.output_dir) / name)
                    results.append({"index": index, "status": "extracted_unverified", "output": name})
                except Exception as exc:
                    code = str(exc) if isinstance(exc, ExtractionError) else "document_processing_failed"
                    results.append({"index": index, "status": "failed", "error": code})
            write_json({"results": results}, Path(args.output_dir) / "manifest_results.json")
            return 1 if any(x["status"] == "failed" for x in results) else 0
        elif args.command == "review":
            base = json.loads(Path(args.extraction).read_text(encoding="utf-8"))
            decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
            write_json(apply_review(base, decisions, args.reviewer), args.output)
        else:
            from .server import make_server
            server = make_server(args.host, args.port)
            print(f"Service local : http://{args.host}:{server.server_port}", flush=True)
            server.serve_forever()
    except (ExtractionError, ValueError, OSError, KeyError) as exc:
        print(f"Échec : {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
