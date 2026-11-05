"""Créer/réinitialiser un accès navigateur pour une identité serveur existante."""

import argparse
import getpass
import os
from uuid import uuid4
from types import SimpleNamespace
from sqlalchemy import select
from credit.auth import authenticate
from credit.persistence import sessions, WebUser, SecurityEvent
from credit.web.application import PASSWORDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    actor = authenticate(SimpleNamespace(headers={}, scope={}), configured_actor_id=args.actor_id)
    password = getpass.getpass("Mot de passe (12 caractères minimum) : ")
    if len(password) < 12 or len(password) > 1024:
        parser.error("12 à 1024 caractères requis")
    if password != getpass.getpass("Confirmer : "):
        parser.error("Confirmation différente")
    _, factory = sessions()
    with factory() as db:
        user = db.get(WebUser, args.actor_id)
        existing = db.scalar(select(WebUser).where(WebUser.username == args.username.lower()))
        if existing and existing.actor_id != args.actor_id:
            parser.error("Nom de connexion déjà utilisé")
        if not user:
            user = WebUser(actor_id=args.actor_id, profile={})
        user.username = args.username.lower()
        user.password_hash = PASSWORDS.hash(password)
        user.enabled = 1
        db.add(user)
        db.add(
            SecurityEvent(
                actor_id="os:" + str(os.getuid()),
                institution_id=actor.institution_id,
                event="web_account_provisioned",
                outcome="success",
                request_id=str(uuid4()),
                resource_id=actor.id,
            )
        )
        db.commit()
    print("Accès navigateur provisionné. Aucun rôle ni jeton technique transmis.")


if __name__ == "__main__":
    main()
