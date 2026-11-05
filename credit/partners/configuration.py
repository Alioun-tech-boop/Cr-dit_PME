import json
import os
from pathlib import Path
from datetime import datetime, timezone
from fastapi import HTTPException
from credit.partners.contracts import WorkflowPolicy
from credit.partners.models import InstitutionPolicy


def identity(actor_id):
    """Lecture minimale du registre administré ; ne retourne jamais de justificatif d'authentification."""
    try:
        path = os.getenv("CREDIT_AUTH_FILE")
        users = json.loads(Path(path).read_text() if path else os.environ["CREDIT_AUTH_JSON"])[
            "users"
        ]
        user = next((u for u in users if u["id"] == actor_id), None)
        if not user or user.get("disabled") or user.get("revoked_at"):
            return None
        expiry = user.get("expires_at")
        if expiry and datetime.fromisoformat(expiry).replace(tzinfo=timezone.utc) <= datetime.now(
            timezone.utc
        ):
            return None
        return {k: user.get(k) for k in ["id", "role", "institution_id"]}
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Registre des identités indisponible") from None


def policy(session, institution_id):
    item = session.get(InstitutionPolicy, institution_id) if institution_id else None
    if not item:
        raise HTTPException(409, "Politique de revue de votre institution non configurée")
    return item, WorkflowPolicy.model_validate(item.data["policy"])


def allow_demo(demonstration, classification):
    if demonstration and (
        classification != "synthetic"
        or os.getenv("CREDIT_ENV") == "production"
        or os.getenv("CREDIT_PARTNER_ALLOW_DEMO", "false").lower() != "true"
    ):
        raise HTTPException(
            409,
            "Parcours de démonstration réservé aux données synthétiques et au mode local autorisé",
        )
