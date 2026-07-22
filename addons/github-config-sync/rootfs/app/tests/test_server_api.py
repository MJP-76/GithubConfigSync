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
        self.assertIn("Would upsert", body["result"])
        self.assertEqual(body["summary"]["synced_count"], 1)
        self.assertEqual(body["summary"]["deleted_count"], 0)

    def test_options_round_trip_include_addon_configs_default_true(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "token",
                "sync_interval_minutes": 60,
                "dry_run": True,
                "include_addon_configs": True,
            }
        )

        response = self.client.get("/api/options")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["include_addon_configs"])

    def test_options_round_trip_auth_method_defaults_to_device_flow(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "token",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        response = self.client.get("/api/options")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["auth_method"], "device_flow")

    def test_start_device_flow_returns_verification_data(self) -> None:
        self._write_options({"github_client_id": "client-id", "github_branch": "main"})
        with patch("sync.github_client.GitHubClient.start_device_flow") as start_flow:
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
        with patch("sync.github_client.GitHubClient.exchange_device_code", return_value="gho_testtoken"):
            response = self.client.post("/api/auth/device/complete")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["options"]["github_token"], "********")

    def test_list_repositories_requires_auth_token(self) -> None:
        self._write_options(
            {
                "release_channel": "stable",
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "",
            }
        )
        response = self.client.get("/api/repos")
        body = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(body["ok"])
        self.assertIn("GitHub token is missing", body["error"])

    def test_list_repositories_returns_picker_items(self) -> None:
        self._write_options({"github_repository": "owner/repo", "github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.list_user_repositories") as list_repos:
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
        self._write_options({"auth_method": "device_flow", "github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.create_repository") as create_repo:
            create_repo.return_value = {"full_name": "owner/new-config-repo"}
            response = self.client.post(
                "/api/repos/create",
                json={"name": "new-config-repo", "private": True, "description": "desc"},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["repository"], "owner/new-config-repo")

    def test_create_repository_respects_visibility_choice(self) -> None:
        self._write_options({"auth_method": "device_flow", "github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.create_repository") as create_repo:
            create_repo.return_value = {"full_name": "owner/new-config-repo"}
            response = self.client.post(
                "/api/repos/create",
                json={"name": "new-config-repo", "private": False, "description": "desc"},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        create_repo.assert_called_once()
        self.assertFalse(create_repo.call_args.kwargs["private"])

    def test_status_and_diagnostics_do_not_expose_token(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        status = self.client.get("/api/status").get_json()
        diagnostics = self.client.get("/api/diagnostics").get_json()

        self.assertEqual(status["auth"]["token_state"], "configured")
        self.assertEqual(status["repo_versions"]["stable"], "0.2.39")
        self.assertEqual(status["repo_versions"]["rc"], "0.3.2")
        self.assertEqual(status["repo_versions"]["dev"], server.APP_VERSION)
        self.assertEqual(diagnostics["options"]["github_token"], "********")

    def test_create_repository_uses_default_name_when_blank(self) -> None:
        self._write_options({"github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.create_repository") as create_repo:
            create_repo.return_value = {"full_name": "owner/ha-github-config-sync"}
            response = self.client.post(
                "/api/repos/create",
                json={"name": "", "private": True, "description": ""},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["repository"], "owner/ha-github-config-sync")
        self.assertEqual(create_repo.call_args.kwargs["name"], "ha-github-config-sync")

    def test_create_repository_defaults_visibility_to_private(self) -> None:
        self._write_options({"auth_method": "device_flow", "github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.create_repository") as create_repo:
            create_repo.return_value = {"full_name": "owner/ha-github-config-sync"}
            response = self.client.post(
                "/api/repos/create",
                json={"name": "ha-github-config-sync", "description": "desc"},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(create_repo.call_args.kwargs["private"])

    def test_create_repository_rejects_non_boolean_private_flag(self) -> None:
        self._write_options({"auth_method": "device_flow", "github_branch": "main", "github_token": "gho_x"})
        response = self.client.post(
            "/api/repos/create",
            json={"name": "ha-github-config-sync", "private": "no", "description": "desc"},
        )

        body = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(body["ok"])
        self.assertIn("private must be true or false", body["error"])

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
        self.assertEqual(body["auth"]["token_saved"], True)
        self.assertIn(body["token_health"]["state"], ["valid", "expired", "error"])

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
        self.assertIn("token_health", body)

    def test_status_reports_missing_token_health(self) -> None:
        self._write_options({"github_repository": "owner/repo", "github_branch": "main", "github_token": ""})
        response = self.client.get("/api/status")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["token_health"]["state"], "missing")

    def test_ignore_recommendations_round_trip_to_local_gitignore(self) -> None:
        response = self.client.get("/api/ignore/recommendations")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertGreater(len(body["patterns"]), 0)

        selected = [item["pattern"] for item in body["patterns"][:2]]
        response = self.client.post("/api/ignore/recommendations", json={"patterns": selected})
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        gitignore = (self._config_root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(selected[0], gitignore)

    def test_cancel_sync_endpoint_sets_state_flag(self) -> None:
        response = self.client.post("/api/sync/cancel")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        status = self.client.get("/api/status").get_json()
        self.assertTrue(status["cancel_sync"])

    def test_clean_sync_returns_summary_and_updates_state(self) -> None:
        (self._config_root / "one.txt").write_text("one", encoding="utf-8")
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )
        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.clean_remote_tree.return_value = None
            engine._github.probe_repository.return_value = (True, "Repository probe succeeded")
            engine.clean_plan.return_value = (
                unittest.mock.MagicMock(
                    added=["one.txt"],
                    changed=[],
                    removed=[],
                    total_files=1,
                ),
                {"one.txt": "abc"},
            )
            engine.run.return_value = unittest.mock.MagicMock(
                synced_count=1, deleted_count=1, skipped_count=0, total_files=1, message="Sync completed."
            )
            response = self.client.post("/api/sync/clean")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"], "Sync completed.")
        self.assertIsNotNone(body["state"].get("last_scan"))

    def test_clean_sync_forces_live_upload_even_when_dry_run_is_enabled(self) -> None:
        (self._config_root / "one.txt").write_text("one", encoding="utf-8")
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
                "scheduled_live_sync": True,
            }
        )

        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.clean_remote_tree.return_value = None
            engine._github.probe_repository.return_value = (True, "Repository probe succeeded")
            engine.clean_plan.return_value = (
                unittest.mock.MagicMock(
                    added=["one.txt"],
                    changed=[],
                    removed=[],
                    total_files=1,
                ),
                {"one.txt": "abc"},
            )
            engine.run.return_value = unittest.mock.MagicMock(
                synced_count=1, deleted_count=1, skipped_count=0, total_files=1, message="Sync completed."
            )
            response = self.client.post("/api/sync/clean")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"], "Sync completed.")

    def test_clean_sync_clears_remote_tree_before_upload(self) -> None:
        (self._config_root / "one.txt").write_text("one", encoding="utf-8")
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.clean_remote_tree.return_value = None
            engine._github.probe_repository.return_value = (True, "Repository probe succeeded")
            engine.clean_plan.return_value = (
                unittest.mock.MagicMock(
                    added=["one.txt"],
                    changed=[],
                    removed=[],
                    total_files=1,
                ),
                {"one.txt": "abc"},
            )
            engine.run.return_value = unittest.mock.MagicMock(
                synced_count=1, deleted_count=1, skipped_count=0, total_files=1, message="Sync completed."
            )
            response = self.client.post("/api/sync/clean")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"], "Sync completed.")
        engine.clean_remote_tree.assert_called_once()

    def test_clean_repo_endpoint_clears_remote_tree_without_upload(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.clean_remote_tree.return_value = None
            response = self.client.post("/api/sync/clean-repo")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"], "Clean repo completed. Remote repo skeleton restored.")
        engine.clean_remote_tree.assert_called_once()
        engine.restore_repo_skeleton.assert_called_once()

    def test_manual_sync_endpoint_uses_retention_days(self) -> None:
        (self._config_root / "one.txt").write_text("one", encoding="utf-8")
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 1440,
                "version_retention_count": 7,
                "manual_version_retention_days": 7,
                "dry_run": True,
            }
        )
        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine._github.probe_repository.return_value = (True, "Repository probe succeeded")
            engine.plan.return_value = (
                unittest.mock.MagicMock(
                    added=["one.txt"],
                    changed=[],
                    removed=[],
                    total_files=1,
                ),
                {"one.txt": "abc"},
            )
            engine.run.return_value = unittest.mock.MagicMock(
                synced_count=1, deleted_count=0, skipped_count=0, total_files=1, message="Sync completed."
            )
            response = self.client.post("/api/sync/manual")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("Would upsert", body["result"])

    def test_manual_sync_respects_dry_run_mode(self) -> None:
        (self._config_root / "one.txt").write_text("one", encoding="utf-8")
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 1440,
                "version_retention_count": 7,
                "manual_version_retention_days": 7,
                "dry_run": True,
            }
        )
        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.plan.return_value = (
                unittest.mock.MagicMock(
                    added=["one.txt"],
                    changed=[],
                    removed=[],
                    total_files=1,
                ),
                {"one.txt": "abc"},
            )
            response = self.client.post("/api/sync/manual")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("Would upsert", body["result"])
        engine.plan.assert_called_once()

    def test_device_flow_persists_token_to_both_option_files(self) -> None:
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
        with patch("server.GitHubClient.exchange_device_code", return_value="gho_persisted"):
            response = self.client.post("/api/auth/device/complete")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("gho_persisted", server.SUPERVISOR_OPTIONS_PATH.read_text(encoding="utf-8"))
        self.assertIn("gho_persisted", server.WEBUI_OPTIONS_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
