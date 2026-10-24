"""Bounded retention for generated demo artifacts; source datasets are never targets."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

TTL = 7 * 24 * 3600


def retention(now=None):
    created = time.time() if now is None else now
    return {"gerado_por": "susight-backend", "criado_epoch": created, "expira_epoch": created + TTL}


def protect(folder):
    folder = Path(folder)
    folder.chmod(0o700)
    for path in folder.iterdir():
        if path.is_file() and not path.is_symlink():
            path.chmod(0o600)


def purge_artifacts(root, now=None):
    """Remove only marked direct children of an explicitly configured generated-output root."""
    root = Path(root)
    now = time.time() if now is None else now
    removed = []
    if not root.is_dir() or root.is_symlink():
        return removed
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.is_symlink():
            continue
        manifest = folder / "manifesto.json"
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            data = json.loads(manifest.read_text())
            start, end = float(data["criado_epoch"]), float(data["expira_epoch"])
            if data["gerado_por"] != "susight-backend" or not 0 < end - start <= TTL:
                continue
            # Preserve the challenge source even if a manifest is placed there accidentally.
            if any(
                (folder / name).exists()
                for name in ["fila_cirurgica.csv", "eventos_clinicos.csv", "procedimentos.csv"]
            ):
                continue
            if end <= now:
                shutil.rmtree(folder)
                removed.append(folder.name)
        except (KeyError, ValueError, OSError, TypeError):
            continue
    return removed
