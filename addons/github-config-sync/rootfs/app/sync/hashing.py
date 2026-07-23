from __future__ import annotations

import fnmatch
import hashlib
import re
from pathlib import Path

IGNORE_DIRS = {
    ".storage",
    ".cloud",
    ".cache",
    ".venv",
    ".vscode",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "tts",
    "__pycache__",
    ".git",
}
IGNORE_PATTERNS = (
    "home-assistant.log",
    "home-assistant.log.*",
    "home-assistant_v2.db",
    "home-assistant_v2.db-*",
    "secrets.yaml",
    "ip_bans.yaml",
    "known_devices.yaml",
    ".ha_run.lock",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.tmp",
    "*.swp",
    "*.pyc",
    "*.log",
    ".yaml_fix_backups",
    ".yaml_fix_backups/*",
    ".ha_fix_yaml.py",
    ".smbdelete*",
    ".DS_Store",
    "Thumbs.db",
)
SENSITIVE_PATTERNS = (
    ".storage/",
    "secrets.yaml",
    "secret",
)
SENSITIVE_NAME_PATTERNS = (
    re.compile(r"(password|passwd|secret|token|credential|private|api[_-]?key|oauth|cookie|session)", re.I),
)
SENSITIVE_CONTENT_PATTERNS = (
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|client_secret)\b\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9]{20,}"),
)


def is_ignored(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/").lower()
    if any(part in IGNORE_DIRS for part in Path(relative_path).parts):
        return True
    if any(pattern in normalized for pattern in SENSITIVE_PATTERNS):
        return True
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in IGNORE_PATTERNS)


def is_sensitive_candidate(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    name = Path(relative_path).name
    return any(pattern.search(normalized) or pattern.search(name) for pattern in SENSITIVE_NAME_PATTERNS)


def scan_sensitive_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    flagged: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if is_ignored(relative):
            continue
        reasons = []
        if is_sensitive_candidate(relative):
            reasons.append("name")
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        if text and any(pattern.search(text) for pattern in SENSITIVE_CONTENT_PATTERNS):
            reasons.append("content")
        if reasons:
            flagged.append(relative)
    return sorted(set(flagged))


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
