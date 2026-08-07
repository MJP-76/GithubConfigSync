from __future__ import annotations

import json
import os
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
        os.environ["FLASK_DEBUG"] = "1"
        self._orig_supervisor_token = os.environ.pop("SUPERVISOR_TOKEN", None)
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
        self._orig_managed_repos = server.MANAGED_REPOS_PATH
        self._orig_device_flow = server.DEVICE_FLOW_PATH
        self._orig_config_root = server.CONFIG_ROOT

        server.DATA_DIR = self._data_dir
        server.SUPERVISOR_OPTIONS_PATH = self._data_dir / "options.json"
        server.WEBUI_OPTIONS_PATH = self._data_dir / "webui_options.json"
        server.STATE_PATH = self._data_dir / "state.json"
        server.LOG_PATH = self._data_dir / "sync.log"
        server.HASH_INDEX_PATH = self._data_dir / "hash_index.json"
        server.MANAGED_REPOS_PATH = self._data_dir / "managed_repos.json"
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
        server.MANAGED_REPOS_PATH = self._orig_managed_repos
        server.DEVICE_FLOW_PATH = self._orig_device_flow
        server.CONFIG_ROOT = self._orig_config_root
        if self._orig_supervisor_token is not None:
            os.environ["SUPERVISOR_TOKEN"] = self._orig_supervisor_token

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

    def test_options_round_trip_include_addon_configs_explicit_true(self) -> None:
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
                {"name": "repo", "full_name": "owner/repo", "private": True},
                {"name": "repo-a", "full_name": "owner/repo-a", "private": True},
                {"name": "repo-b", "full_name": "owner/repo-b", "private": False},
            ]
            with patch("sync.github_client.GitHubClient.list_directory_contents", return_value=[]):
                response = self.client.get("/api/repos")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertGreaterEqual(len(body["repos"]), 2)
        full_names = [r["full_name"] for r in body["repos"]]
        self.assertIn("owner/repo-a", full_names)
        self.assertIn("owner/repo-b", full_names)

    def test_list_managed_repositories_only_returns_marked_repos(self) -> None:
        self._write_options({"github_repository": "owner/repo", "github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.list_user_repositories") as list_repos:
            list_repos.return_value = [
                {"name": "repo-a", "full_name": "owner/repo-a", "private": True, "default_branch": "main"},
                {"name": "repo-b", "full_name": "owner/repo-b", "private": False, "default_branch": "main"},
            ]
            with patch("sync.github_client.GitHubClient.list_directory_contents") as list_contents:
                list_contents.side_effect = [
                    [{"path": server.ADDON_REPO_MARKER_PATH}],  # repo-a: managed
                    [{"path": "README.md"}],                   # repo-b: not managed
                    [{"path": "other.txt"}],                   # current_repo (owner/repo): not managed
                ]
                response = self.client.get("/api/repos/managed")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["repos"]), 1)
        self.assertEqual(body["repos"][0]["full_name"], "owner/repo-a")
        self.assertTrue(body["repos"][0]["managed"])

    def test_adopt_repository_marks_repo_and_updates_options(self) -> None:
        self._write_options({"github_repository": "", "github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.write_repo_marker") as write_marker:
            response = self.client.post(
                "/api/repos/adopt",
                json={"repository": "owner/repo-a", "private": True},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["repository"], "owner/repo-a")
        write_marker.assert_called_once()
        saved = json.loads(server.WEBUI_OPTIONS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved["github_repository"], "owner/repo-a")
        self.assertEqual(saved["existing_repo_confirmed_for"], "owner/repo-a")

    def test_create_repository_updates_selected_repository(self) -> None:
        self._write_options({"auth_method": "device_flow", "github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.create_repository") as create_repo:
            create_repo.return_value = {"full_name": "owner/new-config-repo"}
            with patch("sync.github_client.GitHubClient.write_repo_marker") as write_marker:
                with patch("sync.engine.SyncEngine.restore_repo_skeleton") as restore_skeleton:
                    response = self.client.post(
                        "/api/repos/create",
                        json={"name": "new-config-repo", "private": True, "description": "desc"},
                    )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["repository"], "owner/new-config-repo")
        write_marker.assert_called_once()
        restore_skeleton.assert_called_once()

    def test_create_repository_respects_visibility_choice(self) -> None:
        self._write_options({"auth_method": "device_flow", "github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.create_repository") as create_repo:
            create_repo.return_value = {"full_name": "owner/new-config-repo"}
            with patch("sync.github_client.GitHubClient.write_repo_marker"):
                with patch("sync.engine.SyncEngine.restore_repo_skeleton"):
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
        self.assertEqual(status["repo_versions"]["stable"], server.STABLE_REPO_VERSION)
        self.assertEqual(status["repo_versions"]["dev"], server.DEV_REPO_VERSION)
        self.assertEqual(diagnostics["options"]["github_token"], "********")

    def test_changelog_endpoint_returns_latest_five_entries(self) -> None:
        changelog_path = server.CHANGELOG_PATH
        original = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else None
        self.addCleanup(
            lambda: changelog_path.write_text(original, encoding="utf-8") if original is not None else changelog_path.unlink(missing_ok=True)
        )
        changelog_path.write_text(
            "\n".join(
                [
                    "# Changelog",
                    "",
                    "## Unreleased",
                    "",
                    "- one",
                    "- two",
                    "- three",
                    "- four",
                    "- five",
                    "- six",
                ]
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/changelog")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["entries"], ["one", "two", "three", "four", "five"])

    def test_create_repository_uses_default_name_when_blank(self) -> None:
        self._write_options({"github_branch": "main", "github_token": "gho_x"})
        with patch("sync.github_client.GitHubClient.create_repository") as create_repo:
            create_repo.return_value = {"full_name": "owner/ha-github-config-sync"}
            with patch("sync.github_client.GitHubClient.write_repo_marker"):
                with patch("sync.engine.SyncEngine.restore_repo_skeleton"):
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
            with patch("sync.github_client.GitHubClient.write_repo_marker"):
                with patch("sync.engine.SyncEngine.restore_repo_skeleton"):
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
        # /api/status must never block on a live GitHub call; empty cache => "checking"
        self.assertEqual(body["token_health"]["state"], "checking")

    def test_token_health_endpoint_runs_live_check_and_caches(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )

        with patch("server.GitHubClient._request_json", return_value={"login": "octocat"}):
            response = self.client.get("/api/token/health")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["token_health"]["state"], "valid")

        # The live result must be cached so /api/status picks it up without a new GitHub call
        status_body = self.client.get("/api/status").get_json()
        self.assertEqual(status_body["token_health"]["state"], "valid")

    def test_token_health_reports_missing_without_github_call(self) -> None:
        self._write_options({"github_repository": "owner/repo", "github_branch": "main", "github_token": ""})
        with patch("server.GitHubClient._request_json", side_effect=AssertionError("must not hit GitHub")):
            response = self.client.get("/api/token/health")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["token_health"]["state"], "missing")

    def test_status_never_hits_github(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )
        with patch("server.GitHubClient._request_json", side_effect=AssertionError("must not hit GitHub")):
            response = self.client.get("/api/status")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["token_health"]["state"], "checking")

    def test_sync_options_to_supervisor_uses_self_endpoint_with_wrapped_payload(self) -> None:
        captured = {}

        class FakeResponse:
            status = 200

            def read(self) -> bytes:
                return b'{"result": "ok"}'

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(request, timeout=10):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["data"] = json.loads(request.data.decode())
            captured["authorization"] = request.headers.get("Authorization")
            return FakeResponse()

        os.environ["SUPERVISOR_TOKEN"] = "supervisor-test-token"
        self.addCleanup(lambda: os.environ.pop("SUPERVISOR_TOKEN", None))
        with patch("server.urllib.request.urlopen", side_effect=fake_urlopen):
            server._sync_options_to_supervisor(
                {"github_repository": "owner/repo", "github_token": "secret-token"}
            )

        self.assertEqual(captured["url"], "http://supervisor/addons/self/options")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(
            captured["data"],
            {"options": {"github_repository": "owner/repo", "github_token": "secret-token"}},
        )
        self.assertEqual(captured["authorization"], "Bearer supervisor-test-token")

    def test_set_options_ignores_masked_token_placeholder(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "real-token",
                "sync_interval_minutes": 60,
                "dry_run": True,
            }
        )
        response = self.client.post(
            "/api/options",
            json={
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "********",
                "sync_interval_minutes": 60,
                "dry_run": True,
            },
        )
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["options"]["github_token"], "********")
        self.assertEqual(server._merge_options()["github_token"], "real-token")

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
                "existing_repo_confirmed_for": "owner/repo",
            }
        )
        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.clean_remote_tree.return_value = None
            engine._github.probe_repository.return_value = (True, "Repository probe succeeded")
            engine.sensitive_files.return_value = []
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
                "existing_repo_confirmed_for": "owner/repo",
            }
        )

        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.clean_remote_tree.return_value = None
            engine._github.probe_repository.return_value = (True, "Repository probe succeeded")
            engine.sensitive_files.return_value = []
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
                "existing_repo_confirmed_for": "owner/repo",
            }
        )

        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.clean_remote_tree.return_value = None
            engine._github.probe_repository.return_value = (True, "Repository probe succeeded")
            engine.sensitive_files.return_value = []
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
            engine._github.write_repo_marker.return_value = {"ok": True}
            response = self.client.post("/api/sync/clean-repo")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"], "Clean repo completed. Remote repo fully reset and skeleton restored.")
        engine.clean_remote_tree.assert_called_once()
        engine.restore_repo_skeleton.assert_called_once()
        engine._github.write_repo_marker.assert_called_once()

    def test_clean_upload_allows_empty_existing_repository(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
                "dry_run": True,
                "existing_repo_confirmed_for": "owner/repo",
            }
        )
        (self._config_root / "one.txt").write_text("one", encoding="utf-8")

        with patch("server.SyncEngine") as engine_cls:
            engine = engine_cls.return_value
            engine._github.list_directory_contents.return_value = []
            engine._github.probe_repository.return_value = (True, "Repository probe succeeded")
            engine._github.write_repo_marker.return_value = {"ok": True}
            engine.sensitive_files.return_value = []
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
                synced_count=1, deleted_count=0, skipped_count=0, total_files=1, message="Sync completed."
            )
            response = self.client.post("/api/sync/clean")

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        engine.clean_remote_tree.assert_called_once()
        engine._github.write_repo_marker.assert_called_once()

    def test_manual_sync_endpoint_uses_retention_days(self) -> None:
        (self._config_root / "one.txt").write_text("one", encoding="utf-8")
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "gho_test",
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

    def test_all_include_flags_default_to_false_when_keys_missing(self) -> None:
        self._write_options(
            {
                "github_repository": "owner/repo",
                "github_branch": "main",
                "github_token": "token",
                "dry_run": True,
            }
        )

        sync_config = server._sync_config(server._merge_options())

        for flag in (
            "include_www",
            "include_media",
            "include_share",
            "include_ssl",
            "include_backups",
            "include_addon_configs",
        ):
            self.assertFalse(
                getattr(sync_config, flag),
                f"{flag} must default to false unless explicitly selected",
            )


class AuthBehaviorTests(unittest.TestCase):
    """Tests for the new _require_auth() behavior."""

    def setUp(self) -> None:
        # Clear FLASK_DEBUG to test real auth behavior
        os.environ.pop("FLASK_DEBUG", None)
        self._orig_supervisor_token = os.environ.pop("SUPERVISOR_TOKEN", None)
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
        self._orig_managed_repos = server.MANAGED_REPOS_PATH
        self._orig_device_flow = server.DEVICE_FLOW_PATH
        self._orig_config_root = server.CONFIG_ROOT

        server.DATA_DIR = self._data_dir
        server.SUPERVISOR_OPTIONS_PATH = self._data_dir / "options.json"
        server.WEBUI_OPTIONS_PATH = self._data_dir / "webui_options.json"
        server.STATE_PATH = self._data_dir / "state.json"
        server.LOG_PATH = self._data_dir / "sync.log"
        server.HASH_INDEX_PATH = self._data_dir / "hash_index.json"
        server.MANAGED_REPOS_PATH = self._data_dir / "managed_repos.json"
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
        server.MANAGED_REPOS_PATH = self._orig_managed_repos
        server.DEVICE_FLOW_PATH = self._orig_device_flow
        server.CONFIG_ROOT = self._orig_config_root
        if self._orig_supervisor_token is not None:
            os.environ["SUPERVISOR_TOKEN"] = self._orig_supervisor_token

    def _write_options(self, payload: dict[str, object]) -> None:
        server.WEBUI_OPTIONS_PATH.write_text(json.dumps(payload), encoding="utf-8")

    def test_get_without_auth_returns_401(self) -> None:
        self._write_options({"github_token": "secret-token"})
        for endpoint in (
            "/api/options",
            "/api/repos",
            "/api/repos/managed",
            "/api/repos/cached",
            "/api/diagnostics",
            "/api/changelog",
            "/api/ignore/recommendations",
        ):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 401, f"{endpoint} should require auth")

    def test_post_without_auth_returns_401(self) -> None:
        self._write_options({"github_token": "secret-token"})
        for endpoint in (
            "/api/sync/manual",
            "/api/options",
            "/api/ignore/recommendations",
            "/api/ignore/recommendations/reset",
            "/api/repos/adopt",
            "/api/repos/create",
            "/api/sync",
            "/api/sync/cancel",
            "/api/sync/clean",
            "/api/sync/clean-repo",
        ):
            response = self.client.post(endpoint, json={})
            self.assertEqual(response.status_code, 401, f"{endpoint} should require auth")

    def test_get_with_valid_bearer_token_succeeds(self) -> None:
        self._write_options({"github_token": "my-secret-token"})
        response = self.client.get(
            "/api/options",
            headers={"Authorization": "Bearer my-secret-token"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("github_token", body)

    def test_get_with_invalid_bearer_token_fails(self) -> None:
        self._write_options({"github_token": "my-secret-token"})
        response = self.client.get(
            "/api/options",
            headers={"Authorization": "Bearer wrong-token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_get_with_malformed_auth_header_fails(self) -> None:
        self._write_options({"github_token": "my-secret-token"})
        response = self.client.get(
            "/api/options",
            headers={"Authorization": "NotBearer token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_health_and_root_remain_open(self) -> None:
        # /api/health should not require auth
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
