"""Fixtures navigateur bancaires, explicitement synthétiques et temporaires."""

import os
from pathlib import Path
from scripts.prepare_partner_demo import prepare

root = Path(os.environ["CREDIT_E2E_OUTPUT"]).resolve()
allowed = Path(__file__).resolve().parents[1] / "output/frontend"
if not root.is_relative_to(allowed.resolve()):
    raise RuntimeError("Environnement E2E non isolé")
prepare(root, os.environ["CREDIT_E2E_URL"], test_password="Synthetic-browser-2026!")
