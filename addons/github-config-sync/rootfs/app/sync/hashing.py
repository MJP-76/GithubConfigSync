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
    "hacs_frontend",
    "node_modules",
    "include_ssl",
    "include_addon_configs",
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
    ".ruff.toml",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.tmp",
    "*.swp",
    "*.pyc",
    "*.log",
    "*.js.map",
    ".yaml_fix_backups",
    ".yaml_fix_backups/*",
    ".ha_fix_yaml.py",
    ".smbdelete*",
    ".DS_Store",
    "Thumbs.db",
    "core.config_entries",
    ".env",
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

MAX_CONTENT_SCAN_BYTES = 2 * 1024 * 1024


def _is_hard_ignored(relative_path: str) -> bool:
    """Ignore based on ignore dirs/patterns/sensitive substrings only.

    Deliberately excludes is_sensitive_candidate() so that files caught by
    the name-pattern scan still appear in the sensitive-file warning list.
    """
    normalized = relative_path.replace("\\", "/").lower()
    if any(part in IGNORE_DIRS for part in Path(relative_path).parts):
        return True
    if any(pattern in normalized for pattern in SENSITIVE_PATTERNS):
        return True
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in IGNORE_PATTERNS)


def is_ignored(relative_path: str) -> bool:
    if _is_hard_ignored(relative_path):
        return True
    return is_sensitive_candidate(relative_path)


def is_sensitive_candidate(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    name = Path(relative_path).name
    return any(pattern.search(normalized) or pattern.search(name) for pattern in SENSITIVE_NAME_PATTERNS)


def _file_contains_sensitive_content(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(MAX_CONTENT_SCAN_BYTES)
    except OSError:
        return False
    text = sample.decode("utf-8", errors="ignore")
    return any(pattern.search(text) for pattern in SENSITIVE_CONTENT_PATTERNS)


def scan_sensitive_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    flagged: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if _is_hard_ignored(relative):
            continue
        reasons = []
        if is_sensitive_candidate(relative):
            reasons.append("name")
        if _file_contains_sensitive_content(path):
            reasons.append("content")
        if reasons:
            flagged.append(relative)
    return sorted(set(flagged))


def _is_file_sensitive(root: Path, path: Path) -> bool:
    """Check if a file should be excluded from upload."""
    relative = path.relative_to(root).as_posix()
    if is_ignored(relative):
        return True
    return _file_contains_sensitive_content(path)


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
        if _is_file_sensitive(root, path):
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
