from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sync.engine import SyncEngine
from sync.models import SyncConfig, SyncPlan


class SyncEngineTests(unittest.TestCase):
    def test_plan_detects_added_changed_removed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "new.yaml").write_text("new", encoding="utf-8")
            (root / "changed.yaml").write_text("new-value", encoding="utf-8")
            addon_root = Path(tmp) / "addon_configs"
            (addon_root / "apps").mkdir(parents=True)
            (addon_root / "apps" / "kitchen.yaml").write_text("id: app", encoding="utf-8")

            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                addon_config_root=str(addon_root),
                dry_run=True,
            )

            previous = {
                "changed.yaml": "old-hash",
                "removed.yaml": "removed-hash",
                "addon_configs/apps/old.yaml": "old-addon",
            }

            engine = SyncEngine(config, previous_hash_index=previous)
            plan, _ = engine.plan()

            self.assertEqual(plan.added, ["addon_configs/apps/kitchen.yaml", "new.yaml"])
            self.assertEqual(plan.changed, ["changed.yaml"])
            self.assertEqual(plan.removed, ["addon_configs/apps/old.yaml", "removed.yaml"])
            self.assertIn("addon_configs/apps/kitchen.yaml", plan.added)

    def test_run_dry_run_returns_counts_without_github_calls(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=True,
        )
        plan = SyncPlan(added=["a.yaml"], changed=["b.yaml"], removed=["c.yaml"], total_files=2)

        with patch("sync.engine.GitHubClient") as client_cls:
            engine = SyncEngine(config, previous_hash_index={})
            result = engine.run(plan)

        self.assertEqual(result.synced_count, 2)
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(result.skipped_count, 0)
        self.assertIn("Dry run completed", result.message)
        client_cls.return_value.put_content.assert_not_called()
        client_cls.return_value.delete_content.assert_not_called()

    def test_run_live_upserts_deletes_and_skips_missing_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "added.yaml").write_text("added", encoding="utf-8")
            (root / "changed.yaml").write_text("changed", encoding="utf-8")

            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                addon_config_root="/addon_configs",
                dry_run=False,
                version_retention_count=0,
            )
            plan = SyncPlan(
                added=["added.yaml", "missing.yaml"],
                changed=["changed.yaml"],
                removed=["removed.yaml", "unknown.yaml"],
                total_files=2,
            )

            fake_client = MagicMock()
            fake_client.get_content.side_effect = [
                {"sha": "a1"},
                {"sha": "b1"},
                {"sha": "c1"},
                None,
            ]

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                result = engine.run(plan)

            self.assertEqual(result.synced_count, 2)
            self.assertEqual(result.deleted_count, 1)
            self.assertEqual(result.skipped_count, 2)
            self.assertIn("Sync completed", result.message)
            self.assertEqual(fake_client.put_content.call_count, 2)
            self.assertEqual(fake_client.delete_content.call_count, 1)

    def test_run_live_retries_on_sha_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.yaml").write_text("a", encoding="utf-8")

            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                addon_config_root="/addon_configs",
                dry_run=False,
                version_retention_count=0,
            )
            plan = SyncPlan(added=["a.yaml"], changed=[], removed=[], total_files=1)

            fake_client = MagicMock()
            fake_client.get_content.side_effect = [
                {"sha": "oldsha"},
                {"sha": "newsha"},
            ]
            fake_client.put_content.side_effect = [
                Exception('GitHub API error HTTP 409 for PUT https://api.github.com/repos/owner/repo/contents/a.yaml: {"status":"409"}'),
                {"content": {"html_url": "https://example.com"}},
            ]

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                result = engine.run(plan)

            self.assertEqual(result.synced_count, 1)
            self.assertEqual(fake_client.put_content.call_count, 2)

    def test_put_content_retries_on_sha_conflict(self) -> None:
        from sync.github_client import GitHubClient
        from sync.errors import SyncError

        client = GitHubClient(repository="owner/repo", branch="main", token="token")
        calls = {"count": 0}

        def fake_request(method: str, url: str, payload=None):  # noqa: ANN001
            calls["count"] += 1
            if calls["count"] == 1:
                raise SyncError(
                    'GitHub API error HTTP 409 for PUT https://api.github.com/repos/owner/repo/contents/.gitignore: {"status":"409"}'
                )
            return {"content": {"path": ".gitignore"}}

        with patch.object(GitHubClient, "_request_json", side_effect=fake_request), patch.object(
            GitHubClient, "get_content", return_value={"sha": "refreshed"}
        ):
            result = client.put_content(".gitignore", b"data", "update .gitignore", sha="stale")

        self.assertEqual(result["content"]["path"], ".gitignore")
        self.assertEqual(calls["count"], 2)

    def test_run_live_can_be_cancelled_between_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.yaml").write_text("1", encoding="utf-8")
            (root / "two.yaml").write_text("2", encoding="utf-8")

            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                addon_config_root="/addon_configs",
                dry_run=False,
            )
            plan = SyncPlan(added=["one.yaml", "two.yaml"], changed=[], removed=[], total_files=2)
            fake_client = MagicMock()
            fake_client.get_content.return_value = None
            calls = {"count": 0}

            def cancel_checker() -> bool:
                calls["count"] += 1
                return calls["count"] > 1

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                engine.set_cancel_checker(cancel_checker)
                result = engine.run(plan)

            self.assertTrue(result.cancelled)
            self.assertEqual(result.synced_count, 1)
            self.assertEqual(fake_client.put_content.call_count, 1)

    def test_run_live_writes_version_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.yaml").write_text("1", encoding="utf-8")

            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                addon_config_root="/addon_configs",
                dry_run=False,
                version_retention_count=7,
            )
            plan = SyncPlan(added=["one.yaml"], changed=[], removed=[], total_files=1)
            fake_client = MagicMock()
            fake_client.get_content.return_value = None
            fake_client.list_directory_contents.return_value = []

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                result = engine.run(plan)

            self.assertEqual(result.synced_count, 1)
            uploaded_paths = [call.kwargs["path"] for call in fake_client.put_content.call_args_list]
            self.assertIn("one.yaml", uploaded_paths)
            self.assertTrue(any(path.startswith("versions/") for path in uploaded_paths))

    def test_run_live_retries_version_snapshot_on_sha_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.yaml").write_text("1", encoding="utf-8")
            (root / ".cache").mkdir()
            (root / ".cache" / "brands").mkdir(parents=True)
            (root / ".cache" / "brands" / "icon.png").write_bytes(b"png")

            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                addon_config_root="/addon_configs",
                dry_run=False,
                version_retention_count=7,
            )
            plan = SyncPlan(added=["one.yaml"], changed=[], removed=[], total_files=1)
            fake_client = MagicMock()
            fake_client.get_content.side_effect = [
                None,
                None,
                {"sha": "stale"},
                {"sha": "fresh"},
            ]
            fake_client.list_directory_contents.return_value = []
            fake_client.put_content.side_effect = [
                {"content": {"path": "one.yaml"}},
                Exception('GitHub API error HTTP 409 for PUT https://api.github.com/repos/owner/repo/contents/versions%2F20260707T204145Z%2Fone.yaml: {"status":"409"}'),
                {"content": {"path": "versions/20260707T204145Z/one.yaml"}},
            ]

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                result = engine.run(plan)

            self.assertEqual(result.synced_count, 1)
            self.assertGreaterEqual(fake_client.put_content.call_count, 3)
            uploaded_paths = [call.kwargs["path"] for call in fake_client.put_content.call_args_list]
            self.assertNotIn("versions/20260707T204145Z/.cache/brands/icon.png", uploaded_paths)

    def test_prune_versions_older_than_days_deletes_stale_snapshots(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            version_retention_count=7,
        )
        fake_client = MagicMock()
        fake_client.list_directory_contents.return_value = [
            {"type": "dir", "name": "20260601T120000Z"},
            {"type": "dir", "name": "20260707T120000Z"},
        ]
        with patch("sync.engine.GitHubClient", return_value=fake_client):
            engine = SyncEngine(config, previous_hash_index={})
            with patch.object(engine, "_delete_remote_tree") as delete_tree:
                engine.prune_versions_older_than_days(7)

        delete_tree.assert_called_once_with("versions/20260601T120000Z")

    def test_clean_remote_tree_deletes_root_content_but_keeps_versions(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            version_retention_count=7,
        )
        fake_client = MagicMock()
        fake_client.list_directory_contents.side_effect = [
            [
                {"type": "dir", "name": "versions", "path": "versions"},
                {"type": "dir", "name": "config", "path": "config"},
                {"type": "file", "name": "root.yaml", "path": "root.yaml", "sha": "rootsha"},
            ],
            [
                {"type": "file", "name": "nested.yaml", "path": "config/nested.yaml", "sha": "nestedsha"},
            ],
        ]

        with patch("sync.engine.GitHubClient", return_value=fake_client):
            engine = SyncEngine(config, previous_hash_index={})
            engine.clean_remote_tree()

        fake_client.delete_content.assert_any_call(
            path="config/nested.yaml",
            sha="nestedsha",
            message="sync: delete config/nested.yaml",
        )
        fake_client.delete_content.assert_any_call(
            path="root.yaml",
            sha="rootsha",
            message="sync: delete root.yaml",
        )

    def test_clean_remote_tree_rebuilds_repo_skeleton(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            version_retention_count=7,
        )
        fake_client = MagicMock()
        fake_client.list_directory_contents.side_effect = [
            [
                {"type": "dir", "name": "versions", "path": "versions"},
                {"type": "file", "name": "README.md", "path": "README.md", "sha": "readmesha"},
                {"type": "dir", "name": "custom_components", "path": "custom_components"},
                {"type": "dir", "name": "addons", "path": "addons"},
                {"type": "dir", "name": ".github", "path": ".github"},
                {"type": "file", "name": "root.yaml", "path": "root.yaml", "sha": "rootsha"},
            ],
            [
                {"type": "file", "name": "nested.yaml", "path": "custom_components/nested.yaml", "sha": "nestedsha"},
            ],
            [
                {"type": "file", "name": "addon.yaml", "path": "addons/addon.yaml", "sha": "addonsha"},
            ],
            [],
        ]

        with patch("sync.engine.GitHubClient", return_value=fake_client):
            engine = SyncEngine(config, previous_hash_index={})
            engine.clean_remote_tree()

        fake_client.delete_content.assert_any_call(
            path="root.yaml",
            sha="rootsha",
            message="sync: delete root.yaml",
        )
        restore_calls = [call.kwargs for call in fake_client.put_content.call_args_list if call.kwargs.get("message", "").startswith("sync: restore ")]
        self.assertTrue(any(call.get("path") == "README.md" for call in restore_calls))
        self.assertTrue(any(call.get("path") == "repository.yaml" for call in restore_calls))
        fake_client.delete_content.assert_any_call(
            path="README.md",
            sha="readmesha",
            message="sync: delete README.md",
        )


if __name__ == "__main__":
    unittest.main()
