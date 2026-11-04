"""Adaptateur HTTP local, PDF binaire ; pas un serveur de production."""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlparse

from .catalog import public_catalog
from .engine import MAX_BYTES, ExtractionError, extract_pdf

SLOTS = BoundedSemaphore(2)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Pas de log contenant des noms de fichiers, URL ou valeurs de client.

    def send_json(self, code, value):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        token = getattr(self.server, "api_token", "")
        if token and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
            self.send_json(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(200, {"status": "ok", "mode": "local_development"})
        elif path == "/catalog":
            self.send_json(200, public_catalog())
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if not self.authorized():
            return
        url = urlparse(self.path)
        if url.path != "/extract":
            self.send_json(404, {"error": "not_found"})
            return
        if self.headers.get_content_type() != "application/pdf":
            self.send_json(415, {"error": "application_pdf_required"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BYTES:
            self.send_json(413, {"error": "invalid_size"})
            return
        if not SLOTS.acquire(blocking=False):
            self.send_json(429, {"error": "busy"})
            return
        try:
            self.connection.settimeout(30)
            payload = self.rfile.read(length)
            if len(payload) != length:
                self.send_json(400, {"error": "incomplete_body"})
                return
            params = parse_qs(url.query)
            result = extract_pdf(payload, params.get("type", [None])[0],
                                 ocr=params.get("ocr", ["auto"])[0],
                                 lang=params.get("lang", ["fra"])[0])
            self.send_json(200, result)
        except ExtractionError as exc:
            self.send_json(422, {"error": str(exc)})
        except Exception:
            self.send_json(500, {"error": "extraction_failed_no_details_logged"})
        finally:
            SLOTS.release()


def make_server(host="127.0.0.1", port=8765):
    # Un jeton seul ne fournit pas TLS/quotas/isolation : exposition refusée.
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("local_binding_only_use_production_gateway_for_remote_access")
    server = ThreadingHTTPServer((host, port), Handler)
    server.api_token = os.environ.get("CREDIT_PDF_API_TOKEN", "")
    return server
