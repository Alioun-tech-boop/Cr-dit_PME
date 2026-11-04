"""Crée une identité locale privée ; les droits existants ne sont jamais devinés."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--user", default="agent-local")
parser.add_argument("--reviewer", action="store_true")
parser.add_argument("--native-exception", action="store_true")
parser.add_argument("--grant-case", action="append", default=[])
args = parser.parse_args()
os.umask(0o077)
root = Path(".local/auth")
root.mkdir(parents=True, exist_ok=True)
config = root / "users.json"
data = json.loads(config.read_text()) if config.exists() else {"users": []}
if any(u["id"] == args.user for u in data["users"]):
    parser.error(
        "Identité existante : modifier explicitement ses droits dans users.json ou choisir un autre identifiant."
    )
token = secrets.token_urlsafe(32)
data["users"].append(
    {
        "id": args.user,
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "case_ids": args.grant_case,
        "reviewer": args.reviewer,
        "native_exception": args.native_exception,
    }
)
config.write_text(json.dumps(data, indent=2) + "\n")
config.chmod(0o600)
# Pas de nom utilisateur utilisé comme chemin.
credentials = root / (hashlib.sha256(args.user.encode()).hexdigest()[:16] + ".json")
credentials.write_text(json.dumps({"user": args.user, "token": token}) + "\n")
credentials.chmod(0o600)
curl_file = credentials.with_suffix(".curl")
curl_file.write_text('header = "Authorization: Bearer ' + token + '"\n')
curl_file.chmod(0o600)
print("Identités :", config.resolve())
print("Configuration curl privée :", curl_file.resolve())
print("Jeton enregistré sans affichage :", credentials.resolve())
