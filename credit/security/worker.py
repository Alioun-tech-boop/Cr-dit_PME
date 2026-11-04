"""Réduction de privilèges Linux ; ceci n’est pas un bac à sable du système de fichiers."""

import ctypes
import os
from pathlib import Path
import resource


def harden(root):
    root = Path(root)
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise RuntimeError("worker_hardening_failed")
    if os.geteuid() == 0:
        # Un lancement local en root ne transmet pas ce privilège aux parseurs.
        for path in [root, *root.rglob("*")]:
            if path.is_symlink():
                raise RuntimeError("invalid_worker_path")
            os.chown(path, 65534, 65534)
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)


def environment():
    return {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL", "TESSDATA_PREFIX", "SYSTEMROOT", "PYTHONPATH"}
    }
