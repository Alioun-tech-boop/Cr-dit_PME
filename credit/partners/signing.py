"""Ed25519 détaché. Clés provisionnées par l'opérateur, jamais au démarrage."""

import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from urllib.parse import urlparse
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import HTTPException


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def keyring():
    path = os.getenv("CREDIT_PARTNER_KEYRING_FILE")
    if not path:
        raise HTTPException(
            503, "Signature non configurée ; aucune attestation signée ne peut être émise"
        )
    try:
        keys = json.loads(Path(path).read_text())["keys"]
        if not isinstance(keys, list) or len({k["id"] for k in keys}) != len(keys):
            raise ValueError()
        if any(
            k["status"] not in {"active", "retired", "revoked"}
            or k["purpose"] not in {"demonstration", "production"}
            for k in keys
        ):
            raise ValueError()
        return keys
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Registre des clés indisponible ou invalide") from None


def signing_key(issuer_id, demonstration):
    keys = [
        k
        for k in keyring()
        if k["status"] == "active"
        and issuer_id in k["issuer_ids"]
        and k["purpose"] == ("demonstration" if demonstration else "production")
    ]
    if len(keys) != 1 or (os.getenv("CREDIT_ENV") == "production" and demonstration):
        raise HTTPException(503, "Clé de signature applicable unique non disponible")
    config = keys[0]
    try:
        path = Path(config["private_key_path"])
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("permissions")
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("key_type")
        public = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        if base64.b64encode(public).decode() != config["public_key_base64"]:
            raise ValueError("public_key_mismatch")
        return config, key
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(
            503, "Clé privée de signature indisponible ou permissions inadéquates"
        ) from None


def sign(envelope, config, key):
    return {
        "algorithm": "Ed25519",
        "key_id": config["id"],
        "public_key_base64": config["public_key_base64"],
        "signature_base64": base64.b64encode(key.sign(canonical(envelope))).decode(),
        "legal_notice": "Signature cryptographique détachée ; aucune certification électronique par un tiers revendiquée.",
    }


def verify(envelope, signature, issuer_id):
    config = next(
        (k for k in keyring() if k["id"] == signature["key_id"] and issuer_id in k["issuer_ids"]),
        None,
    )
    if config is None:
        raise HTTPException(503, "Clé publique historique non disponible")
    try:
        if (
            signature["algorithm"] != "Ed25519"
            or signature["public_key_base64"] != config["public_key_base64"]
        ):
            raise ValueError()
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(config["public_key_base64"], validate=True)
        )
        key.verify(
            base64.b64decode(signature["signature_base64"], validate=True), canonical(envelope)
        )
        return {"valid": True, "key_status": config["status"]}
    except (InvalidSignature, ValueError, TypeError, KeyError):
        return {"valid": False, "key_status": config["status"]}


def verification_url(token):
    origin = os.getenv("CREDIT_WEB_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(origin)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path
        or not parsed.hostname
    ):
        raise HTTPException(503, "Origine de vérification invalide")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and os.getenv("CREDIT_ENV") != "production"
    ):
        raise HTTPException(503, "Origine HTTPS contrôlée requise pour la vérification")
    return origin + "/verify-attestation.html?id=" + token


# Point d'extension pour un prestataire de confiance à sélectionner et auditer ultérieurement.
# Aucun adaptateur tiers n'est installé ni activé par ce contrat.
from typing import Protocol  # noqa: E402


class TrustedSignatureProvider(Protocol):
    def sign_manifest(self, canonical_manifest: bytes, *, key_id: str, issuer_id: str) -> dict: ...
    def verify_manifest(self, canonical_manifest: bytes, signature: dict) -> dict: ...
