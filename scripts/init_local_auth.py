"""Crée une identité locale privée ; les droits existants ne sont jamais devinés."""

import argparse
import hashlib
import os
from pathlib import Path
import secrets
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from credit.security.auth_store import locked_registry, event, credentials

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--user", default="agent-local")
parser.add_argument("--institution", default=None)
parser.add_argument(
    "--role",
    choices=[
        "applicant",
        "analyst",
        "institution_manager",
        "administrator",
        "bank_agent",
        "bank_manager",
    ],
    default=None,
)
parser.add_argument("--hours", type=int, default=24)
parser.add_argument("--reviewer", action="store_true")
parser.add_argument("--native-exception", action="store_true")
parser.add_argument("--grant-case", action="append", default=[])
args = parser.parse_args()
os.umask(0o077)
root = Path(".local/auth")
root.mkdir(parents=True, exist_ok=True)
config = root / "users.json"
if (
    not args.user.strip()
    or len(args.user) > 100
    or (
        args.institution is not None
        and (not args.institution.strip() or len(args.institution) > 100)
    )
):
    parser.error("Identité / institution : 1 à 100 caractères non vides")
if not 1 <= args.hours <= 168:
    parser.error("Durée autorisée : 1 à 168 heures")
with locked_registry(config) as data:
    if any(u["id"] == args.user for u in data["users"]):
        parser.error(
            "Identité existante ; utiliser manage_local_auth.py pour rotation ou révocation"
        )
    token = secrets.token_urlsafe(32)
    role = args.role or ("analyst" if args.reviewer else "applicant")
    data["users"].append(
        {
            "id": args.user,
            "institution_id": args.institution,
            "role": role,
            "reviewer": role in {"analyst", "institution_manager", "administrator"},
            "native_exception": args.native_exception,
            "case_ids": args.grant_case,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=args.hours)).isoformat(),
        }
    )
    private = credentials(root, args.user, token)
event(config, "created", args.user, args.institution)
print("Identité créée ; justificatif privé :", private.resolve())
