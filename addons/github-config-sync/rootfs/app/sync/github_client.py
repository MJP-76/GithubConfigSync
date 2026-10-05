from __future__ import annotations

import base64
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import SyncError

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
OAUTH_BASE = "https://github.com"
ADDON_REPO_MARKER_PATH = ".github-config-sync-addon.json"
# Written to the repository root once a flat -> structured migration has run.
# It lives in the repository rather than in local state on purpose: it survives
# a reinstall, it is visible in the repo, and it travels with a cloned copy.
MIGRATED_MARKER_PATH = ".github-config-sync-migrated.json"


@dataclass
class _RateGate:
    """Backoff state for one client, shared by that client's worker threads.

    This used to be module-global, so one client's rate limit stalled every other
    client in the process. That was not hypothetical. The add-on's own update
    check runs unauthenticated, and unauthenticated requests draw on GitHub's
    60/hour per-IP budget rather than the authenticated one. When that budget
    was spent, the half-hour backoff that check opened held up every fully
    authenticated sync behind it - a sync would report itself running while
    waiting on a limit it had not hit and had no way to clear.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    until: float = 0.0
    reason: str = ""
    remaining: int | None = None
    reset_at: float | None = None
    cancel_check: Callable[[], bool] | None = None
    progress: Callable[[dict[str, object]], None] | None = None

    def register_hooks(
        self,
        cancel_check: Callable[[], bool] | None = None,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        """Wire the watchdog's cancel and progress signals (clear with None)."""
        self.cancel_check = cancel_check
        self.progress = progress

    def reset(self) -> None:
        """Clear gate state. A sync clears this when it finishes."""
        with self.lock:
            self.until = 0.0
            self.reason = ""
            self.remaining = None
            self.reset_at = None

    def wait(self) -> float:
        with self.lock:
            return max(0.0, self.until - time.time())

    def open(self, wait_seconds: float, reason: str = "") -> None:
        until = time.time() + wait_seconds
        with self.lock:
            self.until = max(self.until, until)
            self.reason = reason
        if self.progress is not None:
            self.progress(
                {
                    "action": "waiting",
                    "wait_seconds": wait_seconds,
                    "reason": reason,
                    "until": until,
                }
            )

    def note_headers(self, headers: Any) -> None:
        if headers is None:
            return
        remaining_raw = headers.get("X-RateLimit-Remaining")
        reset_raw = headers.get("X-RateLimit-Reset")
        if remaining_raw is None and reset_raw is None:
            return
        try:
            remaining = int(remaining_raw) if remaining_raw is not None else None
            reset_at = float(reset_raw) if reset_raw is not None else None
        except (ValueError, TypeError):
            return
        with self.lock:
            if remaining is not None:
                self.remaining = remaining
            if reset_at is not None:
                self.reset_at = reset_at

    def sleep(self, seconds: float) -> None:
        """Sleep for ``seconds``, bailing early with a SyncError on cancellation."""
        if seconds <= 0:
            return
        if self.cancel_check is None:
            time.sleep(seconds)
            return
        deadline = time.time() + seconds
        while True:
            if self.cancel_check():
                raise SyncError("Sync cancelled during GitHub rate-limit wait")
            now = time.time()
            if now >= deadline:
                return
            time.sleep(min(0.25, deadline - now))

    def wait_out(self) -> None:
        """Hold this thread until this client's gate clears, staggered on release.

        Waiters used to sleep the whole remaining wait and then all fire at once.
        """
        announced = False
        rounds = 0
        stagger = _thread_stagger()
        while rounds < _GATE_MAX_ROUNDS:
            wait = self.wait()
            if wait <= 0:
                break
            rounds += 1
            if not announced:
                _LOGGER.warning("GitHub rate limit still active, waiting %.0fs", wait)
                announced = True
            self.sleep(wait)
        if rounds:
            self.sleep(stagger)

    def wait_for_budget(self) -> None:
        """Pause before sending when the core budget is nearly exhausted."""
        with self.lock:
            remaining = self.remaining
            reset_at = self.reset_at
        if (
            remaining is None
            or reset_at is None
            or remaining > _PREEMPTIVE_REMAINING_MIN
        ):
            return
        wait = reset_at - time.time()
        if wait <= 0:
            return
        _LOGGER.warning(
            "GitHub core rate limit nearly exhausted (remaining=%d), pausing %.0fs until reset",
            remaining,
            wait,
        )
        self.sleep(min(wait, _MAX_RATE_LIMIT_WAIT))


@dataclass(frozen=True)
class GitHubClient:
    repository: str
    branch: str
    token: str
    # Auxiliary clients ask for isolation. They run unauthenticated, so they
    # share GitHub's much smaller 60/hour per-IP budget, and a long backoff
    # opened for one of them used to hold up every authenticated sync in the
    # process. An isolated client gives up on a rate limit instead of sleeping
    # through it, which is all its callers could act on anyway - they catch the
    # error, report it and carry on.
    isolate_rate_limits: bool = False
    gate: _RateGate = field(default_factory=_RateGate, compare=False, repr=False)

    def register_rate_limit_hooks(
        self,
        cancel_check: Callable[[], bool] | None = None,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.gate.register_hooks(cancel_check=cancel_check, progress=progress)

    def reset_rate_gate(self) -> None:
        self.gate.reset()

    @property
    def _base(self) -> str:
        return f"{API_BASE}/repos/{self.repository}"

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "github-config-sync-addon",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def start_device_flow(self, client_id: str, scope: str = "repo") -> dict[str, Any]:
        return self._oauth_request(
            "POST",
            "/login/device/code",
            payload={"client_id": client_id, "scope": scope},
        )

    def exchange_device_code(
        self, client_id: str, device_code: str, interval: int = 5, timeout: int = 600
    ) -> str:
        deadline = time.monotonic() + timeout
        poll_interval = max(1, interval)
        slow_down_count = 0
        MAX_SLOW_DOWN = 10
        while True:
            payload = self._oauth_request(
                "POST",
                "/login/oauth/access_token",
                payload={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            token = payload.get("access_token")
            if isinstance(token, str) and token:
                return token

            error = payload.get("error")
            if error == "authorization_pending":
                if time.monotonic() >= deadline:
                    raise SyncError("Timed out waiting for GitHub device authorization")
                time.sleep(poll_interval)
                continue
            if error == "slow_down":
                slow_down_count += 1
                if slow_down_count > MAX_SLOW_DOWN:
                    raise SyncError("GitHub device flow returned too many slow_down responses")
                if time.monotonic() >= deadline:
                    raise SyncError("Timed out waiting for GitHub device authorization")
                poll_interval += 5
                time.sleep(poll_interval)
                continue
            description = payload.get("error_description", error or "Device authorization failed")
            raise SyncError(str(description))

    def list_user_repositories(self, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        payload = self._request_any("GET", f"{API_BASE}/user/repos?per_page={max(1, min(limit, 100))}&sort=updated")
        if not isinstance(payload, list):
            raise SyncError("GitHub repositories response was not a list")
        repos = [
            repo
            for repo in payload
            if isinstance(repo, dict) and isinstance(repo.get("full_name"), str)
        ]
        needle = query.strip().lower()
        if needle:
            repos = [
                repo
                for repo in repos
                if needle in str(repo.get("full_name", "")).lower()
                or needle in str(repo.get("name", "")).lower()
            ]
        return repos

    def create_repository(self, name: str, private: bool = True, description: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "private": private,
            "auto_init": True,
        }
        if description.strip():
            payload["description"] = description.strip()
        created = self._request_json("POST", f"{API_BASE}/user/repos", payload=payload)
        if not created.get("full_name"):
            raise SyncError("GitHub create repository returned incomplete payload")
        return created

    def write_repo_marker(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        marker_payload = payload or {"created_by": "github-config-sync-addon"}
        already_present = self.get_content(ADDON_REPO_MARKER_PATH)
        sha = already_present.get("sha") if already_present else None
        return self.put_content(
            path=ADDON_REPO_MARKER_PATH,
            content=json.dumps(marker_payload, indent=2, sort_keys=True).encode("utf-8"),
            message="sync: add repo marker",
            sha=sha,
        )

    def probe_repository(self) -> tuple[bool, str]:
        try:
            payload = self._request_json("GET", self._base)
            if payload.get("full_name"):
                return True, "Repository probe succeeded"
            return False, "Repository probe returned incomplete payload"
        except SyncError as err:
            message = str(err)
            if "HTTP 401" in message or "HTTP 403" in message:
                return False, "Repository probe failed with an auth error"
            if "HTTP 404" in message:
                return False, "Repository probe failed with a not-found error"
            return False, message

    def get_content(self, path: str) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(path, safe="")
        try:
            return self._request_json(
                "GET",
                f"{self._base}/contents/{encoded}?ref={urllib.parse.quote(self.branch, safe='')}",
            )
        except SyncError as err:
            if "HTTP 404" in str(err):
                return None
            raise

    def put_content(self, path: str, content: bytes, message: str, sha: str | None = None) -> dict[str, Any]:
        encoded = urllib.parse.quote(path, safe="")
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        url = f"{self._base}/contents/{encoded}"
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return self._request_json("PUT", url, payload=payload)
            except SyncError as err:
                if not _is_sha_conflict(err) or attempt == max_retries - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
                remote = self.get_content(path)
                refreshed_sha = remote.get("sha") if remote else None
                if refreshed_sha:
                    payload["sha"] = refreshed_sha
                else:
                    payload.pop("sha", None)
        raise SyncError(f"SHA conflict persisted after {max_retries} attempts for {path}")

    def delete_content(self, path: str, sha: str, message: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(path, safe="")
        payload = {"message": message, "sha": sha, "branch": self.branch}
        url = f"{self._base}/contents/{encoded}"
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return self._request_json("DELETE", url, payload=payload)
            except SyncError as err:
                if not _is_sha_conflict(err) or attempt == max_retries - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
                remote = self.get_content(path)
                refreshed_sha = remote.get("sha") if remote else None
                if not refreshed_sha:
                    raise
                payload["sha"] = refreshed_sha
        raise SyncError(f"SHA conflict persisted after {max_retries} attempts for {path}")

    def get_branch_head_sha(self) -> str:
        payload = self._request_json("GET", f"{self._base}/git/ref/heads/{urllib.parse.quote(self.branch, safe='')}")
        object_payload = payload.get("object")
        if not isinstance(object_payload, dict) or not isinstance(object_payload.get("sha"), str):
            raise SyncError("GitHub ref response was incomplete")
        return object_payload["sha"]

    def get_commit_tree_sha(self, commit_sha: str) -> str:
        payload = self._request_json("GET", f"{self._base}/git/commits/{urllib.parse.quote(commit_sha, safe='')}")
        tree_payload = payload.get("tree")
        if not isinstance(tree_payload, dict) or not isinstance(tree_payload.get("sha"), str):
            raise SyncError("GitHub commit tree response was incomplete")
        return tree_payload["sha"]

    def create_blob(self, content: bytes) -> str:
        """Upload one file's content and return its blob SHA.

        Blob SHAs are content-addressed, so uploading the same bytes twice is
        free of consequence: the tree just references the existing object.
        That is what lets a whole run be staged and then committed at once.
        """
        payload = {
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        }
        response = self._request_json("POST", f"{self._base}/git/blobs", payload=payload)
        sha = response.get("sha")
        if not isinstance(sha, str) or not sha:
            raise SyncError("GitHub blob response was incomplete")
        return sha

    def create_git_tree(self, base_tree: str | None = None, tree: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if base_tree:
            payload["base_tree"] = base_tree
        if tree is not None:
            payload["tree"] = tree
        return self._request_json("POST", f"{self._base}/git/trees", payload=payload)

    def create_git_commit(self, message: str, tree_sha: str, parent_sha: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": message, "tree": tree_sha}
        if parent_sha:
            payload["parents"] = [parent_sha]
        return self._request_json("POST", f"{self._base}/git/commits", payload=payload)

    def update_branch_ref(self, commit_sha: str, force: bool = True) -> dict[str, Any]:
        """Point the branch at a commit.

        force=False makes a concurrent push fail rather than be discarded, so
        the caller can rebuild on the new head. The reset path genuinely means
        to overwrite history and keeps force=True.
        """
        payload = {"sha": commit_sha, "force": force}
        return self._request_json(
            "PATCH",
            f"{self._base}/git/refs/heads/{urllib.parse.quote(self.branch, safe='')}",
            payload=payload,
        )

    def list_directory_contents(self, path: str = "") -> list[dict[str, Any]]:
        suffix = ""
        if path:
            encoded = urllib.parse.quote(path, safe="")
            suffix = f"/contents/{encoded}"
        else:
            suffix = "/contents"
        try:
            payload = self._request_any("GET", f"{self._base}{suffix}")
        except SyncError as err:
            if "HTTP 404" in str(err):
                return []
            raise
        if payload is None:
            return []
        if not isinstance(payload, list):
            raise SyncError("GitHub directory listing response was not a list")
        return [item for item in payload if isinstance(item, dict)]

    def list_all_paths(self) -> list[str]:
        """Every path in the repository's current tree, in one request.

        Migrations need the remote tree rather than the scan baseline: a
        baseline only ever records what a previous sync saw, and a run that
        scanned nothing records nothing at all - which is exactly how the
        root-level leftovers became unreachable by every other operation.
        """
        sha = self.get_branch_head_sha()
        payload = self._request_json("GET", f"{self._base}/git/trees/{sha}?recursive=1")
        tree = payload.get("tree") if isinstance(payload, dict) else None
        if not isinstance(tree, list):
            raise SyncError("GitHub tree response was incomplete")
        return [
            str(item.get("path"))
            for item in tree
            if isinstance(item, dict) and item.get("path") and item.get("type") == "blob"
        ]

    def write_migrated_marker(self) -> dict[str, Any]:
        """Record that the migration has run, unless it is already recorded.

        Written only after the commit landed, so a run that failed partway
        leaves the tick box usable and the user can simply try again.
        """
        if self.get_content(MIGRATED_MARKER_PATH):
            return {"path": MIGRATED_MARKER_PATH}
        payload = {"migrated_from": "flat", "layout": "prefixed"}
        return self.put_content(
            path=MIGRATED_MARKER_PATH,
            content=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            message="chore: record that the layout migration has run",
        )

    def create_release(self, tag_name: str, name: str, body: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tag_name": tag_name,
            "name": name,
            "body": body,
            "draft": False,
            "prerelease": False,
        }
        return self._request_json("POST", f"{self._base}/releases", payload=payload)

    def list_releases(self, per_page: int = 50) -> list[dict[str, Any]]:
        payload = self._request_any("GET", f"{self._base}/releases?per_page={max(1, min(per_page, 100))}")
        if not isinstance(payload, list):
            return []
        return [r for r in payload if isinstance(r, dict)]

    def delete_release(self, release_id: int) -> None:
        self._request_any("DELETE", f"{self._base}/releases/{release_id}")

    def list_all_releases(self, per_page: int = 100) -> list[dict[str, Any]]:
        releases: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._request_any(
                "GET", f"{self._base}/releases?per_page={max(1, min(per_page, 100))}&page={page}"
            )
            if not isinstance(payload, list) or not payload:
                break
            releases.extend(r for r in payload if isinstance(r, dict))
            if len(payload) < per_page:
                break
            page += 1
        return releases

    def list_tags(self, per_page: int = 100) -> list[dict[str, Any]]:
        tags: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._request_any(
                "GET", f"{self._base}/git/refs/tags?per_page={max(1, min(per_page, 100))}&page={page}"
            )
            if not isinstance(payload, list) or not payload:
                break
            tags.extend(r for r in payload if isinstance(r, dict))
            if len(payload) < per_page:
                break
            page += 1
        return tags

    def delete_tag(self, tag_name: str) -> None:
        try:
            self._request_any("DELETE", f"{self._base}/git/refs/tags/{urllib.parse.quote(tag_name, safe='')}")
        except SyncError as err:
            if "HTTP 404" in str(err):
                return
            raise

    def _request_json(
        self, method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 60
    ) -> dict[str, Any]:
        decoded = self._request_any(method, url, payload=payload, timeout=timeout)
        if not isinstance(decoded, dict):
            raise SyncError(f"GitHub API returned non-object JSON for {method} {url}")
        return decoded

    def _request_any(self, method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> Any:
        transient_errors = 0
        rate_limit_errors = 0
        while True:
            self.gate.wait_out()
            self.gate.wait_for_budget()
            data = None
            headers = dict(self._headers)
            if payload is not None:
                data = json.dumps(payload).encode("utf-8")
                headers["Content-Type"] = "application/json"
            request = urllib.request.Request(url, method=method, data=data, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    self.gate.note_headers(response.headers)
                    body = response.read().decode("utf-8")
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as err:
                body = err.read().decode("utf-8", errors="ignore")
                wait = _rate_limit_wait_from(err, body)
                if wait is not None:
                    rate_limit_errors += 1
                    if self.isolate_rate_limits:
                        # Auxiliary work must never park a request thread for
                        # half an hour on a limit the core sync does not share.
                        _LOGGER.warning(
                            "GitHub rate limit HTTP %d on %s %s, not retrying this "
                            "auxiliary request: %s",
                            err.code,
                            method,
                            url,
                            _body_excerpt(body),
                        )
                        raise SyncError(
                            f"GitHub rate limit HTTP {err.code} for {method} {url}: "
                            f"{_body_excerpt(body)}"
                        ) from err
                    _LOGGER.warning(
                        "GitHub rate limit HTTP %d on %s %s, waiting %.0fs before retry "
                        "(attempt %d/%d): %s",
                        err.code,
                        method,
                        url,
                        wait,
                        rate_limit_errors,
                        _RATE_LIMIT_MAX_RETRIES,
                        _body_excerpt(body),
                    )
                    if rate_limit_errors > _RATE_LIMIT_MAX_RETRIES:
                        raise SyncError(
                            f"GitHub rate limit did not clear for {method} {url} after "
                            f"{rate_limit_errors} attempts. GitHub said: "
                            f"{_body_excerpt(body)}"
                        ) from err
                    self.gate.open(wait, reason=f"HTTP {err.code}")
                    continue
                if err.code in (500, 502, 503, 504):
                    transient_errors += 1
                    if transient_errors >= 5:
                        raise SyncError(f"GitHub API error HTTP {err.code} for {method} {url}: {body}") from err
                    wait = min(2 ** (transient_errors - 1), 8)
                    _LOGGER.warning(
                        "GitHub transient error HTTP %d (attempt %d/5), retrying in %ds",
                        err.code,
                        transient_errors,
                        wait,
                    )
                    self.gate.sleep(wait)
                    continue
                raise SyncError(f"GitHub API error HTTP {err.code} for {method} {url}: {body}") from err
            except urllib.error.URLError as err:
                raise SyncError(f"GitHub API request failed for {method} {url}: {err.reason}") from err

    def _oauth_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "User-Agent": "github-config-sync-addon",
            "Accept": "application/json",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{OAUTH_BASE}{path}",
            method=method,
            data=data,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
                if not body:
                    return {}
                decoded = json.loads(body)
                if not isinstance(decoded, dict):
                    raise SyncError(f"GitHub OAuth returned non-object JSON for {method} {path}")
                return decoded
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="ignore")
            raise SyncError(f"GitHub OAuth error HTTP {err.code} for {method} {path}: {body}") from err
        except urllib.error.URLError as err:
            raise SyncError(f"GitHub OAuth request failed for {method} {path}: {err.reason}") from err


def _is_sha_conflict(err: SyncError) -> bool:
    message = str(err)
    if "HTTP 409" in message or '"status":"409"' in message or '"status": "409"' in message:
        return True
    if '"status":"422"' in message or '"status": "422"' in message:
        lowered = message.lower()
        return "sha" in lowered and "supplied" in lowered
    return False


def _parse_rate_limit_wait(err: urllib.error.HTTPError, attempt: int) -> float:
    reset_header = err.headers.get("X-RateLimit-Reset") if err.headers else None
    if reset_header:
        try:
            reset_epoch = int(reset_header)
            wait = max(1.0, reset_epoch - time.time() + 2)
            return min(wait, 60)
        except (ValueError, TypeError):
            pass
    return min(60 * (2 ** attempt), 60)


_MAX_RATE_LIMIT_WAIT = 3600.0
_PREEMPTIVE_REMAINING_MIN = 1

# A rate limit that does not clear is a permanent failure, not a slow sync.
# The retry loop had no ceiling, so a request that was refused for a reason
# retrying cannot fix spun for hours: no error, no result, repository
# untouched, and nothing in the log to explain why.
_RATE_LIMIT_MAX_RETRIES = 3

# Released together, every waiter fires at GitHub on the same instant, which is
# what draws a secondary rate limit. The gate then re-armed and the whole cycle
# repeated, so the backoff could never converge. Each thread waits the gate out
# and then adds a short offset of its own.
_GATE_STAGGER_MAX = 8.0
# Bounded so this cannot spin: one round normally covers the gate, and a second
# catches one re-armed while this thread slept.
_GATE_MAX_ROUNDS = 3

def _body_excerpt(body: str, limit: int = 220) -> str:
    """A short single-line view of a GitHub error body.

    The body is the only thing that distinguishes an exhausted quota from a
    token that cannot reach the repository, and those need opposite fixes. It
    was being discarded, which left a five-hour stall unexplained.
    """
    collapsed = " ".join((body or "").split())
    if not collapsed:
        return "(empty response body)"
    if len(collapsed) > limit:
        return collapsed[:limit] + "..."
    return collapsed


def _rate_limit_wait_from(err: urllib.error.HTTPError, body: str) -> float | None:
    """Return seconds to back off for, or None when the error is not a rate limit.

    Handles GitHub's two flavours: 429 / 403 secondary limits (honoured via the
    ``Retry-After`` header) and 403 primary limits (honoured via
    ``X-RateLimit-Reset``). Falls back to exponential backoff when no header is
    present, and keeps retrying — the loop only ends on success or cancellation.
    """
    lowered = body.lower()
    is_secondary = err.code == 429 or (
        err.code == 403
        and ("rate limit" in lowered or "secondary" in lowered or "abuse" in lowered)
    )
    if not is_secondary:
        return None
    headers = err.headers or {}
    retry_after = headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(max(1.0, float(retry_after) + 1.0), _MAX_RATE_LIMIT_WAIT)
        except (ValueError, TypeError):
            pass
    reset_header = headers.get("X-RateLimit-Reset")
    if reset_header is not None:
        try:
            wait = max(1.0, float(reset_header) - time.time() + 2)
            return min(wait, _MAX_RATE_LIMIT_WAIT)
        except (ValueError, TypeError):
            pass
    return _parse_rate_limit_wait(err, 0)


# Per-thread release offsets are handed out from a counter held here rather than
# derived from get_ident(), which is pointer-aligned on aarch64 and so would
# return the same slot for every thread.
_GATE_STAGGER_SLOTS = 16
_GATE_STAGGER_ATTR = "_github_rate_limit_stagger"
_GATE_STAGGER_LOCK = threading.Lock()
_GATE_STAGGER_NEXT = 0


def _thread_stagger() -> float:
    """A stable per-thread release offset, spread across the stagger window.

    The offset is kept on the Thread object, so it needs no registry here and
    dies with the thread that owns it. It is handed out from a counter rather
    than derived from ``get_ident()``: on aarch64 that value is pointer-aligned,
    so ``get_ident() % 16`` is zero for every thread and would have disabled
    this silently - the stagger would read as working while staggering nothing.
    """
    global _GATE_STAGGER_NEXT
    thread = threading.current_thread()
    offset = getattr(thread, _GATE_STAGGER_ATTR, None)
    if offset is None:
        with _GATE_STAGGER_LOCK:
            slot = _GATE_STAGGER_NEXT % _GATE_STAGGER_SLOTS
            _GATE_STAGGER_NEXT += 1
        offset = slot / _GATE_STAGGER_SLOTS * _GATE_STAGGER_MAX
        setattr(thread, _GATE_STAGGER_ATTR, offset)
    return offset


