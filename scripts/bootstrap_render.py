"""Provisionnement initial explicite, à retirer du service après vérification.

Le fichier privé est fourni par l'opérateur. Aucun secret n'est journalisé.
Ne modifie ni mot de passe ni identité déjà présents.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, text


def main():
    source = Path("/etc/secrets/credit-bootstrap.json")
    data = json.loads(source.read_text())
    admin = create_engine(data["admin_url"], hide_parameters=True)
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname='credit_application'")
        ).scalar()
        if not exists:
            # Identifiant constant ; le mot de passe est cité par le pilote PostgreSQL.
            from psycopg import sql

            raw = conn.connection.driver_connection
            with raw.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE credit_application LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Literal(data["app_password"]))
                )
    env = dict(os.environ, DATABASE_URL=data["admin_url"])
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    with admin.begin() as conn:
        conn.execute(text("GRANT USAGE ON SCHEMA public TO credit_application"))
        conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO credit_application"
            )
        )
        conn.execute(
            text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO credit_application")
        )
        conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        present = conn.execute(
            text("SELECT 1 FROM web_users WHERE actor_id=:id"), {"id": data["actor_id"]}
        ).scalar()
        if not present:
            conn.execute(
                text(
                    "INSERT INTO web_users (actor_id,username,password_hash,profile,enabled,revision) VALUES (:id,:username,:password_hash,'{}',1,1)"
                ),
                {
                    "id": data["actor_id"],
                    "username": data["username"],
                    "password_hash": data["password_hash"],
                },
            )
    admin.dispose()
    print(
        "Provisionnement initial terminé ; retirer le fichier de bootstrap administratif.",
        flush=True,
    )


if __name__ == "__main__":
    main()
