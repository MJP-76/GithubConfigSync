from __future__ import annotations

import base64
import asyncio
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

API_BASE = "https://api.github.com"
OAUTH_BASE = "https://github.com"


class GitHubError(Exception):
    pass


@dataclass
class GitHubBackupClient:
    hass: HomeAssistant
    token: str
    repository: str

    @property
    def session(self) -> aiohttp.ClientSession:
        return async_get_clientsession(self.hass)

    async def async_validate(self) -> dict[str, Any]:
        return await self._request("GET", "/user")

    async def async_start_device_flow(self, client_id: str) -> dict[str, Any]:
        return await self._oauth_request(
            "POST",
            "/login/device/code",
            json={"client_id": client_id, "scope": "repo"},
        )

    async def async_exchange_device_code(
        self, client_id: str, device_code: str, interval: int = 5, timeout: int = 600
    ) -> str:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            response = await self._oauth_request(
                "POST",
                "/login/oauth/access_token",
                json={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            payload = response
            if "access_token" in payload:
                return payload["access_token"]
            error = payload.get("error")
            if error == "authorization_pending":
                if asyncio.get_event_loop().time() >= deadline:
                    raise GitHubError("Timed out waiting for GitHub authorization")
                await asyncio.sleep(interval)
                continue
            if error == "slow_down":
                interval += 5
                await asyncio.sleep(interval)
                continue
            description = payload.get("error_description", error or "Auth failed")
            raise GitHubError(description)

    async def async_get_repository(self) -> dict[str, Any]:
        return await self._request("GET", f"/repos/{self.repository}")

    async def async_create_repo(
        self, name: str, private: bool, description: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "private": private}
        if description:
            payload["description"] = description
        return await self._request("POST", "/user/repos", json=payload)

    async def async_write_gitignore(
        self, local_folder: Path, extra_patterns: list[str]
    ) -> None:
        gitignore_path = local_folder / ".gitignore"
        lines = [
            "# Managed by Home Assistant Github Config Sync",
            "# Home Assistant core files",
            "secrets.yaml",
            "automations.yaml",
            "scripts.yaml",
            "scenes.yaml",
            ".storage/",
            ".cloud/",
            ".cache/",
            "tts/",
            "home-assistant_v2.db",
            "home-assistant_v2.db-shm",
            "home-assistant_v2.db-wal",
            "home-assistant.log",
            "home-assistant.log.*",
            "*.log",
            "*.log.*",
            "*.db",
            "*.sqlite",
            "*.sqlite3",
            "*.tmp",
            "*.swp",
            "# User additions",
        ]
        for pattern in extra_patterns:
            if pattern and pattern not in lines:
                lines.append(pattern)
        content = "\n".join(lines) + "\n"
        if not gitignore_path.exists() or gitignore_path.read_text(encoding="utf-8") != content:
            gitignore_path.write_text(content, encoding="utf-8")

    async def async_sync_local_folder_to_github(
        self,
        local_folder: Path,
        remote_path: str,
        ignore_patterns: list[str],
        message: str,
    ) -> dict[str, Any]:
        ignore_rules = self._load_ignore_rules(local_folder, ignore_patterns)
        synced = 0
        last_result: dict[str, Any] = {}
        for path in local_folder.rglob("*"):
            if path.is_dir():
                continue
            relative_path = path.relative_to(local_folder).as_posix()
            if self._is_ignored(relative_path, ignore_rules):
                continue
            remote_file_path = self._join_remote_path(remote_path, relative_path)
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            existing = await self._request(
                "GET",
                f"/repos/{self.repository}/contents/{quote(remote_file_path, safe='')}",
                allow_statuses={404},
            )
            payload: dict[str, Any] = {"message": message, "content": encoded}
            if existing.get("sha"):
                payload["sha"] = existing["sha"]
            last_result = await self._request(
                "PUT",
                f"/repos/{self.repository}/contents/{quote(remote_file_path, safe='')}",
                json=payload,
            )
            synced += 1
        return {"synced": synced, "last_result": last_result}

    async def async_sync_github_to_local_folder(
        self,
        local_folder: Path,
        remote_path: str,
        ignore_patterns: list[str],
    ) -> dict[str, Any]:
        ignore_rules = self._load_ignore_rules(local_folder, ignore_patterns)
        repo = await self.async_get_repository()
        branch = repo["default_branch"]
        tree = await self._request(
            "GET",
            f"/repos/{self.repository}/git/trees/{quote(branch, safe='')}?recursive=1",
        )
        synced = 0
        for item in tree.get("tree", []):
            if item.get("type") != "blob":
                continue
            remote_file_path = item["path"]
            if not self._matches_remote_path(remote_file_path, remote_path):
                continue
            relative_path = self._strip_remote_path(remote_file_path, remote_path)
            if self._is_ignored(relative_path, ignore_rules):
                continue
            content = await self._request("GET", item["url"])
            encoded = content.get("content", "")
            decoded = base64.b64decode(encoded.encode("ascii")) if encoded else b""
            destination = local_folder / Path(relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(decoded)
            synced += 1
        return {"synced": synced}

    async def _oauth_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        async with self.session.request(
            method,
            f"{OAUTH_BASE}{path}",
            headers=headers,
            json=json,
            timeout=60,
        ) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise GitHubError(str(data))
            return data

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        allow_statuses: set[int] | None = None,
        accept_json: bool = True,
    ) -> dict[str, Any]:
        allow_statuses = allow_statuses or set()
        url = f"{API_BASE}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with self.session.request(
            method, url, headers=headers, json=json, timeout=60
        ) as response:
            if response.status in allow_statuses:
                return {}
            if response.status >= 400:
                text = await response.text()
                raise GitHubError(f"GitHub API error {response.status}: {text}")
            if response.content_type == "application/json" and accept_json:
                return await response.json()
            return {"text": await response.text()}

    @staticmethod
    def _is_ignored(relative_path: str, ignore_rules: list[str]) -> bool:
        ignored = False
        basename = Path(relative_path).name
        for rule in ignore_rules:
            if not rule:
                continue
            negate = rule.startswith("!")
            pattern = rule[1:] if negate else rule
            if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(
                basename, pattern
            ):
                ignored = not negate
        return ignored

    @staticmethod
    def _load_ignore_rules(
        local_folder: Path, ignore_patterns: list[str]
    ) -> list[str]:
        rules = list(ignore_patterns)
        gitignore_path = local_folder / ".gitignore"
        if gitignore_path.is_file():
            for line in gitignore_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                rules.append(stripped)
        return rules

    @staticmethod
    def _normalize_remote_path(remote_path: str) -> str:
        remote_path = remote_path.strip().strip("/")
        return remote_path or "."

    @classmethod
    def _join_remote_path(cls, remote_path: str, relative_path: str) -> str:
        remote_path = cls._normalize_remote_path(remote_path)
        if remote_path == ".":
            return relative_path
        return f"{remote_path}/{relative_path}"

    @classmethod
    def _matches_remote_path(cls, remote_file_path: str, remote_path: str) -> bool:
        remote_path = cls._normalize_remote_path(remote_path)
        if remote_path == ".":
            return True
        return remote_file_path == remote_path or remote_file_path.startswith(
            f"{remote_path}/"
        )

    @classmethod
    def _strip_remote_path(cls, remote_file_path: str, remote_path: str) -> str:
        remote_path = cls._normalize_remote_path(remote_path)
        if remote_path == ".":
            return remote_file_path
        prefix = f"{remote_path}/"
        if remote_file_path.startswith(prefix):
            return remote_file_path[len(prefix) :]
        return remote_file_path
