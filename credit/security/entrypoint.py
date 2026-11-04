"""Démarrage local migré ; en production, migrations séparées et rôle restreint."""

import os
import subprocess
import sys
from sqlalchemy import create_engine, text
from credit.security.runtime import production_guard


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
                != "0006"
            ):
                raise RuntimeError("Migration administrative préalable requise")
    else:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "credit.api:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--no-access-log",
            "--proxy-headers",
            "--forwarded-allow-ips",
            os.getenv("CREDIT_TRUSTED_PROXY_IPS", "127.0.0.1"),
        ],
    )


if __name__ == "__main__":
    main()
