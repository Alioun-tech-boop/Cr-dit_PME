"""Provisionnement explicite d'une clé locale. Ne constitue pas une certification tierce."""

import argparse
import base64
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create-demo", "retire", "revoke"])
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--directory", type=Path, default=Path(".local/partner-signing"))
    args = parser.parse_args()
    if not args.key_id.replace("-", "").replace("_", "").isalnum():
        parser.error("Identifiant de clé invalide")
    os.umask(0o077)
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    registry = root / "keyring.json"
    data = json.loads(registry.read_text()) if registry.exists() else {"keys": []}
    if args.action == "create-demo":
        if os.getenv("CREDIT_ENV") == "production":
            parser.error("Clé de démonstration interdite en production")
        if any(k["id"] == args.key_id for k in data["keys"]):
            parser.error("Identifiant de clé existant")
        key = Ed25519PrivateKey.generate()
        private = root / (args.key_id + ".pem")
        with private.open("xb") as f:
            f.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        private.chmod(0o600)
        data["keys"].append(
            {
                "id": args.key_id,
                "status": "active",
                "purpose": "demonstration",
                "issuer_ids": [args.issuer],
                "private_key_path": str(private),
                "public_key_base64": base64.b64encode(
                    key.public_key().public_bytes(
                        serialization.Encoding.Raw, serialization.PublicFormat.Raw
                    )
                ).decode(),
            }
        )
    else:
        item = next(
            (k for k in data["keys"] if k["id"] == args.key_id and args.issuer in k["issuer_ids"]),
            None,
        )
        if item is None:
            parser.error("Clé inconnue")
        item["status"] = "retired" if args.action == "retire" else "revoked"
    temp = root / "keyring.tmp"
    temp.write_text(json.dumps(data, indent=2))
    temp.chmod(0o600)
    temp.replace(registry)
    print("Registre de clés mis à jour :", registry)
    print("Aucune clé privée affichée ; démonstration uniquement, jamais génération au démarrage.")


if __name__ == "__main__":
    main()
