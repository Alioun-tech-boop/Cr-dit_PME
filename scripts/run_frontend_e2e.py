"""Lancer l'API et Chromium sur un jeu synthétique isolé, puis arrêter le serveur."""

import os
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--browser-test",
    choices=["browser-e2e.cjs", "home-videos.cjs", "budget-widget.cjs", "banking.cjs"],
    default="browser-e2e.cjs",
)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = root / "output/frontend"
output.mkdir(parents=True, exist_ok=True)
run = Path(tempfile.mkdtemp(prefix="browser-", dir=output))
port = os.environ.get("CREDIT_E2E_PORT", "8004")
origin = "http://127.0.0.1:" + port
env = {
    **os.environ,
    "DATABASE_URL": "sqlite:///" + str(run / "database.db"),
    "CREDIT_E2E_OUTPUT": str(run),
    "CREDIT_E2E_URL": origin,
    "CREDIT_AUTH_FILE": str(run / "users.json"),
    "CREDIT_WEB_ORIGIN": origin,
    "CREDIT_ENV": "local",
    "CREDIT_RATE_REQUESTS": "10000",
    "CREDIT_RATE_ACTOR": "10000",
    "CREDIT_RATE_JOBS": "1000",
    "CREDIT_ALLOWED_HOSTS": "127.0.0.1,localhost",
}
if (root / ".local/share/tessdata/fra.traineddata").is_file():
    env.setdefault("TESSDATA_PREFIX", str(root / ".local/share/tessdata"))
if args.browser_test == "banking.cjs":
    env["CREDIT_PARTNER_ALLOW_DEMO"] = "true"
    env["CREDIT_PARTNER_KEYRING_FILE"] = str(run / "keyring.json")
# Préparation avant création de l'application, registre absent initialement : aucune connexion HTTP.
subprocess.run(
    [
        sys.executable,
        "-m",
        "scripts.prepare_partner_e2e"
        if args.browser_test == "banking.cjs"
        else "scripts.prepare_frontend_e2e",
    ],
    cwd=root,
    env=env,
    check=True,
)
with (run / "server.log").open("w") as log:
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "credit.web.application:app",
            "--host",
            "127.0.0.1",
            "--port",
            port,
            "--no-access-log",
        ],
        cwd=root,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError("Le serveur a échoué : " + str(run / "server.log"))
            try:
                urllib.request.urlopen(origin + "/health", timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Démarrage du serveur hors délai")
        subprocess.run(["npm", "run", "build"], cwd=root / "frontend", check=True)
        with (run / "browser.log").open("w") as report:
            result = subprocess.run(
                ["node", "tests/" + args.browser_test],
                cwd=root / "frontend",
                env=env,
                stdout=report,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
        print((run / "browser.log").read_text())
        print("Résultats synthétiques :", run)
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
