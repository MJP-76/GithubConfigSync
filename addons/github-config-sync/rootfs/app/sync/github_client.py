from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .errors import SyncError


@dataclass(frozen=True)
class GitHubClient:
    repository: str
    branch: str
    token: str

    @property
    def _base(self) -> str:
        return f"https://api.github.com/repos/{self.repository}"

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

    def probe_repository(self) -> tuple[bool, str]:
        try:
            payload = self._request_json("GET", f"{self._base}")
            if payload.get("full_name"):
                return True, "Repository probe succeeded"
            return False, "Repository probe returned incomplete payload"
        except SyncError as err:
            return False, str(err)

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
                decoded = json.loads(body)
                if not isinstance(decoded, dict):
                    raise SyncError(f"GitHub API returned non-object JSON for {method} {url}")
                return decoded
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="ignore")
            raise SyncError(f"GitHub API error HTTP {err.code} for {method} {url}: {body}") from err
        except urllib.error.URLError as err:
            raise SyncError(f"GitHub API request failed for {method} {url}: {err.reason}") from err
