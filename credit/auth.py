"""Identités locales configurées côté serveur ; aucun utilisateur fourni dans les corps HTTP."""

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Actor:
    id: str
    case_ids: tuple[str, ...] = ()
    reviewer: bool = False
    native_exception: bool = False


def authenticate(request: Request) -> Actor:
    path = os.getenv("CREDIT_AUTH_FILE")
    raw_config = os.getenv("CREDIT_AUTH_JSON")
    if not path and not raw_config:
        raise HTTPException(
            503, "Identités non configurées : définir CREDIT_AUTH_FILE ou CREDIT_AUTH_JSON"
        )
    try:
        users = json.loads(Path(path).read_text() if path else raw_config)["users"]
        if not isinstance(users, list) or len({u["id"] for u in users}) != len(users):
            raise ValueError("invalid_users")
        import re

        for user in users:
            if (
                not isinstance(user["id"], str)
                or not user["id"].strip()
                or not re.fullmatch(r"[a-f0-9]{64}", user["token_sha256"])
                or not isinstance(user.get("case_ids", []), list)
                or not all(isinstance(v, str) for v in user.get("case_ids", []))
                or not isinstance(user.get("reviewer", False), bool)
                or not isinstance(user.get("native_exception", False), bool)
            ):
                raise ValueError("invalid_user")
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Configuration des identités indisponible") from None
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or len(header) > 4096:
        raise HTTPException(401, "Authentification requise", headers={"WWW-Authenticate": "Bearer"})
    digest = hashlib.sha256(header[7:].encode()).hexdigest()
    for user in users:
        if hmac.compare_digest(digest, user["token_sha256"]):
            return Actor(
                user["id"],
                tuple(user.get("case_ids", [])),
                user.get("reviewer", False),
                user.get("native_exception", False),
            )
    raise HTTPException(401, "Jeton invalide", headers={"WWW-Authenticate": "Bearer"})


def authorize(case, actor):
    if case.owner_id != actor.id and case.id not in actor.case_ids:
        # Même réponse qu'un identifiant inexistant, sans révéler le dossier.
        raise HTTPException(404, "Dossier introuvable")
