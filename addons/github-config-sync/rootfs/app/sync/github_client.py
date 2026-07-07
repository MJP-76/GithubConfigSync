from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .errors import SyncError

API_BASE = "https://api.github.com"
OAUTH_BASE = "https://github.com"


@dataclass(frozen=True)
class GitHubClient:
    repository: str
    branch: str
    token: str

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
        return self._request_json(
            "PUT",
            f"{self._base}/contents/{encoded}",
            payload=payload,
        )

    def delete_content(self, path: str, sha: str, message: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(path, safe="")
        payload = {"message": message, "sha": sha, "branch": self.branch}
        return self._request_json(
            "DELETE",
            f"{self._base}/contents/{encoded}",
            payload=payload,
        )

    def _request_json(self, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        decoded = self._request_any(method, url, payload=payload)
        if not isinstance(decoded, dict):
            raise SyncError(f"GitHub API returned non-object JSON for {method} {url}")
        return decoded

    def _request_any(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        data = None
        headers = dict(self._headers)
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, method=method, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="ignore")
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
