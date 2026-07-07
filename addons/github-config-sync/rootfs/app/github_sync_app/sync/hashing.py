from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path

IGNORE_DIRS = {".storage", ".cloud", ".cache", "tts", "__pycache__", ".git"}
IGNORE_PATTERNS = (
    "home-assistant.log",
    "home-assistant.log.*",
    "home-assistant_v2.db",
    "home-assistant_v2.db-*",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.tmp",
    "*.swp",
    "*.pyc",
)


def is_ignored(relative_path: str) -> bool:
    if any(part in IGNORE_DIRS for part in Path(relative_path).parts):
        return True
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in IGNORE_PATTERNS)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_hash_index(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}

    index: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if is_ignored(relative):
            continue
        index[relative] = sha256_file(path)
    return index


def diff_hash_indexes(previous: dict[str, str], current: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    previous_keys = set(previous)
    current_keys = set(current)

    added = sorted(current_keys - previous_keys)
    removed = sorted(previous_keys - current_keys)
    changed = sorted(
        key for key in (current_keys & previous_keys) if previous.get(key) != current.get(key)
    )
    return added, changed, removed
