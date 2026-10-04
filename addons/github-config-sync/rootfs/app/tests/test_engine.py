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
from sync.errors import SyncError
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
                include_addon_configs=True,
                sync_paths=(".",),
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

    def test_backups_root_scans_the_backup_mount(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root="/config",
            dry_run=True,
            include_backups=True,
        )
        engine = SyncEngine(config, previous_hash_index={})
        self.assertIn(("backups", Path("/backup")), engine._root_map)
        with patch.object(Path, "exists", return_value=True):
            self.assertEqual(
                engine._local_path_for("backups/snapshot.tar"),
                Path("/backup/snapshot.tar"),
            )

    def test_whitelist_mode_filters_roots_by_toggles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=tmp,
                dry_run=True,
                sync_mode="whitelist",
            )
            engine = SyncEngine(config, previous_hash_index={})
            self.assertEqual(engine._root_map, [("", Path(tmp))])

    def test_whitelist_mode_respects_explicitly_enabled_roots(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root="/config",
            dry_run=True,
            sync_mode="whitelist",
            include_media=True,
            include_ssl=True,
        )
        engine = SyncEngine(config, previous_hash_index={})
        roots = dict(engine._root_map)
        self.assertEqual(roots["media"], Path("/media"))
        self.assertEqual(roots["ssl"], Path("/ssl"))
        self.assertNotIn("backups", roots)
        self.assertNotIn("share", roots)

    def test_blacklist_mode_syncs_all_roots_regardless_of_toggles(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root="/config",
            dry_run=True,
            sync_mode="blacklist",
        )
        engine = SyncEngine(config, previous_hash_index={})
        self.assertEqual(
            [label for label, _ in engine._root_map],
            ["", "addon_configs", "media", "share", "ssl", "backups"],
        )

    def test_run_dry_run_returns_counts_without_github_calls(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=True,
            include_addon_configs=True,
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
                include_addon_configs=True,
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
                include_addon_configs=True,
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
                include_addon_configs=True,
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

    def test_run_live_reports_progress_events(self) -> None:
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
                include_addon_configs=True,
            )
            plan = SyncPlan(added=["one.yaml"], changed=[], removed=[], total_files=1)
            fake_client = MagicMock()
            fake_client.get_content.return_value = None

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                progress_events: list[dict[str, object]] = []
                engine.set_progress_callback(progress_events.append)
                engine.run(plan)

            self.assertTrue(
                any(
                    event.get("current_action") == "upserting"
                    and event.get("current_path") == ""
                    for event in progress_events
                )
            )

    def test_run_returns_cancelled_when_rate_limit_wait_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=tmp,
                addon_config_root="/addon_configs",
                dry_run=False,
            )
            plan = SyncPlan(added=[], changed=[], removed=["stale.yaml"], total_files=1)
            fake_client = MagicMock()

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={"stale.yaml": "h"})
                engine.set_cancel_checker(lambda: True)
                engine.set_progress_callback(lambda _payload: None)
                with patch.object(
                    engine,
                    "_delete_one",
                    side_effect=SyncError("Sync cancelled during GitHub rate-limit wait"),
                ):
                    result = engine.run(plan)

            self.assertTrue(result.cancelled)
            self.assertEqual(result.deleted_count, 0)
            self.assertIn("Sync cancelled", result.message)

    def test_delete_remote_tree_wipes_nested_tree(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            include_addon_configs=True,
        )
        fake_client = MagicMock()
        fake_client.list_directory_contents.side_effect = [
            [
                {"type": "dir", "name": "config", "path": "config"},
                {"type": "file", "name": "root.yaml", "path": "root.yaml", "sha": "rootsha"},
            ],
            [
                {"type": "file", "name": "nested.yaml", "path": "config/nested.yaml", "sha": "nestedsha"},
            ],
        ]
        fake_client.get_content.side_effect = [{"sha": "nestedsha"}, {"sha": "rootsha"}]

        with patch("sync.engine.GitHubClient", return_value=fake_client):
            engine = SyncEngine(config, previous_hash_index={})
            engine._delete_remote_tree("")

        fake_client.list_directory_contents.assert_any_call("")
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

    def test_clean_remote_tree_uses_atomic_empty_tree_commit(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            include_addon_configs=True,
        )
        fake_client = MagicMock()
        fake_client.get_branch_head_sha.return_value = "headsha"
        fake_client.create_git_tree.return_value = {"sha": "treesha"}
        fake_client.create_git_commit.return_value = {"sha": "commitsha"}

        with patch("sync.engine.GitHubClient", return_value=fake_client):
            engine = SyncEngine(config, previous_hash_index={})
            engine.clean_remote_tree()

        fake_client.get_branch_head_sha.assert_called_once()
        fake_client.create_git_tree.assert_called_once_with(tree=[])
        fake_client.create_git_commit.assert_called_once_with(
            message="sync: reset repository",
            tree_sha="treesha",
            parent_sha="headsha",
        )
        fake_client.update_branch_ref.assert_called_once_with("commitsha")
        fake_client.delete_content.assert_not_called()

    def test_nuke_remote_tree_resets_history_with_orphan_commit(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            include_addon_configs=True,
        )
        fake_client = MagicMock()
        fake_client.create_git_tree.return_value = {"sha": "treesha"}
        fake_client.create_git_commit.return_value = {"sha": "commitsha"}

        with patch("sync.engine.GitHubClient", return_value=fake_client):
            engine = SyncEngine(config, previous_hash_index={})
            engine.nuke_remote_tree(reset_history=True)

        fake_client.get_branch_head_sha.assert_not_called()
        fake_client.create_git_tree.assert_called_once_with(tree=[])
        fake_client.create_git_commit.assert_called_once_with(
            message="sync: reset repository",
            tree_sha="treesha",
            parent_sha=None,
        )
        fake_client.update_branch_ref.assert_called_once_with("commitsha")
        fake_client.delete_content.assert_not_called()

    def test_delete_all_releases_and_tags(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            include_addon_configs=True,
        )
        fake_client = MagicMock()
        fake_client.list_all_releases.return_value = [
            {"id": 101, "tag_name": "sync-21-09-26-03-00-00"},
            {"id": 102, "tag_name": "v1.0.0"},
            {"id": "not-an-int", "tag_name": "v2.0.0"},
        ]
        fake_client.list_tags.return_value = [
            {"name": "v3.0.0"},
            {"ref": "refs/tags/sync-22-09-26-03-00-00"},
            {"node_id": "nope"},
        ]

        with patch("sync.engine.GitHubClient", return_value=fake_client):
            engine = SyncEngine(config, previous_hash_index={})
            engine.delete_all_releases_and_tags()

        self.assertEqual(fake_client.delete_release.call_count, 2)
        for release_id in (101, 102):
            fake_client.delete_release.assert_any_call(release_id)
        for tag in ("sync-21-09-26-03-00-00", "v1.0.0", "sync-22-09-26-03-00-00"):
            fake_client.delete_tag.assert_any_call(tag)

    def test_run_refuses_to_delete_when_local_scan_is_empty(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            include_addon_configs=True,
        )
        fake_client = MagicMock()
        plan = SyncPlan(added=[], changed=[], removed=["config.yaml", "secrets.yaml"], total_files=0)

        with patch("sync.engine.GitHubClient", return_value=fake_client):
            engine = SyncEngine(config, previous_hash_index={})
            with self.assertRaises(Exception) as ctx:
                engine.run(plan)

        self.assertIn("local scan found no files", str(ctx.exception))
        fake_client.put_content.assert_not_called()
        fake_client.delete_content.assert_not_called()

    def test_restore_repo_skeleton_uses_app_root_assets(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=".",
            addon_config_root="/addon_configs",
            dry_run=False,
            include_addon_configs=True,
        )
        fake_client = MagicMock()
        fake_client.list_directory_contents.return_value = []

        with patch("sync.engine.GitHubClient", return_value=fake_client), patch("sync.engine.Path.exists", return_value=True), patch(
            "sync.engine.Path.read_bytes", return_value=b"content"
        ):
            engine = SyncEngine(config, previous_hash_index={})
            engine.restore_repo_skeleton()

        self.assertTrue(fake_client.put_content.called)


    def test_plan_www_files_under_config_root_resolve_without_escaping_sync_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            www_file = root / "www" / "community" / "Drag-And-Drop-Card" / "drag-and-drop-card.js.gz"
            www_file.parent.mkdir(parents=True)
            www_file.write_bytes(b"\x1f\x8b" * 10)
            (root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")

            for include_www in (False, True):
                with self.subTest(include_www=include_www):
                    config = SyncConfig(
                        repository="owner/repo",
                        branch="main",
                        token="token",
                        config_root=str(root),
                        addon_config_root="/addon_configs",
                        dry_run=False,
                        include_www=include_www,
                        sync_paths=(".",),
                    )
                    engine = SyncEngine(config, previous_hash_index={})
                    plan, _ = engine.plan()

                    www_paths = [p for p in plan.added if p.startswith("www/")]
                    self.assertEqual(
                        www_paths,
                        ["www/community/Drag-And-Drop-Card/drag-and-drop-card.js.gz"],
                    )
                    for relative in www_paths:
                        local = engine._local_path_for(relative)
                        self.assertTrue(local.exists())

    def test_run_live_uploads_www_files_from_config_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            www_file = root / "www" / "community" / "card.js.gz"
            www_file.parent.mkdir(parents=True)
            www_file.write_bytes(b"data")
            (root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")

            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                addon_config_root="/addon_configs",
                dry_run=False,
                include_www=False,
            )
            plan = SyncPlan(
                added=[p for p, _ in _seed_index(config).items()],
                changed=[],
                removed=[],
                total_files=0,
            )
            fake_client = MagicMock()
            fake_client.get_content.return_value = None

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                result = engine.run(plan)

            self.assertIn("Sync completed", result.message)
            self.assertEqual(fake_client.put_content.call_count, len(plan.added))
            self.assertEqual(fake_client.delete_content.call_count, 0)

    def test_plan_honors_gitignore_patterns_from_config_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            www_file = root / "www" / "community" / "Drag-And-Drop-Card" / "drag-and-drop-card.js.gz"
            www_file.parent.mkdir(parents=True)
            www_file.write_bytes(b"data")
            (root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            (root / ".gitignore").write_text(
                "# --- HACS FRONTEND DOWNLOADS ---\nwww/community/\n", encoding="utf-8"
            )

            config = SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                addon_config_root="/addon_configs",
                dry_run=False,
                include_www=True,
                sync_paths=(".",),
            )
            engine = SyncEngine(config, previous_hash_index={})
            plan, _ = engine.plan()

            self.assertEqual(sorted(plan.added), [".gitignore", "configuration.yaml"])
            self.assertNotIn("www/community/Drag-And-Drop-Card/drag-and-drop-card.js.gz", plan.added)


class SyncSelectionModesTests(unittest.TestCase):
    """The three modes differ on two axes: how much you pick, and whether the
    security checks stand between you and it.

    Selection is never enough on its own to release a credential file - that
    needs Override - and no mode can reach the runtime floor or the .gitignore.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self._tmp = tmp
        root = Path(tmp.name) / "config"
        self.root = root
        root.mkdir()
        (root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
        (root / "secrets.yaml").write_text("token: abc123\n", encoding="utf-8")
        (root / "home-assistant_v2.db").write_bytes(b"sqlite")
        (root / "local_only.yaml").write_text("x: 1\n", encoding="utf-8")
        (root / ".gitignore").write_text("local_only.yaml\n", encoding="utf-8")
        (root / "esphome").mkdir()
        (root / "esphome" / "kitchen.yaml").write_text('wifi:\n  password: "x"\n', encoding="utf-8")
        (root / "blueprints").mkdir()
        (root / "blueprints" / "motion.yaml").write_text("id: a\n", encoding="utf-8")

    def _plan(self, mode: str, sync_paths=(), **kwargs) -> set[str]:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            addon_config_root=str(Path(self._tmp.name) / "no_such_addon_root"),
            dry_run=True,
            sync_mode=mode,
            sync_paths=tuple(sync_paths),
            **kwargs,
        )
        engine = SyncEngine(config, previous_hash_index={})
        plan, _ = engine.plan()
        return set(plan.added)

    def test_whitelist_with_nothing_selected_syncs_nothing(self) -> None:
        self.assertEqual(self._plan("whitelist"), set())

    def test_override_with_nothing_selected_syncs_nothing(self) -> None:
        """An empty selection must never quietly become everything-unfiltered."""
        self.assertEqual(self._plan("override"), set())

    def test_whitelist_selects_the_config_root(self) -> None:
        added = self._plan("whitelist", sync_paths=(".",))
        self.assertIn("configuration.yaml", added)
        self.assertIn("blueprints/motion.yaml", added)

    def test_whitelist_keeps_the_security_checks(self) -> None:
        added = self._plan("whitelist", sync_paths=(".",))
        self.assertNotIn("secrets.yaml", added)
        self.assertNotIn("esphome/kitchen.yaml", added)  # dropped on content

    def test_override_releases_credentials_but_not_the_floor(self) -> None:
        added = self._plan("override", sync_paths=(".",))
        self.assertIn("secrets.yaml", added)
        self.assertIn("esphome/kitchen.yaml", added)
        self.assertNotIn("home-assistant_v2.db", added)
        self.assertNotIn("local_only.yaml", added)

    def test_blacklist_walks_the_defaults_and_filters(self) -> None:
        added = self._plan("blacklist")
        self.assertIn("configuration.yaml", added)
        self.assertNotIn("secrets.yaml", added)
        self.assertNotIn("esphome/kitchen.yaml", added)
        self.assertNotIn("home-assistant_v2.db", added)
        self.assertNotIn("local_only.yaml", added)

    def test_subdirectory_selection_is_scoped(self) -> None:
        added = self._plan("whitelist", sync_paths=("blueprints",))
        self.assertIn("blueprints/motion.yaml", added)
        self.assertNotIn("configuration.yaml", added)

    def test_glob_selection_is_accepted(self) -> None:
        added = self._plan("whitelist", sync_paths=("blueprints/*.yaml",))
        self.assertIn("blueprints/motion.yaml", added)

    def test_selected_runtime_artifact_is_still_refused(self) -> None:
        for mode in ("whitelist", "override", "blacklist"):
            with self.subTest(mode=mode):
                added = self._plan(mode, sync_paths=(".", "home-assistant_v2.db"))
                self.assertNotIn("home-assistant_v2.db", added)

    def test_ticked_mount_becomes_a_selection(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            dry_run=True,
            sync_mode="whitelist",
            include_media=True,
        )
        engine = SyncEngine(config, previous_hash_index={})
        labels = [label for label, _ in engine._root_map]

        walked = [label for label, _ in engine._walkable_roots()]

        self.assertIn("media", engine._selections)
        self.assertIn("media", walked)
        self.assertIn("", labels)  # still the base every path resolves against
        # Nothing was picked inside /config, so it is not walked - hashing it
        # only to discard every digest would be wasted work.
        self.assertNotIn("", walked)

    def test_config_root_is_walked_when_anything_inside_it_is_selected(self) -> None:
        for selection in (".", "esphome", "www"):
            with self.subTest(selection=selection):
                config = SyncConfig(
                    repository="owner/repo",
                    branch="main",
                    token="token",
                    config_root=str(self.root),
                    dry_run=True,
                    sync_mode="whitelist",
                    sync_paths=(selection,),
                )
                engine = SyncEngine(config, previous_hash_index={})
                walked = [label for label, _ in engine._walkable_roots()]
                self.assertIn("", walked, f"{selection} lives inside /config")
                self.assertNotIn("media", walked)

    def test_mount_only_selection_does_not_walk_the_config_root(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            dry_run=True,
            sync_mode="override",
            sync_paths=("media/photos",),
        )
        engine = SyncEngine(config, previous_hash_index={})

        self.assertEqual([label for label, _ in engine._walkable_roots()], ["media"])

    def test_mount_root_is_walked_for_a_granular_selection(self) -> None:
        """Selecting media/photos must still walk /media, even though the whole
        mount was never ticked - otherwise the pick is silently dropped."""
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            dry_run=True,
            sync_mode="whitelist",
            sync_paths=("media/photos",),
        )
        engine = SyncEngine(config, previous_hash_index={})
        labels = [label for label, _ in engine._root_map]

        self.assertIn("media", labels)
        self.assertNotIn("share", labels)
        self.assertTrue(engine._mount_has_selection("media"))
        self.assertFalse(engine._mount_has_selection("share"))

    def test_whole_mount_selection_comes_from_the_tick_box(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            dry_run=True,
            sync_mode="whitelist",
            include_media=True,
        )
        engine = SyncEngine(config, previous_hash_index={})
        self.assertIn("media", engine._selections)
        self.assertIn("media", [label for label, _ in engine._root_map])

    def test_www_is_not_a_separate_root(self) -> None:
        """www lives under /config, so it used to be walked twice."""
        (self.root / "www").mkdir()
        (self.root / "www" / "dash.yaml").write_text("x: 1\n", encoding="utf-8")
        added = self._plan("blacklist")
        self.assertEqual(
            sorted(p for p in added if p.startswith("www/")),
            ["www/dash.yaml"],
        )


def _seed_index(config: SyncConfig) -> dict[str, str]:
    """Return a plausible index for a temp config root so live runs have content."""
    engine = SyncEngine(config, previous_hash_index={})
    plan, index = engine.plan()
    return {p: index[p] for p in plan.added}


if __name__ == "__main__":
    unittest.main()
