from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from flask import Flask, jsonify, request, send_from_directory

from sync import SyncConfig, SyncEngine
from sync.errors import SyncError
from sync.github_client import GitHubClient

APP_VERSION = "0.1.6"
APP_PORT = 8099
DEFAULT_OAUTH_CLIENT_ID = "Ov23li2ycCraodta6WCU"

DATA_DIR = Path("/data")
SUPERVISOR_OPTIONS_PATH = DATA_DIR / "options.json"
WEBUI_OPTIONS_PATH = DATA_DIR / "webui_options.json"
STATE_PATH = DATA_DIR / "state.json"
LOG_PATH = DATA_DIR / "sync.log"
HASH_INDEX_PATH = DATA_DIR / "hash_index.json"
DEVICE_FLOW_PATH = DATA_DIR / "device_flow.json"
STATIC_DIR = Path("/app/static")
CONFIG_ROOT = Path("/config")

DEFAULT_OPTIONS: dict[str, Any] = {
    "github_repository": "",
    "github_branch": "main",
    "github_token": "",
    "github_client_id": DEFAULT_OAUTH_CLIENT_ID,
    "sync_interval_minutes": 60,
    "dry_run": True,
}

DEFAULT_STATE: dict[str, Any] = {
    "status": "idle",
    "last_run": None,
    "last_success": None,
    "last_error": None,
    "last_result": None,
    "last_scan": None,
}


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


def _save_state(updates: dict[str, Any]) -> dict[str, Any]:
    state = _load_state()
    state.update(updates)
    _save_json(STATE_PATH, state)
    return state


def _append_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _validate_payload(payload: dict[str, Any]) -> tuple[bool, str | None]:
    repository = str(payload.get("github_repository", "")).strip()
    if repository and repository.count("/") != 1:
        return False, "github_repository must be in owner/repo format"

    branch = str(payload.get("github_branch", "")).strip()
    if not branch:
        return False, "github_branch is required"

    interval_raw = payload.get("sync_interval_minutes")
    try:
        interval = int(interval_raw)
    except (TypeError, ValueError):
        return False, "sync_interval_minutes must be an integer"
    if interval < 5 or interval > 1440:
        return False, "sync_interval_minutes must be between 5 and 1440"

    if not isinstance(payload.get("dry_run"), bool):
        return False, "dry_run must be true or false"

    return True, None


def _mask_token(options: dict[str, Any]) -> dict[str, Any]:
    output = dict(options)
    token = output.get("github_token") or ""
    if token:
        output["github_token"] = "********"
    return output


def _sync_config(options: dict[str, Any]) -> SyncConfig:
    return SyncConfig(
        repository=str(options.get("github_repository", "")).strip(),
        branch=str(options.get("github_branch", "main")).strip() or "main",
        token=str(options.get("github_token", "")).strip(),
        config_root=str(CONFIG_ROOT),
        dry_run=bool(options.get("dry_run", True)),
    )


def _token_client(options: dict[str, Any]) -> GitHubClient:
    token = str(options.get("github_token", "")).strip()
    if not token:
        raise SyncError("Authenticate with Device Flow first to access repositories")
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
    return {
        "added_count": len(plan.added),
        "changed_count": len(plan.changed),
        "removed_count": len(plan.removed),
        "total_files": plan.total_files,
        "added_files": plan.added[:50],
        "changed_files": plan.changed[:50],
        "removed_files": plan.removed[:50],
    }


app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "version": APP_VERSION})


@app.get("/api/options")
def get_options():
    return jsonify(_mask_token(_merge_options()))


@app.post("/api/options")
def set_options():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400

    candidate = {
        "github_repository": str(payload.get("github_repository", "")).strip(),
        "github_branch": str(payload.get("github_branch", "main")).strip() or "main",
        "github_token": str(payload.get("github_token", "")).strip(),
        "github_client_id": str(
            payload.get("github_client_id", _merge_options().get("github_client_id", DEFAULT_OAUTH_CLIENT_ID))
        ).strip()
        or DEFAULT_OAUTH_CLIENT_ID,
        "sync_interval_minutes": payload.get("sync_interval_minutes", 60),
        "dry_run": payload.get("dry_run", True),
    }

    valid, message = _validate_payload(candidate)
    if not valid:
        return jsonify({"ok": False, "error": message}), 400

    candidate["sync_interval_minutes"] = int(candidate["sync_interval_minutes"])
    _save_json(WEBUI_OPTIONS_PATH, candidate)
    _append_log("Settings updated via web UI")
    return jsonify({"ok": True, "options": _mask_token(_merge_options())})


@app.get("/api/status")
def get_status():
    state = _load_state()
    logs = ""
    if LOG_PATH.exists():
        logs = LOG_PATH.read_text(encoding="utf-8")[-4000:]
    return jsonify({"ok": True, "state": state, "log_tail": logs})


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
    _save_json(WEBUI_OPTIONS_PATH, merged)
    _clear_device_flow()
    _append_log("GitHub token obtained via device flow")
    return jsonify({"ok": True, "options": _mask_token(_merge_options())})


@app.get("/api/repos")
def list_repos():
    options = _merge_options()
    query = request.args.get("q", "", type=str)
    try:
        client = _token_client(options)
        repos = client.list_user_repositories(query=query, limit=100)
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    return jsonify(
        {
            "ok": True,
            "repos": [
                {
                    "name": str(repo.get("name", "")),
                    "full_name": str(repo.get("full_name", "")),
                    "private": bool(repo.get("private", False)),
                }
                for repo in repos
            ],
        }
    )


@app.post("/api/repos/create")
def create_repo():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400

    name = str(payload.get("name", "")).strip()
    if not name:
        return jsonify({"ok": False, "error": "Repository name is required"}), 400

    private = bool(payload.get("private", True))
    description = str(payload.get("description", "")).strip()

    options = _merge_options()
    try:
        client = _token_client(options)
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 400
    try:
        repo = client.create_repository(name=name, private=private, description=description)
    except SyncError as err:
        return jsonify({"ok": False, "error": str(err)}), 502

    merged = _merge_options()
    merged["github_repository"] = str(repo.get("full_name", "")).strip()
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
    options = _merge_options()
    sync_config = _sync_config(options)

    if not sync_config.repository:
        state = _save_state(
            {
                "status": "error",
                "last_error": "github_repository is required",
                "last_run": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        return jsonify({"ok": False, "error": "github_repository is required", "state": state}), 400

    previous_index = _load_json(HASH_INDEX_PATH, {})
    engine = SyncEngine(sync_config, previous_hash_index=previous_index)

    started = dt.datetime.now(dt.timezone.utc).isoformat()
    _save_state({"status": "running", "last_run": started, "last_error": None})
    _append_log(f"Sync started for {sync_config.repository} (dry_run={sync_config.dry_run})")

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
            state = _save_state(
                {
                    "status": "error",
                    "last_error": probe_message,
                    "last_result": None,
                    "last_scan": scan,
                }
            )
            _append_log(f"Repository probe failed: {probe_message}")
            return jsonify({"ok": False, "error": probe_message, "state": state}), 502

    try:
        result = engine.run(plan)
    except SyncError as err:
        state = _save_state(
            {
                "status": "error",
                "last_error": str(err),
                "last_result": None,
                "last_scan": scan,
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
            "state": state,
        }
    )


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
