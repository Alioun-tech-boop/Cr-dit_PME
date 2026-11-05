"""Vérification hors ligne contre un trousseau PUBLIC obtenu par une voie de confiance."""

import argparse
import json
import os
from pathlib import Path
import zipfile
from credit.partners import signing


def verify(path, recipient):
    if path.stat().st_size > 64_000_000:
        raise ValueError("Archive trop volumineuse")
    with zipfile.ZipFile(path) as z:
        if (
            len(z.infolist()) > 50
            or sum(i.file_size for i in z.infolist()) > 64_000_000
            or any(i.file_size > 30_000_000 for i in z.infolist())
        ):
            raise ValueError("Limites de décompression dépassées")
        if len(z.namelist()) != len(set(z.namelist())) or any(
            "/" in n or "\\" in n for n in z.namelist()
        ):
            raise ValueError("Noms de fichiers invalides")
        envelope = json.loads(z.read("signed-manifest.json"))
        sig = json.loads(z.read("signature.json"))
        manifest = json.loads(z.read("sharing-manifest.json"))
        sharing_sig = json.loads(z.read("sharing-signature.json"))
        issuer = envelope["core"]["issuer_id"]
        signatures = [
            signing.verify(envelope, sig, issuer),
            signing.verify(manifest, sharing_sig, issuer),
        ]
        if not all(s["valid"] and s["key_status"] != "revoked" for s in signatures):
            raise ValueError("Signature ou clé non utilisable")
        if manifest["recipient_institution_id"] != recipient:
            raise ValueError("Mauvais destinataire")
        if signing.digest(signing.canonical(envelope)) != manifest["attestation_envelope_sha256"]:
            raise ValueError("Enveloppe altérée")
        approved = envelope["approved_manifest"]
        if (
            signing.digest(signing.canonical(approved))
            != envelope["core"]["approved_manifest_sha256"]
        ):
            raise ValueError("Manifeste approuvé altéré")
        hashes = {f["id"]: f["sha256"] for f in approved["files"] + [envelope["attestation_file"]]}
        for entry in manifest["files"]:
            if (
                hashes.get(entry["id"]) != entry["sha256"]
                or signing.digest(z.read(entry["name"])) != entry["sha256"]
            ):
                raise ValueError("Document altéré")
        return {
            "integrity": "verified",
            "manifest_sha256": signing.digest(signing.canonical(manifest)),
            "files": len(manifest["files"]),
            "notice": "Statut actuel, expiration et révocation de l’attestation à vérifier auprès de l’émetteur ; aucune confiance juridique déduite de la seule cryptographie.",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--trusted-keyring", type=Path, required=True)
    parser.add_argument("--recipient", required=True)
    args = parser.parse_args()
    os.environ["CREDIT_PARTNER_KEYRING_FILE"] = str(args.trusted_keyring)
    print(json.dumps(verify(args.archive, args.recipient), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
