"""Détection ciblée locale ; ne restitue jamais la valeur d’un secret éventuel."""

import json
from pathlib import Path
import re
import subprocess

patterns = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}"),
    "aws_access_key": re.compile(r"AKIA[A-Z0-9]{16}"),
}
files = subprocess.run(
    ["git", "ls-files", "-co", "--exclude-standard"], check=True, capture_output=True, text=True
).stdout.splitlines()
findings = []
count = 0
for filename in files:
    path = Path(filename)
    if not path.is_file() or path.suffix in {".pdf", ".png", ".jpg", ".zip"}:
        continue
    try:
        source = path.read_text()
    except (UnicodeError, OSError):
        continue
    count += 1
    for i, line in enumerate(source.splitlines(), 1):
        for kind, pattern in patterns.items():
            if pattern.search(line):
                findings.append({"file": filename, "line": i, "kind": kind})
print(
    json.dumps(
        {
            "files_checked": count,
            "findings": findings,
            "limitation": "Détecteurs ciblés ; absence de correspondance ne prouve pas l’absence de secrets.",
        },
        ensure_ascii=False,
        indent=2,
    )
)
raise SystemExit(bool(findings))
