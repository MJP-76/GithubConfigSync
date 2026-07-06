from __future__ import annotations

import base64
import fnmatch
import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

API_BASE = "https://api.github.com"


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

    async def async_create_repo(
        self, name: str, private: bool, description: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "private": private}
        if description:
            payload["description"] = description
        return await self._request("POST", "/user/repos", json=payload)

    async def async_build_archive(
        self,
        config_dir: Path,
        backup_prefix: str,
        ignore_patterns: list[str],
    ) -> tuple[str, bytes]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        archive_name = f"{backup_prefix}-{stamp}.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for path in config_dir.rglob("*"):
                if path.is_dir():
                    continue
                relative_path = path.relative_to(config_dir).as_posix()
                if self._is_ignored(relative_path, ignore_patterns):
                    continue
                zip_file.write(path, arcname=relative_path)
        return archive_name, buffer.getvalue()

    async def async_upload_archive(
        self, archive_name: str, archive_bytes: bytes, message: str
    ) -> dict[str, Any]:
        archive_path = f"backups/{archive_name}"
        encoded = base64.b64encode(archive_bytes).decode("ascii")
        existing = await self._request(
            "GET",
            f"/repos/{self.repository}/contents/{quote(archive_path, safe='')}",
            allow_statuses={404},
        )
        payload: dict[str, Any] = {
            "message": message,
            "content": encoded,
        }
        if existing.get("sha"):
            payload["sha"] = existing["sha"]
        return await self._request(
            "PUT",
            f"/repos/{self.repository}/contents/{quote(archive_path, safe='')}",
            json=payload,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        allow_statuses: set[int] | None = None,
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
            if response.content_type == "application/json":
                return await response.json()
            return {"text": await response.text()}

    @staticmethod
    def _is_ignored(relative_path: str, ignore_patterns: list[str]) -> bool:
        for pattern in ignore_patterns:
            if pattern and fnmatch.fnmatch(relative_path, pattern):
                return True
        return False
