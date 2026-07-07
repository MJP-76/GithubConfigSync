from __future__ import annotations

import json
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if importlib.util.find_spec("flask") is None:
    raise unittest.SkipTest("flask is required for server API tests")

import server


class ServerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._data_dir = Path(self._tmp.name) / "data"
        self._config_root = Path(self._tmp.name) / "config"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._config_root.mkdir(parents=True, exist_ok=True)

        self._orig_data_dir = server.DATA_DIR
        self._orig_supervisor_options = server.SUPERVISOR_OPTIONS_PATH
        self._orig_webui_options = server.WEBUI_OPTIONS_PATH
        self._orig_state = server.STATE_PATH
        self._orig_log = server.LOG_PATH
        self._orig_hash_index = server.HASH_INDEX_PATH
        self._orig_device_flow = server.DEVICE_FLOW_PATH
        self._orig_config_root = server.CONFIG_ROOT

        server.DATA_DIR = self._data_dir
        server.SUPERVISOR_OPTIONS_PATH = self._data_dir / "options.json"
        server.WEBUI_OPTIONS_PATH = self._data_dir / "webui_options.json"
        server.STATE_PATH = self._data_dir / "state.json"
        server.LOG_PATH = self._data_dir / "sync.log"
        server.HASH_INDEX_PATH = self._data_dir / "hash_index.json"
        server.DEVICE_FLOW_PATH = self._data_dir / "device_flow.json"
        server.CONFIG_ROOT = self._config_root

        self.addCleanup(self._restore_paths)
        self.client = server.app.test_client()

    def _restore_paths(self) -> None:
        server.DATA_DIR = self._orig_data_dir
        server.SUPERVISOR_OPTIONS_PATH = self._orig_supervisor_options
        server.WEBUI_OPTIONS_PATH = self._orig_webui_options
        server.STATE_PATH = self._orig_state
        server.LOG_PATH = self._orig_log
        server.HASH_INDEX_PATH = self._orig_hash_index
        server.DEVICE_FLOW_PATH = self._orig_device_flow
        server.CONFIG_ROOT = self._orig_config_root

    def _write_options(self, payload: dict[str, object]) -> None:
        server.WEBUI_OPTIONS_PATH.write_text(json.dumps(payload), encoding="utf-8")

    def test_sync_requires_repository(self) -> None:
        self._write_options(
            {
                "github_repository": "",
                "github_branch": "main",
                "github_token": "token",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        response = self.client.post("/api/sync")
        body = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(body["ok"])
        self.assertIn("github_repository is required", body["error"])

    def test_sync_dry_run_returns_summary(self) -> None:
        (self._config_root / "automations.yaml").write_text("id: test", encoding="utf-8")
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "token",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        response = self.client.post("/api/sync")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("Dry run completed", body["result"])
        self.assertEqual(body["summary"]["synced_count"], 1)

    def test_start_device_flow_returns_verification_data(self) -> None:
        self._write_options({"github_client_id": "client-id", "github_branch": "main"})
        with patch("server.GitHubClient.start_device_flow") as start_flow:
            start_flow.return_value = {
                "device_code": "device-code",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://github.com/login/device",
                "interval": 5,
                "expires_in": 900,
            }
            response = self.client.post("/api/auth/device/start", json={})

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["user_code"], "ABCD-EFGH")
        self.assertIn("verification_uri_complete", body)

    def test_complete_device_flow_stores_token(self) -> None:
        server.DEVICE_FLOW_PATH.write_text(
            json.dumps(
                {
                    "client_id": "client-id",
                    "device_code": "device-code",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://github.com/login/device",
                    "interval": 5,
                }
            ),
            encoding="utf-8",
        )
        self._write_options({"github_repository": "owner/repo", "github_branch": "main"})
        with patch("server.GitHubClient.exchange_device_code", return_value="gho_testtoken"):
            response = self.client.post("/api/auth/device/complete")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["options"]["github_token"], "********")

    def test_list_repositories_requires_auth_token(self) -> None:
        self._write_options({"github_repository": "owner/repo", "github_branch": "main", "github_token": ""})
        response = self.client.get("/api/repos")
        body = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(body["ok"])
        self.assertIn("Authenticate with Device Flow first", body["error"])

    def test_list_repositories_returns_picker_items(self) -> None:
        self._write_options({"github_repository": "owner/repo", "github_branch": "main", "github_token": "gho_x"})
        with patch("server.GitHubClient.list_user_repositories") as list_repos:
            list_repos.return_value = [
                {"name": "repo-a", "full_name": "owner/repo-a", "private": True},
                {"name": "repo-b", "full_name": "owner/repo-b", "private": False},
            ]
            response = self.client.get("/api/repos")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["repos"]), 2)
        self.assertEqual(body["repos"][0]["full_name"], "owner/repo-a")

    def test_create_repository_updates_selected_repository(self) -> None:
        self._write_options({"github_branch": "main", "github_token": "gho_x"})
        with patch("server.GitHubClient.create_repository") as create_repo:
            create_repo.return_value = {"full_name": "owner/new-config-repo"}
            response = self.client.post(
                "/api/repos/create",
                json={"name": "new-config-repo", "private": True, "description": "desc"},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["repository"], "owner/new-config-repo")

    def test_status_includes_auth_diagnostics(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        response = self.client.get("/api/status")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["auth"]["token_state"], "configured")
        self.assertEqual(body["auth"]["repository_state"], "configured")

    def test_diagnostics_bundle_masks_token(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        response = self.client.get("/api/diagnostics")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["options"]["github_token"], "********")
        self.assertEqual(body["auth"]["token_state"], "configured")


if __name__ == "__main__":
    unittest.main()
