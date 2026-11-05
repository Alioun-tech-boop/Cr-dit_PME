"""Démarrage local migré ; en production, migrations séparées et rôle restreint."""

import os
import subprocess
import sys
from sqlalchemy import create_engine, text
from credit.security.runtime import production_guard
from alembic.config import Config
from alembic.script import ScriptDirectory


def listen_port():
    port = int(os.getenv("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT doit être compris entre 1 et 65535")
    return port


def main():
    production_guard()
    if os.getenv("CREDIT_ENV", "local") == "production":
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
