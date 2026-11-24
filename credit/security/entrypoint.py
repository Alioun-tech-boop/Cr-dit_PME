"""Démarrage local migré ; en production, migrations séparées et rôle restreint."""

import os
import subprocess
import sys
from sqlalchemy import create_engine, text
from credit.security.runtime import production_guard
from alembic.config import Config
from alembic.script import ScriptDirectory


# Verrou de session PostgreSQL : empêche deux instances de migrer simultanément.
_RENDER_MIGRATION_LOCK = 73120420261124


def listen_port():
    port = int(os.getenv("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT doit être compris entre 1 et 65535")
    return port


def prepare_private_registry():
    """Copie privée d'un secret monté en lecture seule par l'hébergeur."""
    from pathlib import Path
    import tempfile

    source = os.getenv("CREDIT_AUTH_SOURCE_FILE")
    if not source:
        return
    destination = Path(tempfile.mkdtemp(prefix="credit-auth-")) / "registry.json"
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(Path(source).read_bytes())
    os.environ["CREDIT_AUTH_FILE"] = str(destination)


def migrate_production_database():
    """Applique les migrations avec le compte DB déjà configuré, sans créer de rôle.

    Ce mode n'accorde aucun privilège PostgreSQL. Il exige un compte non privilégié
    disposant déjà du droit CREATE sur le schéma public. Le verrou consultatif est
    conservé pendant toute l'exécution d'Alembic.
    """
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url, hide_parameters=True)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            role = connection.execute(
                text(
                    """
                    SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls,
                           has_schema_privilege(current_user, 'public', 'CREATE')
                    FROM pg_roles
                    WHERE rolname = current_user
                    """
                )
            ).one()
            if any(bool(value) for value in role[:4]):
                raise RuntimeError(
                    "Migration Render refusée : le compte PostgreSQL possède des privilèges élevés."
                )
            if not bool(role[4]):
                raise RuntimeError(
                    "Migration Render impossible : le compte DATABASE_URL n'a pas le droit "
                    "CREATE sur le schéma public. Un administrateur PostgreSQL doit provisionner "
                    "ce droit ou exécuter les migrations séparément."
                )

            connection.execute(
                text("SELECT pg_advisory_lock(:lock_key)"),
                {"lock_key": _RENDER_MIGRATION_LOCK},
            )
            try:
                subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    env=dict(os.environ),
                    check=True,
                )
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _RENDER_MIGRATION_LOCK},
                )
    finally:
        engine.dispose()


def main():
    prepare_private_registry()
    production_guard()
    if os.getenv("CREDIT_ENV", "local") == "production":
        if os.getenv("CREDIT_RENDER_AUTO_MIGRATE", "false").lower() == "true":
            migrate_production_database()
        with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
            privileged = connection.execute(
                text(
                    "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname=current_user"
                )
            ).scalar_one()
            if privileged:
                raise RuntimeError("Rôle applicatif PostgreSQL trop privilégié")
            if (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                != ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
            ):
                raise RuntimeError("Migration administrative préalable requise")
    else:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            os.getenv("CREDIT_ASGI_APP", "credit.web.application:app"),
            "--host",
            "0.0.0.0",
            "--port",
            str(listen_port()),
            "--no-access-log",
            "--proxy-headers",
            "--forwarded-allow-ips",
            os.getenv("CREDIT_TRUSTED_PROXY_IPS", "127.0.0.1"),
        ],
    )


if __name__ == "__main__":
    main()
