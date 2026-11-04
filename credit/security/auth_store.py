"""Écriture atomique du registre local, sous verrou ; aucun secret dans le journal."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


@contextmanager
def locked_registry(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = path.with_suffix(".lock")
    with lock.open("a") as handle:
        os.chmod(lock, 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else {"users": []}
        yield data
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".auth-")
        try:
            with os.fdopen(fd, "w") as out:
                os.fchmod(out.fileno(), 0o600)
                out.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, path)
        finally:
            if Path(tmp).exists():
                Path(tmp).unlink()


def event(path, action, user, institution=None):
    # Journal opérateur séparé, lisible seulement par le compte administrant le registre.
    with Path(path).with_suffix(".audit.jsonl").open("a") as out:
        os.chmod(out.name, 0o600)
        out.write(
            json.dumps(
                {
                    "date": datetime.now(timezone.utc).isoformat(),
                    "event": action,
                    "operator_uid": os.getuid(),
                    "user_id": user,
                    "institution_id": institution,
                }
            )
            + "\n"
        )
        out.flush()
        os.fsync(out.fileno())


def credentials(root, user, token):
    root = Path(root)
    path = root / (hashlib.sha256(user.encode()).hexdigest()[:16] + ".json")
    path.write_text(json.dumps({"user": user, "token": token}) + "\n")
    path.chmod(0o600)
    curl = path.with_suffix(".curl")
    curl.write_text('header = "Authorization: Bearer ' + token + '"\n')
    curl.chmod(0o600)
    return path
