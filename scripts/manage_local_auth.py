"""Révocation / rotation opérateur du registre opaque local, jamais via un corps HTTP."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from credit.security.auth_store import locked_registry, event, credentials

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("action", choices=["revoke", "rotate"])
parser.add_argument("--user", required=True)
parser.add_argument("--registry", type=Path, default=Path(".local/auth/users.json"))
parser.add_argument("--hours", type=int, default=24)
args = parser.parse_args()
if not 1 <= args.hours <= 168:
    parser.error("Durée technique autorisée : 1 à 168 heures")
with locked_registry(args.registry) as data:
    user = next((u for u in data["users"] if u["id"] == args.user), None)
    if user is None:
        parser.error("Identité inconnue")
    if args.action == "revoke":
        user["revoked_at"] = datetime.now(timezone.utc).isoformat()
    else:
        token = secrets.token_urlsafe(32)
        user["token_sha256"] = hashlib.sha256(token.encode()).hexdigest()
        user["expires_at"] = (datetime.now(timezone.utc) + timedelta(hours=args.hours)).isoformat()
        user.pop("revoked_at", None)
        credentials(args.registry.parent, args.user, token)
event(args.registry, args.action, args.user, user.get("institution_id"))
print("Registre mis à jour ; aucun jeton affiché.")
