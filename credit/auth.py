"""Identités locales configurées côté serveur ; aucun utilisateur fourni dans les corps HTTP."""

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Actor:
    id: str
    case_ids: tuple[str, ...] = ()
    reviewer: bool = False
    native_exception: bool = False
    institution_id: str | None = None
    role: str | None = None


def authenticate(request: Request, *, configured_actor_id: str | None = None) -> Actor:
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
        if len({u["token_sha256"] for u in users}) != len(users):
            raise ValueError("ambiguous_credentials")
        import re

        for user in users:
            if (
                not isinstance(user["id"], str)
                or not user["id"].strip()
                or len(user["id"]) > 100
                or (user.get("expires_at") is not None and not isinstance(user["expires_at"], str))
                or not isinstance(user.get("disabled", False), bool)
                or not re.fullmatch(r"[a-f0-9]{64}", user["token_sha256"])
                or not isinstance(user.get("case_ids", []), list)
                or not all(isinstance(v, str) for v in user.get("case_ids", []))
                or (
                    user.get("institution_id") is not None
                    and (
                        not isinstance(user["institution_id"], str)
                        or not user["institution_id"].strip()
                        or len(user["institution_id"]) > 100
                    )
                )
                or user.get("role", "analyst" if user.get("reviewer") else "applicant")
                not in {"applicant", "analyst", "institution_manager", "administrator"}
                or not isinstance(user.get("reviewer", False), bool)
                or not isinstance(user.get("native_exception", False), bool)
            ):
                raise ValueError("invalid_user")
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Configuration des identités indisponible") from None
    header = request.headers.get("Authorization", "")
    web_actor = request.scope.get("credit.web_actor")
    if web_actor is not None:
        return web_actor
    if configured_actor_id is None and (not header.startswith("Bearer ") or len(header) > 4096):
        raise HTTPException(401, "Authentification requise", headers={"WWW-Authenticate": "Bearer"})
    digest = hashlib.sha256(header[7:].encode()).hexdigest()
    for user in users:
        if (configured_actor_id is not None and user["id"] == configured_actor_id) or (
            configured_actor_id is None and hmac.compare_digest(digest, user["token_sha256"])
        ):
            expired = False
            try:
                expiration = (
                    datetime.fromisoformat(user["expires_at"].replace("Z", "+00:00"))
                    if user.get("expires_at")
                    else None
                )
                if expiration is not None:
                    expired = expiration.tzinfo is None or expiration <= datetime.now(timezone.utc)
            except (ValueError, TypeError):
                expired = True
            production = os.getenv("CREDIT_ENV", "local") == "production"
            if (
                user.get("revoked_at")
                or user.get("disabled", False)
                or expired
                or (
                    production
                    and (
                        expiration is None or not user.get("institution_id") or not user.get("role")
                    )
                )
            ):
                raise HTTPException(
                    401, "Jeton invalide ou expiré", headers={"WWW-Authenticate": "Bearer"}
                )
            current_role = user.get("role", "analyst" if user.get("reviewer") else "applicant")
            return Actor(
                user["id"],
                tuple(user.get("case_ids", [])),
                current_role in {"analyst", "institution_manager", "administrator"},
                user.get("native_exception", False)
                and current_role in {"analyst", "institution_manager", "administrator"},
                user.get("institution_id"),
                current_role,
            )
    raise HTTPException(401, "Jeton invalide ou expiré", headers={"WWW-Authenticate": "Bearer"})


def authorize(case, actor):
    if (case.institution_id != actor.institution_id) or (
        case.owner_id != actor.id and case.id not in actor.case_ids
    ):
        # Même réponse qu'un identifiant inexistant, sans révéler le dossier.
        raise HTTPException(404, "Dossier introuvable")
