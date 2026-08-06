from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
import socket
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from flask import Flask, jsonify, request, send_from_directory

from sync import SyncConfig, SyncEngine
from sync.errors import SyncError
from sync.github_client import GitHubClient
from sync.hashing import IGNORE_PATTERNS

def _read_addon_version() -> str:
    """Read version from the add-on config.yaml (single source of truth)."""
    import re
    for candidate in (Path("/app/config.yaml"), Path(__file__).resolve().parent.parent.parent / "config.yaml"):
        try:
            text = candidate.read_text()
            match = re.search(r'^version:\s*["\']?([^"\']+)["\']?\s*$', text, re.MULTILINE)
            if match:
                return match.group(1).strip()
        except Exception as err:
            logging.getLogger(__name__).warning("Could not read version from %s: %s", candidate, err)
    logging.getLogger(__name__).warning(
        "Could not determine add-on version from config.yaml, falling back to 0.0.0"
    )
    return "0.0.0"


APP_VERSION = _read_addon_version()
STABLE_REPO_VERSION = APP_VERSION
DEV_REPO_VERSION = APP_VERSION
APP_PORT = 8099
DEFAULT_OAUTH_CLIENT_ID = "Ov23li2ycCraodta6WCU"
DEFAULT_NEW_REPO_NAME = "ha-github-config-sync"
ADDON_REPO_MARKER_PATH = ".github-config-sync-addon.json"
SENSITIVE_WARNING_PATH = "SECURITY_UPLOAD_WARNINGS.md"

DATA_DIR = Path("/data")
SUPERVISOR_OPTIONS_PATH = DATA_DIR / "options.json"
WEBUI_OPTIONS_PATH = DATA_DIR / "webui_options.json"
STATE_PATH = DATA_DIR / "state.json"
LOG_PATH = DATA_DIR / "sync.log"
HASH_INDEX_PATH = DATA_DIR / "hash_index.json"
DEVICE_FLOW_PATH = DATA_DIR / "device_flow.json"
MANAGED_REPOS_PATH = DATA_DIR / "managed_repos.json"
STATIC_DIR = Path("/app/static")
CONFIG_ROOT = Path("/config")
CHANGELOG_PATH = Path(__file__).resolve().parent / "CHANGELOG.md"

logging.getLogger("werkzeug").setLevel(logging.ERROR)

ALLOWED_SYNC_ROOTS = {"/config", "/media", "/share", "/ssl", "/backups", "/www", "/addon_configs"}


def _is_private_ip(ip: str) -> bool:
    """Return True if IP is in private ranges (RFC 1918)."""
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        a, b = int(parts[0]), int(parts[1])
        return (
            a == 10
            or (a == 172 and 16 <= b <= 31)
            or (a == 192 and b == 168)
            or a == 127
        )
    except (ValueError, IndexError):
        return False


def _via_ingress_proxy() -> bool:
    """Return True when the request arrived through the Supervisor ingress proxy.

    The Supervisor's ingress proxy forwards Home Assistant authenticated
    requests to the add-on directly, so the TCP peer is usually the Supervisor
    container. As a fallback, we also trust requests that carry the
    ``X-Hass-Source: core.ingress`` header set by HA Core, provided the peer
    is on a private network (HA Core/Supervisor always are).
    """
    logger = logging.getLogger(__name__)
    try:
        supervisor_ip = socket.gethostbyname("supervisor")
    except OSError as err:
        logger.debug("Could not resolve supervisor hostname: %s", err)
        supervisor_ip = None

    client_ip = request.remote_addr

    # Primary check: direct Supervisor peer
    if supervisor_ip and client_ip == supervisor_ip:
        return True

    # Fallback: HA Core ingress header + private network peer
    if request.headers.get("X-Hass-Source") == "core.ingress" and _is_private_ip(client_ip):
        logger.debug(
            "Ingress auth via X-Hass-Source fallback: client_ip=%s", client_ip
        )
        return True

    if supervisor_ip:
        logger.debug(
            "Ingress check failed: client_ip=%s supervisor_ip=%s hass_source=%s",
            client_ip,
            supervisor_ip,
            request.headers.get("X-Hass-Source"),
        )
    return False


def _require_auth() -> bool:
    """Return True if request is authenticated.

    Via ingress: the request must have been proxied by the Supervisor (i.e. it
    already passed Home Assistant authentication and an ingress session check).
    Via raw port 8099: must supply the configured github_token as Bearer.
    """
    if os.environ.get("FLASK_DEBUG") == "1":
        return True
    if _via_ingress_proxy():
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        configured = str(_merge_options().get("github_token", "")).strip()
        if configured and token == configured:
            return True
    return False


def _assert_safe_path(path: Path, allowed_roots: set[str]) -> None:
    """Ensure a resolved path is within one of the allowed root directories."""

    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return
        except ValueError:
            continue
    raise SyncError(f"Path escapes allowed sync roots: {path}")


_REDACT_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{80,}"),
    re.compile(r"gho_[A-Za-z0-9]{36,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r'(?i)(password|passwd|secret|token|api[_-]?key|client_secret|oauth)["\s:=]+\S+'),
    re.compile(r'https?://[^@\s]+:[^@\s]+@[^\s]+'),
]


def _redact_line(line: str) -> str:
    for pattern in _REDACT_PATTERNS:
        line = pattern.sub("[REDACTED]", line)
    return line


DEFAULT_OPTIONS: dict[str, Any] = {
    "auth_method": "device_flow",
    "repo_mode": "existing",
    "existing_repo_confirmed_for": "",
    "github_repository": "",
    "github_branch": "main",
    "github_token": "",
    "github_client_id": DEFAULT_OAUTH_CLIENT_ID,
    "version_retention_count": 7,
    "dry_run": True,
    "auto_sync_enabled": False,
    "auto_sync_days": [1, 2, 3, 4, 5],
    "auto_sync_time": "03:00",
    "auto_sync_create_release": True,
    "sync_interval_minutes": 1440,
    "include_addon_configs": False,
    "include_media": False,
    "include_share": False,
    "include_ssl": False,
    "include_backups": False,
    "include_www": False,
    "sync_mode": "whitelist",
}


def _repo_safety_state(engine: SyncEngine) -> tuple[bool, str]:
    contents = engine._github.list_directory_contents()  # pylint: disable=protected-access
    if not isinstance(contents, list):
        contents = []
    marker_present = any(
        isinstance(item.get("path"), str) and item["path"] == ADDON_REPO_MARKER_PATH for item in contents
    )
    if marker_present:
        return True, "Repository marker found"
    if not contents:
        return True, "Repository is empty"
    return False, "Repository was not created by this add-on and is not empty"


def _repo_sync_config(options: dict[str, Any], repository: str) -> SyncConfig:
    return SyncConfig(
        repository=repository,
        branch=str(options.get("github_branch", "main")).strip() or "main",
        token=str(options.get("github_token", "")).strip(),
        config_root=str(CONFIG_ROOT),
        dry_run=bool(options.get("dry_run", True)),
        addon_config_root="/addon_configs" if bool(options.get("include_addon_configs", False)) else "",
        include_media=bool(options.get("include_media", False)),
        include_share=bool(options.get("include_share", False)),
        include_ssl=bool(options.get("include_ssl", False)),
        include_backups=bool(options.get("include_backups", False)),
        include_www=bool(options.get("include_www", False)),
        include_addon_configs=bool(options.get("include_addon_configs", False)),
        sync_mode=str(options.get("sync_mode", "whitelist")),
    )


def _existing_repo_confirmation_error(options: dict[str, Any]) -> str | None:
    if str(options.get("repo_mode", "existing")).strip() != "existing":
        return None
    repository = str(options.get("github_repository", "")).strip()
    if not repository:
        return None
    if str(options.get("existing_repo_confirmed_for", "")).strip() == repository:
        return None
    try:
        engine = SyncEngine(_repo_sync_config(options, repository), previous_hash_index={})
        safe, _reason = _repo_safety_state(engine)
        if safe:
            return None
    except SyncError:
        pass
    return (
        "Using an existing repository can overwrite or delete remote files. "
        "Tick the existing-repo confirmation checkbox in Repository setup before continuing."
    )


def _ensure_repo_marker(engine: SyncEngine, repository: str) -> None:
    engine._github.write_repo_marker(  # pylint: disable=protected-access
        {"created_by": "github-config-sync-addon", "repository": repository}
    )


def _restore_repo_skeleton_and_marker(engine: SyncEngine, repository: str) -> None:
    engine.restore_repo_skeleton()
    _ensure_repo_marker(engine, repository)


def _format_sensitive_warning(sensitive_files: list[str]) -> str:
    lines = [
        "# Security upload warnings",
        "",
        "These files were not uploaded because they look like they may contain secrets, passwords, or personal details:",
        "",
    ]
    lines.extend(f"- `{item}`" for item in sensitive_files)
    lines.extend(
        [
            "",
            "Review them locally before removing them from the ignore list.",
        ]
    )
    return "\n".join(lines) + "\n"


def _sync_sensitive_warning(engine: SyncEngine) -> list[str]:
    sensitive_files = engine.sensitive_files()
    remote = engine._github.get_content(SENSITIVE_WARNING_PATH)  # pylint: disable=protected-access
    if sensitive_files:
        warning = _format_sensitive_warning(sensitive_files)
        sha = remote.get("sha") if isinstance(remote, dict) else None
        engine._github.put_content(  # pylint: disable=protected-access
            path=SENSITIVE_WARNING_PATH,
            content=warning.encode("utf-8"),
            message="sync: update security warnings",
            sha=sha if isinstance(sha, str) else None,
        )
    elif remote and isinstance(remote.get("sha"), str):
        engine._github.delete_content(  # pylint: disable=protected-access
            path=SENSITIVE_WARNING_PATH,
            sha=remote["sha"],
            message="sync: remove security warnings",
        )
    return sensitive_files

DEFAULT_STATE: dict[str, Any] = {
    "status": "idle",
    "last_run": None,
    "last_success": None,
    "last_error": None,
    "last_result": None,
    "last_scan": None,
}


def _display_repo_version(value: str | None, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback


def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(fallback)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(fallback)
    if not isinstance(parsed, dict):
        return dict(fallback)
    return parsed


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _merge_options() -> dict[str, Any]:
    options = dict(DEFAULT_OPTIONS)
    options.update(_load_json(SUPERVISOR_OPTIONS_PATH, {}))
    options.update(_load_json(WEBUI_OPTIONS_PATH, {}))
    return options


def _load_state() -> dict[str, Any]:
    state = dict(DEFAULT_STATE)
    state.update(_load_json(STATE_PATH, {}))
    return state


def _reset_stale_runtime_state() -> None:
    state = _load_state()
    if state.get("status") != "running" and not state.get("cancel_sync", False):
        return
    state.update(
        {
            "status": "idle",
            "cancel_sync": False,
            "last_result": None,
            "last_scan": None,
            "sync_progress": None,
        }
    )
    _save_json(STATE_PATH, state)


def _set_cancel_requested(value: bool) -> dict[str, Any]:
    return _save_state({"cancel_sync": value})


def _is_cancel_requested() -> bool:
    return bool(_load_state().get("cancel_sync", False))


def _save_state(updates: dict[str, Any]) -> dict[str, Any]:
    state = _load_state()
    state.update(updates)
    _save_json(STATE_PATH, state)
    return state


def _clear_sync_progress_state() -> dict[str, Any]:
    return {
        "sync_progress": None,
        "sync_progress_current_path_started_at": None,
        "sync_progress_last_seen_at": None,
    }


def _persist_options(payload: dict[str, Any]) -> None:
    _save_json(SUPERVISOR_OPTIONS_PATH, payload)
    _save_json(WEBUI_OPTIONS_PATH, payload)


def _append_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _validate_payload(payload: dict[str, Any]) -> tuple[bool, str | None]:
    repo_mode = str(payload.get("repo_mode", "existing")).strip()
    if repo_mode not in ("existing", "create"):
        return False, "repo_mode must be existing or create"

    repository = str(payload.get("github_repository", "")).strip()
    if repository and repository.count("/") != 1:
        return False, "github_repository must be in owner/repo format"
    existing_repo_confirmed_for = str(payload.get("existing_repo_confirmed_for", "")).strip()
    if existing_repo_confirmed_for and existing_repo_confirmed_for.count("/") != 1:
        return False, "existing_repo_confirmed_for must be in owner/repo format"

    branch = str(payload.get("github_branch", "")).strip()
    if not branch:
        return False, "github_branch is required"


    retention_raw = payload.get("version_retention_count")
    try:
        retention = int(retention_raw)
    except (TypeError, ValueError):
        return False, "version_retention_count must be an integer"
    if retention < 1 or retention > 100:
        return False, "version_retention_count must be between 1 and 100"


    if not isinstance(payload.get("dry_run"), bool):
        return False, "dry_run must be true or false"
    if not isinstance(payload.get("auto_sync_enabled"), bool):
        return False, "auto_sync_enabled must be true or false"
    if not isinstance(payload.get("auto_sync_create_release"), bool):
        return False, "auto_sync_create_release must be true or false"
    auto_sync_time = str(payload.get("auto_sync_time", "03:00")).strip()
    if auto_sync_time and ":" not in auto_sync_time:
        return False, "auto_sync_time must be in HH:MM format"
    auto_sync_days = payload.get("auto_sync_days", [])
    if isinstance(auto_sync_days, str):
        auto_sync_days = [d.strip() for d in auto_sync_days.split(",") if d.strip()]
    if auto_sync_days:
        for day in auto_sync_days:
            try:
                d = int(day)
                if d < 1 or d > 7:
                    return False, "auto_sync_days must contain values 1-7 (Mon-Sun)"
            except (TypeError, ValueError):
                return False, "auto_sync_days must contain integers 1-7 (Mon-Sun)"

    if str(payload.get("auth_method", "device_flow")) not in ("device_flow", "fine_grained_pat"):
        return False, "auth_method must be device_flow or fine_grained_pat"
    sync_mode = str(payload.get("sync_mode", "whitelist")).strip()
    if sync_mode not in ("whitelist", "blacklist"):
        return False, "sync_mode must be whitelist or blacklist"

    for key in (
        "include_addon_configs",
        "include_media",
        "include_share",
        "include_ssl",
        "include_backups",
        "include_www",
    ):
        if not isinstance(payload.get(key), bool):
            return False, f"{key} must be true or false"

    return True, None


def _mask_token(options: dict[str, Any]) -> dict[str, Any]:
    output = dict(options)
    token = output.get("github_token") or ""
    if token:
        output["github_token"] = "********"
    return output


def _auth_diagnostics(options: dict[str, Any]) -> dict[str, Any]:
    token = str(options.get("github_token", "")).strip()
    repository = str(options.get("github_repository", "")).strip()
    return {
        "repository_configured": bool(repository),
        "token_configured": bool(token),
        "token_saved": bool(token),
        "token_state": "configured" if token else "missing",
        "repository_state": "configured" if repository else "missing",
    }


def _token_health(options: dict[str, Any]) -> dict[str, Any]:
    token = str(options.get("github_token", "")).strip()
    if not token:
        return {"state": "missing", "message": "No token saved"}

    # Stable cache key using SHA256 (not Python's randomized hash())
    cache_key = f"_token_health_cache_{hashlib.sha256(token.encode()).hexdigest()[:16]}"
    cached = _load_state().get(cache_key)
    if cached and time.time() - cached.get("timestamp", 0) < 300:
        logging.getLogger(__name__).debug("Token health cache hit: %s", cached["result"]["state"])
        return cached["result"]

    client = GitHubClient(
        repository=str(options.get("github_repository", "")).strip(),
        branch=str(options.get("github_branch", "main")).strip() or "main",
        token=token,
    )
    try:
        client._request_json("GET", "https://api.github.com/user")  # pylint: disable=protected-access
    except SyncError as err:
        message = str(err)
        logger = logging.getLogger(__name__)
        logger.warning("Token health check failed: %s", message)
        # Distinguish rate limit (403 with rate limit context) from auth failure
        if "HTTP 401" in message:
            result = {"state": "expired", "message": "GitHub rejected the token"}
        elif "HTTP 403" in message:
            # Check if error body mentions rate limit
            body_lower = message.lower()
            if any(kw in body_lower for kw in ("rate limit", "secondary rate limit", "abuse detection", "x-ratelimit-remaining", "x-ratelimit-reset")):
                result = {"state": "rate_limited", "message": "GitHub rate limit exceeded"}
            else:
                result = {"state": "rate_limited", "message": "GitHub rate limit likely exceeded"}
        else:
            result = {"state": "error", "message": message}
        # Cache the negative result for 30 seconds to avoid hammering on repeated failures
        _save_state({f"_token_health_cache_{hashlib.sha256(token.encode()).hexdigest()[:16]}": {"timestamp": time.time(), "result": result}})
        return result

    result = {"state": "valid", "message": "GitHub accepted the token"}
    _save_state({f"_token_health_cache_{hashlib.sha256(token.encode()).hexdigest()[:16]}": {"timestamp": time.time(), "result": result}})
    return result

    result = {"state": "valid", "message": "GitHub accepted the token"}
    _save_state({f"_token_health_cache_{hash(token)}": {"timestamp": time.time(), "result": result}})
    return result

    result = {"state": "valid", "message": "GitHub accepted the token"}
    _save_state({cache_key: {"timestamp": time.time(), "result": result}})
    return result


def _sanitized_log_tail(limit: int = 4000) -> str:
    if not LOG_PATH.exists():
        return ""
    raw = LOG_PATH.read_text(encoding="utf-8")[-limit:]
    return "\n".join(_redact_line(line) for line in raw.splitlines())


def _read_changelog_entries(limit: int = 5) -> list[str]:
    if not CHANGELOG_PATH.exists():
        return []
    entries: list[str] = []
    for raw_line in CHANGELOG_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line in {"<!-- VERSION:START -->", "<!-- VERSION:END -->"}:
            continue
        if line.startswith("- "):
            entries.append(line[2:].strip())
            if len(entries) >= limit:
                break
    return entries


def _load_managed_repos() -> list[dict[str, Any]]:
    if not MANAGED_REPOS_PATH.exists():
        return []
    try:
        data = json.loads(MANAGED_REPOS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    repos: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        full_name = str(item.get("full_name", "")).strip()
        if not full_name:
            continue
        repos.append(
            {
                "name": str(item.get("name", "")).strip(),
                "full_name": full_name,
                "private": bool(item.get("private", False)),
                "managed": bool(item.get("managed", True)),
            }
        )
    return repos


def _save_managed_repos(repos: list[dict[str, Any]]) -> None:
    MANAGED_REPOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANAGED_REPOS_PATH.write_text(json.dumps(repos, indent=2, sort_keys=True), encoding="utf-8")


def _repo_has_addon_marker(options: dict[str, Any], repository: str) -> bool:
    engine = SyncEngine(_repo_sync_config(options, repository), previous_hash_index={})
    contents = engine._github.list_directory_contents()  # pylint: disable=protected-access
    return any(
        isinstance(item.get("path"), str) and item["path"] == ADDON_REPO_MARKER_PATH
        for item in contents
        if isinstance(item, dict)
    )


def _repo_picker_entries(
    options: dict[str, Any], query: str = "", include_unmanaged: bool = False
) -> list[dict[str, Any]]:
    client = _token_client(options)
    repos = client.list_user_repositories(query=query, limit=100)
    cached_repos = _load_managed_repos()
    cached_by_name = {
        str(item.get("full_name", "")).strip(): item
        for item in cached_repos
        if str(item.get("full_name", "")).strip()
    }
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for repo in repos:
        full_name = str(repo.get("full_name", "")).strip()
        if not full_name or full_name in seen:
            continue
        seen.add(full_name)
        managed = False
        try:
            managed = _repo_has_addon_marker(options, full_name)
        except SyncError:
            managed = False
        if not include_unmanaged and not managed:
            continue
        combined.append(
            {
                "name": str(repo.get("name", "")).strip(),
                "full_name": full_name,
                "private": bool(repo.get("private", False)),
                "managed": managed,
            }
        )

    current_repo = str(options.get("github_repository", "")).strip()
    if current_repo and current_repo not in seen:
        managed = False
        try:
            managed = _repo_has_addon_marker(options, current_repo)
        except SyncError:
            managed = False
        if not include_unmanaged and not managed:
            return combined
        combined.insert(
            0,
            {
                "name": current_repo.rsplit("/", 1)[-1],
                "full_name": current_repo,
                "private": True,
                "managed": managed,
            },
        )
    return combined


def _diagnostics_bundle() -> dict[str, Any]:
    options = _merge_options()
    state = _load_state()
    return {
        "ok": True,
        "version": APP_VERSION,
        "auth": _auth_diagnostics(options),
        "token_health": _token_health(options),
        "options": _mask_token(options),
        "state": state,
        "log_tail": _sanitized_log_tail(),
    }


def _sync_config(options: dict[str, Any]) -> SyncConfig:
    return SyncConfig(
        repository=str(options.get("github_repository", "")).strip(),
        branch=str(options.get("github_branch", "main")).strip() or "main",
        token=str(options.get("github_token", "")).strip(),
        config_root=str(CONFIG_ROOT),
        dry_run=bool(options.get("dry_run", True)),
        addon_config_root="/addon_configs" if bool(options.get("include_addon_configs", False)) else "",
        include_media=bool(options.get("include_media", False)),
        include_share=bool(options.get("include_share", False)),
        include_ssl=bool(options.get("include_ssl", False)),
        include_backups=bool(options.get("include_backups", False)),
        include_www=bool(options.get("include_www", False)),
        include_addon_configs=bool(options.get("include_addon_configs", False)),
        sync_mode=str(options.get("sync_mode", "whitelist")),
    )


def _token_client(options: dict[str, Any]) -> GitHubClient:
    token = str(options.get("github_token", "")).strip()
    if not token:
        raise SyncError(
            "GitHub token is missing. Complete Device Flow login before listing repositories."
        )
    return GitHubClient(
        repository=str(options.get("github_repository", "")).strip(),
        branch=str(options.get("github_branch", "main")).strip() or "main",
        token=token,
    )


def _build_verification_url(device_flow: dict[str, Any]) -> str:
    complete = str(device_flow.get("verification_uri_complete", "")).strip()
    if complete:
        return complete
    base = str(device_flow.get("verification_uri", "https://github.com/login/device")).strip()
    user_code = str(device_flow.get("user_code", "")).strip()
    if not user_code:
        return base
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}user_code={quote(user_code)}"


def _load_device_flow() -> dict[str, Any]:
    return _load_json(DEVICE_FLOW_PATH, {})


def _save_device_flow(payload: dict[str, Any]) -> None:
    _save_json(DEVICE_FLOW_PATH, payload)


def _clear_device_flow() -> None:
    if DEVICE_FLOW_PATH.exists():
        DEVICE_FLOW_PATH.unlink()


def _plan_summary(plan) -> dict[str, Any]:
    changed_count = len(plan.added) + len(plan.changed)
    return {
        "added_count": len(plan.added),
        "changed_count": len(plan.changed),
        "removed_count": len(plan.removed),
        "unchanged_count": plan.total_files - changed_count - len(plan.removed),
        "total_files": plan.total_files,
        "added_files": plan.added[:50],
        "changed_files": plan.changed[:50],
        "removed_files": plan.removed[:50],
    }


def _sync_progress_payload(payload: dict[str, Any]) -> dict[str, Any]:
    current_path = str(payload.get("current_path", "")).strip()
    previous = _load_state()
    previous_path = str(previous.get("sync_progress", {}).get("current_path", "")).strip() if isinstance(previous.get("sync_progress"), dict) else ""
    current_path_started_at = previous.get("sync_progress", {}).get("current_path_started_at") if isinstance(previous.get("sync_progress"), dict) else None
    if current_path and current_path != previous_path:
        current_path_started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    if not current_path:
        current_path_started_at = None
    return {
        "sync_progress": payload,
        "sync_progress_last_seen_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sync_progress_current_path_started_at": current_path_started_at,
        "status": payload.get("status", "running"),
    }


def _run_sync(sync_config: SyncConfig, clean_upload: bool = False) -> tuple[int, dict[str, Any], str | None]:
    previous_index = _load_json(HASH_INDEX_PATH, {})
    engine = SyncEngine(sync_config, previous_hash_index=previous_index)
    if clean_upload:
        plan, current_hash_index = engine.clean_plan()
    else:
        plan, current_hash_index = engine.plan()
    engine.set_progress_callback(lambda payload: _save_state(_sync_progress_payload(payload)))

    scan = _plan_summary(plan)
    _append_log(
        "Scan summary: "
        f"+{scan['added_count']} "
        f"~{scan['changed_count']} "
        f"-{scan['removed_count']} "
        f"files={scan['total_files']}"
    )

    if not sync_config.dry_run:
        probe_ok, probe_message = engine._github.probe_repository()  # pylint: disable=protected-access
        if not probe_ok:
            friendly_message = probe_message
            if "HTTP 401" in probe_message or "HTTP 403" in probe_message:
                friendly_message = (
                    "GitHub rejected the repository probe. "
                    "Check that the token is valid and has repo access."
                )
            elif "HTTP 404" in probe_message:
                friendly_message = (
                    "GitHub could not find the repository. "
                    "Check the repository name, visibility, and token access."
                )
            raise SyncError(friendly_message)

    result = engine.run(plan)
    if not sync_config.dry_run:
        _ensure_repo_marker(engine, sync_config.repository)
    _save_json(HASH_INDEX_PATH, current_hash_index)
    return 200, scan, result.message


class _SyncScheduler:
    """Background scheduler that runs sync at configured days/times.

    Polls every 30 seconds and checks if current day-of-week and time match
    the configured schedule. Creates a dated release before each scheduled sync
    and prunes old releases based on version_retention_count.
    """

    POLL_INTERVAL = 30

    def __init__(self) -> None:
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._running = False
        self._last_triggered_minute: str | None = None

    def restart(self) -> None:
        """Cancel any pending timer and start a fresh poll cycle."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._last_triggered_minute = None
        self._schedule_next_poll()

    def _schedule_next_poll(self) -> None:
        with self._lock:
            self._timer = threading.Timer(self.POLL_INTERVAL, self._poll)
            self._timer.daemon = True
            self._timer.start()

    def _poll(self) -> None:
        try:
            options = _merge_options()
            if not options.get("auto_sync_enabled"):
                return
            if not options.get("github_token") or not options.get("github_repository"):
                return
            now = dt.datetime.now(dt.timezone.utc)
            local_now = now.astimezone()
            day_of_week = local_now.isoweekday()
            auto_days = options.get("auto_sync_days", [])
            if isinstance(auto_days, str):
                auto_days = [int(d) for d in auto_days.split(",") if d.strip().isdigit()]
            if day_of_week not in [int(d) for d in auto_days]:
                return
            configured_time = str(options.get("auto_sync_time", "03:00")).strip()
            current_minute = local_now.strftime("%H:%M")
            trigger_key = f"{local_now.strftime('%Y-%m-%d')}:{current_minute}"
            if trigger_key == self._last_triggered_minute:
                return
            if current_minute != configured_time:
                return
            self._last_triggered_minute = trigger_key
            self._do_sync(options)
        except Exception as err:
            _append_log(f"Scheduler poll error: {err}")
        finally:
            self._schedule_next_poll()

    def _do_sync(self, options: dict[str, Any]) -> None:
        with self._lock:
            if self._running:
                _append_log("Scheduler: sync already in progress, skipping")
                return
            self._running = True
        try:
            token = str(options.get("github_token", "")).strip()
            repository = str(options.get("github_repository", "")).strip()
            dry_run = False
            sync_config = SyncConfig(
                repository=repository,
                branch=str(options.get("github_branch", "main")).strip() or "main",
                token=token,
                config_root=str(CONFIG_ROOT),
                dry_run=dry_run,
                addon_config_root="/addon_configs" if bool(options.get("include_addon_configs", False)) else "",
                include_media=bool(options.get("include_media", False)),
                include_share=bool(options.get("include_share", False)),
                include_ssl=bool(options.get("include_ssl", False)),
                include_backups=bool(options.get("include_backups", False)),
                include_www=bool(options.get("include_www", False)),
                include_addon_configs=bool(options.get("include_addon_configs", False)),
                sync_mode=str(options.get("sync_mode", "whitelist")),
            )
            now = dt.datetime.now(dt.timezone.utc)
            local_now = now.astimezone()
            tag_name = f"sync-{local_now.strftime('%d/%m/%y-%H/%M/%S').replace('/', '-')}"
            release_name = f"Sync {local_now.strftime('%d/%m/%y %H:%M:%S')}"
            if not dry_run and options.get("auto_sync_create_release", True):
                try:
                    github = GitHubClient(repository=repository, branch=sync_config.branch, token=token)
                    github.create_release(tag_name=tag_name, name=release_name, body=f"Auto-sync release created at {release_name}")
                    _append_log(f"Scheduler: created release {tag_name}")
                    retention = int(options.get("version_retention_count", 7))
                    releases = github.list_releases()
                    sync_releases = [r for r in releases if isinstance(r.get("tag_name"), str) and r["tag_name"].startswith("sync-")]
                    sync_releases.sort(key=lambda r: r.get("created_at", ""), reverse=True)
                    for old in sync_releases[retention:]:
                        old_id = old.get("id")
                        old_tag = old.get("tag_name", "")
                        if old_id:
                            try:
                                github.delete_release(int(old_id))
                                github.delete_tag(old_tag)
                                _append_log(f"Scheduler: pruned old release {old_tag}")
                            except SyncError:
                                pass
                except SyncError as err:
                    _append_log(f"Scheduler: release creation failed: {err}")
            started = now.isoformat()
            _append_log(f"Scheduler: sync started for {repository} (dry_run={dry_run})")
            _save_state({"status": "running", "last_run": started, "last_error": None, **_clear_sync_progress_state()})
            scan: dict[str, Any] | None = None
            try:
                engine = SyncEngine(sync_config, previous_hash_index=_load_json(HASH_INDEX_PATH, {}))
                engine.set_progress_callback(lambda payload: _save_state(_sync_progress_payload(payload)))
                plan, current_hash_index = engine.plan()
                scan = _plan_summary(plan)
                if not sync_config.dry_run:
                    probe_ok, probe_message = engine._github.probe_repository()
                    if not probe_ok:
                        raise SyncError(probe_message)
                result = engine.run(plan)
                if not sync_config.dry_run:
                    _ensure_repo_marker(engine, sync_config.repository)
                _save_json(HASH_INDEX_PATH, current_hash_index)
                _save_state({
                    "status": "ok",
                    "last_success": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "last_result": result.message,
                    "last_scan": scan,
                    "last_error": None,
                    **_clear_sync_progress_state(),
                })
                _append_log(f"Scheduler: {result.message}")
            except SyncError as err:
                _save_state({
                    "status": "error",
                    "last_error": str(err),
                    "last_result": None,
                    "last_scan": scan,
                    **_clear_sync_progress_state(),
                })
                _append_log(f"Scheduler: sync failed: {err}")
            except Exception as err:
                _save_state({
                    "status": "error",
                    "last_error": str(err),
                    "last_result": None,
                    "last_scan": scan,
                    **_clear_sync_progress_state(),
                })
                _append_log(f"Scheduler: unexpected error: {err}")
        finally:
            with self._lock:
                self._running = False

    @property
    def next_run_info(self) -> dict[str, Any]:
        options = _merge_options()
        if not options.get("auto_sync_enabled"):
            return {"enabled": False}
        auto_days = options.get("auto_sync_days", [])
        if isinstance(auto_days, str):
            auto_days = [int(d) for d in auto_days.split(",") if d.strip().isdigit()]
        configured_time = str(options.get("auto_sync_time", "03:00")).strip()
        return {
            "enabled": True,
            "days": auto_days,
            "time": configured_time,
            "create_release": bool(options.get("auto_sync_create_release", True)),
        }


_scheduler = _SyncScheduler()


app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
_reset_stale_runtime_state()
_scheduler.restart()


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "version": APP_VERSION})


@app.post("/api/sync/manual")
def trigger_manual_sync():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    options = _merge_options()
    sync_config = _sync_config(options)
    if not sync_config.repository:
        return jsonify({"ok": False, "error": "github_repository is required"}), 400
    if sync_config.dry_run:
        engine = SyncEngine(sync_config, previous_hash_index=_load_json(HASH_INDEX_PATH, {}))
        plan, _ = engine.plan()
        scan = _plan_summary(plan)
        started = dt.datetime.now(dt.timezone.utc).isoformat()
        result_message = (
            "Dry run completed. "
            f"Would upsert {scan['added_count'] + scan['changed_count']} files and delete {scan['removed_count']} files."
        )
        _save_state(
            {
                "status": "ok",
                "last_run": started,
                "last_error": None,
                "last_result": result_message,
                "last_scan": scan,
                **_clear_sync_progress_state(),
            }
        )
        return jsonify(
            {
                "ok": True,
                "result": result_message,
                "summary": {
                    **scan,
                    "synced_count": scan["added_count"] + scan["changed_count"],
                    "deleted_count": scan["removed_count"],
                    "skipped_count": 0,
                },
                "state": _load_state(),
            }
        )

    confirmation_error = _existing_repo_confirmation_error(options)
    if confirmation_error:
        return jsonify({"ok": False, "error": confirmation_error}), 400

    started = dt.datetime.now(dt.timezone.utc).isoformat()
    _save_state(
        {
            "status": "running",
            "last_run": started,
            "last_error": None,
            "last_result": None,
            "last_scan": None,
            **_clear_sync_progress_state(),
        }
    )
    _set_cancel_requested(False)
    _append_log(f"Manual sync started for {sync_config.repository}")

    scan: dict[str, Any] | None = None
    try:
        sync_config = SyncConfig(
            repository=sync_config.repository,
            branch=sync_config.branch,
            token=sync_config.token,
            config_root=sync_config.config_root,
            addon_config_root=sync_config.addon_config_root,
            dry_run=bool(options.get("dry_run", True)),
            include_media=sync_config.include_media,
            include_share=sync_config.include_share,
            include_ssl=sync_config.include_ssl,
            include_backups=sync_config.include_backups,
            include_www=sync_config.include_www,
            include_addon_configs=sync_config.include_addon_configs,
            sync_mode=sync_config.sync_mode,
        )
        engine = SyncEngine(sync_config, previous_hash_index=_load_json(HASH_INDEX_PATH, {}))
        engine.set_cancel_checker(_is_cancel_requested)
        engine.set_progress_callback(lambda payload: _save_state(_sync_progress_payload(payload)))
        plan, current_hash_index = engine.plan()
        scan = _plan_summary(plan)
        probe_ok, probe_message = engine._github.probe_repository()  # pylint: disable=protected-access
        if not probe_ok:
            raise SyncError(probe_message)
        result = engine.run(plan)
        _save_json(HASH_INDEX_PATH, current_hash_index)
    except SyncError as err:
        state = _save_state(
            {
                "status": "error",
                "last_error": str(err),
                "last_result": None,
                "last_scan": scan,
                **_clear_sync_progress_state(),
            }
        )
        return jsonify({"ok": False, "error": str(err), "state": state}), 502

    state = _save_state(
        {
            "status": "ok",
            "last_success": dt.datetime.now(dt.timezone.utc).isoformat(),
            "last_result": result.message,
            "last_scan": scan,
            "last_error": None,
            **_clear_sync_progress_state(),
        }
    )
    return jsonify(
        {
            "ok": True,
            "result": result.message,
            "summary": {
                **scan,
                "synced_count": result.synced_count,
                "deleted_count": result.deleted_count,
                "skipped_count": result.skipped_count,
                "total_files": result.total_files,
            },
            "state": state,
        }
    )


@app.get("/api/options")
def get_options():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    return jsonify(_mask_token(_merge_options()))


@app.post("/api/options")
def set_options():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400

    candidate = {
        "auth_method": str(payload.get("auth_method", _merge_options().get("auth_method", "device_flow"))).strip()
        or "device_flow",
        "repo_mode": str(payload.get("repo_mode", _merge_options().get("repo_mode", "existing"))).strip()
        or "existing",
        "existing_repo_confirmed_for": str(payload.get("existing_repo_confirmed_for", "")).strip(),
        "github_repository": str(payload.get("github_repository", "")).strip(),
        "github_branch": str(payload.get("github_branch", "main")).strip() or "main",
        "github_token": str(payload.get("github_token", "")).strip() or _merge_options().get("github_token", ""),
        "github_client_id": str(
            payload.get("github_client_id", _merge_options().get("github_client_id", DEFAULT_OAUTH_CLIENT_ID))
        ).strip()
        or DEFAULT_OAUTH_CLIENT_ID,
        "version_retention_count": payload.get("version_retention_count", 7),
        "dry_run": payload.get("dry_run", True),
        "auto_sync_enabled": payload.get("auto_sync_enabled", False),
        "auto_sync_days": payload.get("auto_sync_days", [1, 2, 3, 4, 5]),
        "auto_sync_time": str(payload.get("auto_sync_time", "03:00")).strip() or "03:00",
        "auto_sync_create_release": payload.get("auto_sync_create_release", True),
        "include_addon_configs": payload.get("include_addon_configs", False),
        "include_media": payload.get("include_media", False),
        "include_share": payload.get("include_share", False),
        "include_ssl": payload.get("include_ssl", False),
        "include_backups": payload.get("include_backups", False),
        "include_www": payload.get("include_www", False),
        "sync_mode": str(payload.get("sync_mode", "whitelist")).strip() or "whitelist",
    }

    valid, message = _validate_payload(candidate)
    if not valid:
        return jsonify({"ok": False, "error": message}), 400

    _persist_options(candidate)
    _append_log("Settings updated via web UI")
    _scheduler.restart()
    return jsonify({"ok": True, "options": _mask_token(_merge_options())})


@app.get("/api/status")
def get_status():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    state = _load_state()
    options = _merge_options()
    return jsonify(
        {
            "ok": True,
            "state": state,
            "auth": _auth_diagnostics(options),
            "version": APP_VERSION,
            "repo_versions": {
                "stable": _display_repo_version(STABLE_REPO_VERSION, "n/a"),
                "dev": _display_repo_version(DEV_REPO_VERSION, APP_VERSION),
                "current": APP_VERSION,
            },
            "token_health": _token_health(options),
            "cancel_sync": _is_cancel_requested(),
            "log_tail": _sanitized_log_tail(),
                "scheduler": _scheduler.next_run_info,
        }
    )


@app.get("/api/ignore/recommendations")
def get_ignore_recommendations():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    gitignore_path = CONFIG_ROOT / ".gitignore"
    current = set()
    local_exists = gitignore_path.exists()
    if local_exists:
        for line in gitignore_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                current.add(stripped)
    return jsonify(
        {
            "ok": True,
            "local_gitignore": local_exists,
            "patterns": [{"pattern": pattern, "selected": (pattern in current) or not local_exists} for pattern in IGNORE_PATTERNS],
        }
    )


@app.post("/api/ignore/recommendations")
def save_ignore_recommendations():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400
    patterns = payload.get("patterns", [])
    if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
        return jsonify({"ok": False, "error": "patterns must be a list of strings"}), 400
    gitignore_path = CONFIG_ROOT / ".gitignore"
    existing = []
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8").splitlines()
    merged = list(existing)
    for pattern in patterns:
        if pattern not in merged:
            merged.append(pattern)
    gitignore_path.parent.mkdir(parents=True, exist_ok=True)
    gitignore_path.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
    _append_log("Updated local .gitignore from recommended patterns")
    return jsonify({"ok": True, "count": len(patterns)})


@app.post("/api/ignore/recommendations/reset")
def reset_ignore_recommendations():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    gitignore_path = CONFIG_ROOT / ".gitignore"
    if gitignore_path.exists():
        gitignore_path.unlink()
        _append_log("Reset local .gitignore to defaults")
    return jsonify({"ok": True, "message": "Reset to defaults"})


@app.get("/api/diagnostics")
def get_diagnostics():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    return jsonify(_diagnostics_bundle())


@app.get("/api/changelog")
def get_changelog():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    return jsonify({"ok": True, "entries": _read_changelog_entries(5)})


@app.get("/api/auth/device")
def get_device_auth_status():
    flow = _load_device_flow()
    if not flow:
        return jsonify({"ok": True, "active": False})
    return jsonify(
        {
            "ok": True,
            "active": True,
            "user_code": flow.get("user_code"),
            "verification_uri": flow.get("verification_uri"),
            "verification_uri_complete": _build_verification_url(flow),
            "expires_at": flow.get("expires_at"),
        }
    )


@app.post("/api/auth/device/start")
def start_device_auth():
    payload = request.get_json(silent=True)
    if payload is not None and not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400

    options = _merge_options()
    client_id = str(
        (payload or {}).get("client_id")
        or options.get("github_client_id")
        or DEFAULT_OAUTH_CLIENT_ID
    ).strip()
    if not client_id:
        return jsonify({"ok": False, "error": "github_client_id is required"}), 400

    client = GitHubClient(
        repository=str(options.get("github_repository", "")).strip(),
        branch=str(options.get("github_branch", "main")).strip() or "main",
        token="",
    )
    try:
        device_flow = client.start_device_flow(client_id)
    except SyncError as err:
        _append_log(f"Device flow start failed: {err}")
        return jsonify({"ok": False, "error": str(err)}), 502

    expires_in = int(device_flow.get("expires_in", 900))
    flow_state = {
        "client_id": client_id,
        "device_code": str(device_flow.get("device_code", "")).strip(),
        "user_code": str(device_flow.get("user_code", "")).strip(),
        "verification_uri": str(
            device_flow.get("verification_uri", "https://github.com/login/device")
        ).strip(),
        "verification_uri_complete": str(device_flow.get("verification_uri_complete", "")).strip(),
        "interval": int(device_flow.get("interval", 5)),
        "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=expires_in)).isoformat(),
    }

    if not flow_state["device_code"] or not flow_state["user_code"]:
        return jsonify({"ok": False, "error": "GitHub device flow returned incomplete response"}), 502

    _save_device_flow(flow_state)
    _append_log("Device flow started from web UI")
    return jsonify(
        {
            "ok": True,
            "user_code": flow_state["user_code"],
            "verification_uri": flow_state["verification_uri"],
            "verification_uri_complete": _build_verification_url(flow_state),
            "expires_at": flow_state["expires_at"],
        }
    )


@app.post("/api/auth/device/complete")
def complete_device_auth():
    flow = _load_device_flow()
    if not flow:
        return jsonify({"ok": False, "error": "No active device flow. Start authorization first."}), 400

    options = _merge_options()
    client = GitHubClient(
        repository=str(options.get("github_repository", "")).strip(),
        branch=str(options.get("github_branch", "main")).strip() or "main",
        token="",
    )
    try:
        token = client.exchange_device_code(
            client_id=str(flow.get("client_id", "")),
            device_code=str(flow.get("device_code", "")),
            interval=int(flow.get("interval", 5)),
            timeout=120,
        )
    except SyncError as err:
        _append_log(f"Device flow completion failed: {err}")
        return jsonify({"ok": False, "error": str(err)}), 502

    merged = _merge_options()
    merged["github_token"] = token
    merged["github_client_id"] = str(flow.get("client_id", "")).strip() or DEFAULT_OAUTH_CLIENT_ID
    _persist_options(merged)
    _clear_device_flow()
    _append_log("GitHub token obtained via device flow")
    return jsonify({"ok": True, "options": _mask_token(_merge_options())})


@app.get("/api/repos")
def list_repos():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    options = _merge_options()
    query = request.args.get("q", "", type=str)
    try:
        repos = _repo_picker_entries(options, query=query, include_unmanaged=True)
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    return jsonify({"ok": True, "repos": repos})


@app.get("/api/repos/managed")
def list_managed_repos():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    options = _merge_options()
    query = request.args.get("q", "", type=str)
    try:
        repos = _repo_picker_entries(options, query=query, include_unmanaged=False)
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 400
    _save_managed_repos(repos)
    return jsonify({"ok": True, "repos": repos})


@app.get("/api/repos/cached")
def list_cached_managed_repos():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    return jsonify({"ok": True, "repos": _load_managed_repos()})


@app.post("/api/repos/adopt")
def adopt_repo():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True)
    if payload is not None and not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400

    options = _merge_options()
    repository = str((payload or {}).get("repository") or options.get("github_repository", "")).strip()
    if not repository:
        return jsonify({"ok": False, "error": "repository is required"}), 400
    if repository.count("/") != 1:
        return jsonify({"ok": False, "error": "repository must be in owner/repo format"}), 400

    private_value = (payload or {}).get("private", True)
    if not isinstance(private_value, bool):
        return jsonify({"ok": False, "error": "private must be true or false"}), 400

    try:
        _token_client(options)
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    try:
        engine = SyncEngine(_repo_sync_config(options, repository), previous_hash_index={})
        engine._github.write_repo_marker(  # pylint: disable=protected-access
            {"created_by": "github-config-sync-addon", "repository": repository}
        )
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 502

    _save_managed_repos(
        [
            *[
                item
                for item in _load_managed_repos()
                if str(item.get("full_name", "")).strip() != repository
            ],
            {
                "name": repository.rsplit("/", 1)[-1],
                "full_name": repository,
                "private": private_value,
                "managed": True,
            },
        ]
    )

    merged = _merge_options()
    merged["repo_mode"] = "existing"
    merged["github_repository"] = repository
    merged["existing_repo_confirmed_for"] = repository
    _save_json(WEBUI_OPTIONS_PATH, merged)
    _append_log(f"Adopted existing repository {repository} with add-on marker")
    return jsonify({"ok": True, "repository": repository, "options": _mask_token(_merge_options())})


@app.post("/api/repos/create")
def create_repo():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400

    name = str(payload.get("name", "")).strip()
    if not name:
        name = DEFAULT_NEW_REPO_NAME

    private_value = payload.get("private", True)
    if not isinstance(private_value, bool):
        return jsonify({"ok": False, "error": "private must be true or false"}), 400
    private = private_value
    description = str(payload.get("description", "")).strip()

    options = _merge_options()
    try:
        client = _token_client(options)
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 400
    try:
        repo = client.create_repository(name=name, private=private, description=description)
        engine = SyncEngine(
            SyncConfig(
                repository=str(repo.get("full_name", "")).strip(),
                branch=str(options.get("github_branch", "main")).strip() or "main",
                token=str(options.get("github_token", "")).strip(),
                config_root=str(CONFIG_ROOT),
                dry_run=True,
                addon_config_root="/addon_configs" if bool(options.get("include_addon_configs", False)) else "",
                include_media=bool(options.get("include_media", False)),
                include_share=bool(options.get("include_share", False)),
                include_ssl=bool(options.get("include_ssl", False)),
                include_backups=bool(options.get("include_backups", False)),
                include_www=bool(options.get("include_www", False)),
                include_addon_configs=bool(options.get("include_addon_configs", False)),
                sync_mode=str(options.get("sync_mode", "whitelist")),
            ),
            previous_hash_index={},
        )
        _restore_repo_skeleton_and_marker(engine, str(repo.get("full_name", "")).strip())
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 502

    merged = _merge_options()
    merged["repo_mode"] = "create"
    merged["github_repository"] = str(repo.get("full_name", "")).strip()
    merged["existing_repo_confirmed_for"] = merged["github_repository"]
    _save_managed_repos(
        [
            *[
                item
                for item in _load_managed_repos()
                if str(item.get("full_name", "")).strip() != merged["github_repository"]
            ],
            {
                "name": str(repo.get("name", "")).strip(),
                "full_name": merged["github_repository"],
                "private": bool(repo.get("private", True)),
                "managed": True,
            },
        ]
    )
    _save_json(WEBUI_OPTIONS_PATH, merged)
    _append_log(f"Created repository {merged['github_repository']} from web UI")
    return jsonify(
        {
            "ok": True,
            "repository": merged["github_repository"],
            "options": _mask_token(_merge_options()),
        }
    )


@app.post("/api/sync")
def trigger_sync():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    options = _merge_options()
    sync_config = _sync_config(options)

    if not sync_config.repository:
        state = _save_state(
            {
                "status": "error",
                "last_error": "github_repository is required",
                "last_run": dt.datetime.now(dt.timezone.utc).isoformat(),
                **_clear_sync_progress_state(),
            }
        )
        return jsonify({"ok": False, "error": "github_repository is required", "state": state}), 400

    if not sync_config.dry_run:
        confirmation_error = _existing_repo_confirmation_error(options)
        if confirmation_error:
            return jsonify({"ok": False, "error": confirmation_error}), 400

    started = dt.datetime.now(dt.timezone.utc).isoformat()
    _save_state(
        {
            "status": "running",
            "last_run": started,
            "last_error": None,
            "last_result": None,
            "last_scan": None,
            **_clear_sync_progress_state(),
        }
    )
    _set_cancel_requested(False)
    _append_log(f"Sync started for {sync_config.repository} (dry_run={sync_config.dry_run})")
    sensitive_files: list[str] = []
    try:
        engine = SyncEngine(sync_config, previous_hash_index=_load_json(HASH_INDEX_PATH, {}))
        engine.set_cancel_checker(_is_cancel_requested)
        engine.set_progress_callback(lambda payload: _save_state(_sync_progress_payload(payload)))
        plan, current_hash_index = engine.plan()
        scan = _plan_summary(plan)
        _append_log(
            "Scan summary: "
            f"+{scan['added_count']} "
            f"~{scan['changed_count']} "
            f"-{scan['removed_count']} "
            f"files={scan['total_files']}"
        )
        if not sync_config.dry_run:
            probe_ok, probe_message = engine._github.probe_repository()  # pylint: disable=protected-access
            if not probe_ok:
                friendly_message = probe_message
                if "HTTP 401" in probe_message or "HTTP 403" in probe_message:
                    friendly_message = (
                        "GitHub rejected the repository probe. "
                        "Check that the token is valid and has repo access."
                    )
                elif "HTTP 404" in probe_message:
                    friendly_message = (
                        "GitHub could not find the repository. "
                        "Check the repository name, visibility, and token access."
                    )
                state = _save_state(
                    {
                        "status": "error",
                        "last_error": friendly_message,
                        "last_result": None,
                        "last_scan": scan,
                        **_clear_sync_progress_state(),
                    }
                )
                _append_log(f"Repository probe failed: {friendly_message}")
                return jsonify({"ok": False, "error": friendly_message, "state": state}), 502
        result = engine.run(plan)
        if not sync_config.dry_run:
            _ensure_repo_marker(engine, sync_config.repository)
            sensitive_files = _sync_sensitive_warning(engine)
    except SyncError as err:
        state = _save_state(
            {
                "status": "error",
                "last_error": str(err),
                "last_result": None,
                "last_scan": scan,
                **_clear_sync_progress_state(),
            }
        )
        _append_log(f"Sync failed: {err}")
        return jsonify({"ok": False, "error": str(err), "state": state}), 502

    _save_json(HASH_INDEX_PATH, current_hash_index)

    state = _save_state(
        {
            "status": "ok",
            "last_success": dt.datetime.now(dt.timezone.utc).isoformat(),
            "last_result": result.message,
            "last_scan": scan,
            "last_error": None,
            **_clear_sync_progress_state(),
        }
    )
    _append_log(result.message)
    return jsonify(
        {
            "ok": True,
            "result": result.message,
            "summary": {
                "synced_count": result.synced_count,
                "deleted_count": result.deleted_count,
                "skipped_count": result.skipped_count,
                "total_files": result.total_files,
            },
            "warnings": sensitive_files,
            "state": state,
        }
    )


@app.post("/api/sync/cancel")
def cancel_sync():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    _set_cancel_requested(True)
    _append_log("Cancel requested for current sync/upload")
    return jsonify({"ok": True, "cancel_sync": True})


@app.post("/api/sync/clean")
def trigger_clean_sync():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    options = _merge_options()
    sync_config = _sync_config(options)
    if not sync_config.repository:
        return jsonify({"ok": False, "error": "github_repository is required"}), 400
    confirmation_error = _existing_repo_confirmation_error(options)
    if confirmation_error:
        return jsonify({"ok": False, "error": confirmation_error}), 400
    sync_config = SyncConfig(
        repository=sync_config.repository,
        branch=sync_config.branch,
        token=sync_config.token,
        config_root=sync_config.config_root,
        addon_config_root=sync_config.addon_config_root,
        dry_run=False,
        include_media=sync_config.include_media,
        include_share=sync_config.include_share,
        include_ssl=sync_config.include_ssl,
        include_backups=sync_config.include_backups,
        include_www=sync_config.include_www,
        include_addon_configs=sync_config.include_addon_configs,
        sync_mode=sync_config.sync_mode,
    )
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    _save_state({"status": "running", "last_run": started, "last_error": None, **_clear_sync_progress_state()})
    _set_cancel_requested(False)
    _append_log(f"Clean upload started for {sync_config.repository} (forced live upload)")
    scan: dict[str, Any] | None = None
    sensitive_files: list[str] = []
    try:
        previous_index = _load_json(HASH_INDEX_PATH, {})
        engine = SyncEngine(sync_config, previous_hash_index=previous_index)
        safe, reason = _repo_safety_state(engine)
        if not safe:
            state = _save_state(
                {
                    "status": "error",
                    "last_error": reason,
                    "last_result": None,
                    "last_scan": None,
                    **_clear_sync_progress_state(),
                }
            )
            _append_log(f"Clean upload blocked: {reason}")
            return jsonify({"ok": False, "error": reason, "state": state}), 400
        engine.set_cancel_checker(_is_cancel_requested)
        engine.set_progress_callback(lambda payload: _save_state(_sync_progress_payload(payload)))
        engine.clean_remote_tree()
        plan, current_hash_index = engine.clean_plan()
        scan = _plan_summary(plan)
        _append_log(
            "Clean upload summary: "
            f"+{scan['added_count']} "
            f"~{scan['changed_count']} "
            f"-{scan['removed_count']} "
            f"files={scan['total_files']}"
        )
        if not sync_config.dry_run:
            probe_ok, probe_message = engine._github.probe_repository()  # pylint: disable=protected-access
            if not probe_ok:
                friendly_message = probe_message
                if "HTTP 401" in probe_message or "HTTP 403" in probe_message:
                    friendly_message = (
                        "GitHub rejected the repository probe. "
                        "Check that the token is valid and has repo access."
                    )
                elif "HTTP 404" in probe_message:
                    friendly_message = (
                        "GitHub could not find the repository. "
                        "Check the repository name, visibility, and token access."
                    )
                state = _save_state(
                    {
                        "status": "error",
                        "last_error": friendly_message,
                        "last_result": None,
                        "last_scan": scan,
                        **_clear_sync_progress_state(),
                    }
                )
                _append_log(f"Repository probe failed: {friendly_message}")
                return jsonify({"ok": False, "error": friendly_message, "state": state}), 502
        result = engine.run(plan)
        _restore_repo_skeleton_and_marker(engine, sync_config.repository)
        sensitive_files = _sync_sensitive_warning(engine)
        _save_json(HASH_INDEX_PATH, current_hash_index)
    except SyncError as err:
        state = _save_state(
            {
                "status": "error",
                "last_error": str(err),
                "last_result": None,
                "last_scan": scan,
                **_clear_sync_progress_state(),
            }
        )
        return jsonify({"ok": False, "error": str(err), "state": state}), 502

    state = _save_state(
        {
            "status": "ok",
            "last_success": dt.datetime.now(dt.timezone.utc).isoformat(),
            "last_result": result.message,
            "last_scan": scan,
            "last_error": None,
            **_clear_sync_progress_state(),
        }
    )
    return jsonify(
        {
            "ok": True,
            "result": result.message,
            "summary": {
                "synced_count": result.synced_count,
                "deleted_count": result.deleted_count,
                "skipped_count": result.skipped_count,
                "total_files": result.total_files,
            },
            "warnings": sensitive_files,
            "state": state,
        }
    )


@app.post("/api/sync/clean-repo")
def trigger_clean_repo():
    if not _require_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    options = _merge_options()
    sync_config = _sync_config(options)

    if not sync_config.repository:
        return jsonify({"ok": False, "error": "github_repository is required"}), 400

    started = dt.datetime.now(dt.timezone.utc).isoformat()
    _save_state({"status": "running", "last_run": started, "last_error": None, **_clear_sync_progress_state()})
    _set_cancel_requested(False)
    _append_log(f"Clean repo requested for {sync_config.repository}")

    try:
        engine = SyncEngine(sync_config, previous_hash_index=_load_json(HASH_INDEX_PATH, {}))
        engine.set_progress_callback(lambda payload: _save_state(_sync_progress_payload(payload)))
        engine.set_cancel_checker(_is_cancel_requested)
        engine.clean_remote_tree()
        if _is_cancel_requested():
            raise SyncError("Clean cancelled")
        _restore_repo_skeleton_and_marker(engine, sync_config.repository)
    except SyncError as err:
        state = _save_state(
            {
                "status": "error",
                "last_error": str(err),
                "last_result": None,
                "last_scan": None,
                **_clear_sync_progress_state(),
            }
        )
        _append_log(f"Clean repo failed: {err}")
        return jsonify({"ok": False, "error": str(err), "state": state}), 502

    state = _save_state(
        {
            "status": "ok",
            "last_success": dt.datetime.now(dt.timezone.utc).isoformat(),
            "last_result": "Clean repo completed. Remote repo fully reset and skeleton restored.",
            "last_scan": None,
            "last_error": None,
            **_clear_sync_progress_state(),
        }
    )
    _append_log("Clean repo completed: remote tree wiped, skeleton restored, marker refreshed")
    return jsonify(
        {
            "ok": True,
            "result": "Clean repo completed. Remote repo fully reset and skeleton restored.",
            "state": state,
        }
    )


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
