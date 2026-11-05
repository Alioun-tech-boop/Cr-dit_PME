"""Protections locales bornées ; ne remplacent pas une passerelle distribuée."""

import asyncio
from datetime import datetime, timezone
from collections import OrderedDict, deque
import json
import logging
import os
import threading
import time
from fastapi import HTTPException

LOGGER = logging.getLogger("credit.security")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)


def audit(event, actor=None, outcome="success", request_id=None, resource=None):
    LOGGER.info(
        json.dumps(
            {
                "date": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "actor_id": getattr(actor, "id", None),
                "institution_id": getattr(actor, "institution_id", None),
                "outcome": outcome,
                "request_id": request_id,
                "resource_id": resource,
            },
            separators=(",", ":"),
        )
    )


class Limiter:
    def __init__(self):
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def check(self, key, limit, seconds=60):
        now = time.monotonic()
        with self.lock:
            values = self.entries.setdefault(key, deque())
            while values and values[0] <= now - seconds:
                values.popleft()
            self.entries.move_to_end(key)
            while len(self.entries) > 10000:
                self.entries.popitem(last=False)
            if len(values) >= limit:
                raise HTTPException(
                    429,
                    "Trop de requêtes ; réessayer plus tard",
                    headers={"Retry-After": str(seconds)},
                )
            values.append(now)


async def bounded_json(request):
    if request.method not in {"POST", "PUT", "PATCH"} or request.scope["path"].endswith(
        ("/sources", "/attachments")
    ):
        return
    maximum = int(os.getenv("CREDIT_MAX_JSON_BYTES", "2000000"))
    length = request.headers.get("content-length")
    if length:
        try:
            count = int(length)
        except ValueError:
            raise HTTPException(400, "Longueur invalide") from None
        if count < 0:
            raise HTTPException(400, "Longueur invalide")
        if count > maximum:
            raise HTTPException(413, "Corps JSON trop volumineux")
    data = bytearray()
    try:
        async with asyncio.timeout(int(os.getenv("CREDIT_BODY_TIMEOUT_SECONDS", "20"))):
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > maximum:
                    raise HTTPException(413, "Corps JSON trop volumineux")
    except TimeoutError:
        raise HTTPException(408, "Délai de réception dépassé") from None
    if data and request.headers.get("content-type", "").split(";")[0] == "application/json":
        try:
            obj = json.loads(data)
            stack = [(obj, 0)]
            nodes = 0
            while stack:
                node, depth = stack.pop()
                nodes += 1
                if depth > 40 or nodes > 40000:
                    raise HTTPException(413, "JSON trop complexe")
                if isinstance(node, dict):
                    stack.extend((v, depth + 1) for v in node.values())
                elif isinstance(node, list):
                    stack.extend((v, depth + 1) for v in node)
        except (RecursionError, ValueError):
            raise HTTPException(400, "JSON invalide") from None
    request._body = bytes(data)


def production_guard():
    if os.getenv("CREDIT_ENV", "local") != "production":
        return
    from sqlalchemy.engine import make_url

    raw = os.getenv("DATABASE_URL", "")
    try:
        url = make_url(raw)
        if (
            url.get_backend_name() != "postgresql"
            or not url.password
            or url.password in {"credit_local", "postgres", "password"}
            or url.query.get("sslmode") != "verify-full"
        ):
            raise ValueError()
    except Exception:
        raise RuntimeError(
            "Production : PostgreSQL TLS verify-full et secrets explicites requis"
        ) from None
    hosts = os.getenv("CREDIT_ALLOWED_HOSTS", "").split(",")
    if not hosts or any(not h or h == "*" or h == "testserver" for h in hosts):
        raise RuntimeError("Production : hôtes explicites requis")
    if os.getenv("CREDIT_ALLOW_DEMO", "false").lower() == "true":
        raise RuntimeError("Production : démonstration interdite")
    if not os.getenv("CREDIT_AUTH_FILE") or os.getenv("CREDIT_AUTH_JSON"):
        raise RuntimeError(
            "Production : registre privé monté, sans secret en variable de conteneur"
        )
    from pathlib import Path

    if Path(os.environ["CREDIT_AUTH_FILE"]).stat().st_mode & 0o077:
        raise RuntimeError("Production : permissions du registre trop ouvertes")
    if any(v.strip() == "*" for v in os.getenv("CREDIT_TRUSTED_PROXY_IPS", "").split(",")):
        raise RuntimeError("Production : proxy de confiance explicite requis")
