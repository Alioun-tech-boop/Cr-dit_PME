"""Compatibilité CLI : le parcours v0.1 est remplacé par les dépôts v0.2."""

from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("demo_scans.py")), run_name="__main__")
