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
from sync.github_client import _gate_wait, _open_rate_gate, reset_rate_limit_gate
from sync.hashing import MAX_SYNCABLE_BYTES
from sync.models import SyncConfig, SyncPlan


def _batch_client():
    """A GitHub client stand-in wired for the batched-commit path."""
    client = MagicMock()
    client.get_branch_head_sha.side_effect = ["headsha", "headsha2", "headsha3"]
    client.get_commit_tree_sha.return_value = "basetree"
    client.create_blob.side_effect = lambda content: f"blob{abs(hash(content)) % 10000}"
    client.create_git_tree.return_value = {"sha": "treesha"}
    client.create_git_commit.return_value = {"sha": "commitsha"}
    client.update_branch_ref.return_value = {"object": {"sha": "commitsha"}}
    return client


def _staged_entries(client) -> list:
    return client.create_git_tree.call_args.kwargs["tree"]


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
                # Flat layout: this test asserts config-root paths by name.
                repo_layout="flat",
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
                # Flat layout: this test asserts config-root paths by name.
                repo_layout="flat",
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
            # Flat layout: this test asserts config-root paths by name.
            repo_layout="flat",
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

            fake_client = _batch_client()

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                result = engine.run(plan)

            self.assertEqual(result.synced_count, 2)
            self.assertEqual(result.deleted_count, 2)
            # "missing.yaml" is not on disk, so it is never staged.
            self.assertEqual(result.skipped_count, 1)
            self.assertIn("Sync completed", result.message)
            self.assertEqual(fake_client.create_blob.call_count, 2)
            entries = _staged_entries(fake_client)
            self.assertEqual(
                sorted(e["path"] for e in entries),
                ["added.yaml", "changed.yaml", "removed.yaml", "unknown.yaml"],
            )
            # A whole run is one commit: one tree, one commit, one ref update.
            fake_client.create_git_tree.assert_called_once()
            fake_client.create_git_commit.assert_called_once()
            fake_client.update_branch_ref.assert_called_once()

    def test_run_live_retries_a_concurrent_push_without_force(self) -> None:
        """Someone else pushed mid-run: rebuild on the new head, do not clobber it.

        Per-file commits failed this with a 409 per file. The batched commit
        refuses a non-fast-forward ref update instead, so the other commit
        survives, and the retry reuses the blobs already uploaded.
        """
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

            fake_client = _batch_client()
            fake_client.update_branch_ref.side_effect = [
                SyncError('GitHub API error HTTP 422 for PATCH ref: {"status":"422"}'),
                {"object": {"sha": "newsha"}},
            ]

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                result = engine.run(plan)

            self.assertEqual(result.synced_count, 1)
            # The ref is never forced, or the concurrent push would be lost.
            self.assertEqual(fake_client.update_branch_ref.call_count, 2)
            for call in fake_client.update_branch_ref.call_args_list:
                self.assertFalse(call.kwargs.get("force", False))
            # The retry rebuilt the tree on a fresh head, re-uploading no blobs.
            self.assertEqual(fake_client.create_blob.call_count, 1)
            self.assertEqual(fake_client.get_branch_head_sha.call_count, 2)
            parents = [
                c.kwargs["parent_sha"] for c in fake_client.create_git_commit.call_args_list
            ]
            self.assertEqual(parents, ["headsha", "headsha2"])

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
            fake_client = _batch_client()
            calls = {"count": 0}

            def cancel_checker() -> bool:
                calls["count"] += 1
                return calls["count"] > 1

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                engine.set_cancel_checker(cancel_checker)
                result = engine.run(plan)

            self.assertTrue(result.cancelled)
            # One blob was staged before the cancel, and because the run is a
            # single commit nothing was written: a cancelled run leaves the
            # repository exactly as it was.
            self.assertEqual(fake_client.create_blob.call_count, 1)
            fake_client.create_git_commit.assert_not_called()
            fake_client.update_branch_ref.assert_not_called()

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
            fake_client = _batch_client()

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={})
                progress_events: list[dict[str, object]] = []
                engine.set_progress_callback(progress_events.append)
                engine.run(plan)

            actions = [event.get("current_action") for event in progress_events]
            # Each file is staged with its own path, then one commit is made.
            self.assertIn("staging", actions)
            self.assertIn("committing", actions)
            self.assertTrue(
                any(
                    event.get("current_action") == "staging"
                    and event.get("current_path") == "one.yaml"
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
            fake_client = _batch_client()
            fake_client.update_branch_ref.side_effect = SyncError(
                "Sync cancelled during GitHub rate-limit wait"
            )

            with patch("sync.engine.GitHubClient", return_value=fake_client):
                engine = SyncEngine(config, previous_hash_index={"stale.yaml": "h"})
                engine.set_cancel_checker(lambda: True)
                engine.set_progress_callback(lambda _payload: None)
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
                        # Flat layout: this test asserts config-root paths by name.
                        repo_layout="flat",
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
                # Flat layout: this test asserts config-root paths by name.
                repo_layout="flat",
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
            repo_layout=kwargs.pop("repo_layout", "flat"),
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
            # Flat layout: this test asserts config-root paths by name.
            repo_layout="flat",
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
                    # Flat layout: this test asserts config-root paths by name.
                    repo_layout="flat",
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


class OutOfScopeDeletionTests(unittest.TestCase):
    """Out of scope is not the same as deleted.

    The diff is "in the last scan but not this one", which cannot by itself
    tell a file removed from disk from a file the current selection no longer
    covers. Reading the second as a deletion removed files from a repository
    purely because the selection changed, so only genuinely absent paths are
    removed now.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self._tmp = tmp
        root = Path(tmp.name) / "config"
        self.root = root
        root.mkdir()
        (root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
        for name in ("template", "modbus", "mqtt"):
            (root / f"{name}.yaml").write_text(f"{name}:\n  - x\n", encoding="utf-8")
        (root / "esphome").mkdir()
        (root / "esphome" / "living.yaml").write_text("sensor:\n  - y\n", encoding="utf-8")
        # a real mount directory, so out-of-scope mount paths can be resolved
        self.addons = Path(tmp.name) / "addon_configs"
        (self.addons / "my_addon").mkdir(parents=True)
        (self.addons / "my_addon" / "config.yaml").write_text("key: value\n", encoding="utf-8")

    def _engine(self, mode, sync_paths, previous=None, **kwargs):
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            addon_config_root=str(self.addons),
            dry_run=True,
            sync_mode=mode,
            sync_paths=tuple(sync_paths),
            repo_layout=kwargs.pop("repo_layout", "flat"),
            **kwargs,
        )
        return SyncEngine(config, previous_hash_index=previous or {})

    def _previous_full_scan(self):
        """The index a completed sync of the whole config root leaves behind."""
        _, index = self._engine("override", ["."]).plan()
        return dict(index)

    def test_narrowing_selection_does_not_delete_out_of_scope_files(self):
        previous = self._previous_full_scan()
        self.assertTrue(previous, "expected a non-empty previous scan")
        plan, index = self._engine("override", ["esphome"], previous).plan()
        self.assertEqual(plan.removed, [])
        # still scanned and synced, just not re-added: it was in the last scan
        self.assertIn("esphome/living.yaml", index)

    def test_empty_selection_does_not_delete_anything_still_on_disk(self):
        previous = self._previous_full_scan()
        plan, _ = self._engine("override", [], previous).plan()
        self.assertEqual(plan.removed, [])

    def test_file_actually_deleted_from_disk_is_still_removed(self):
        previous = self._previous_full_scan()
        (self.root / "template.yaml").unlink()
        plan, _ = self._engine("override", ["."], previous).plan()
        self.assertEqual(plan.removed, ["template.yaml"])

    def test_out_of_scope_mount_file_still_on_disk_is_left_alone(self):
        previous = self._previous_full_scan()
        previous["addon_configs/my_addon/config.yaml"] = "digest"
        plan, _ = self._engine(
            "override", ["."], previous, include_addon_configs=False
        ).plan()
        self.assertEqual(plan.removed, [])

    def test_out_of_scope_mount_file_deleted_from_disk_is_removed(self):
        previous = self._previous_full_scan()
        previous["addon_configs/my_addon/config.yaml"] = "digest"
        (self.addons / "my_addon" / "config.yaml").unlink()
        plan, _ = self._engine(
            "override", ["."], previous, include_addon_configs=False
        ).plan()
        self.assertEqual(plan.removed, ["addon_configs/my_addon/config.yaml"])

    def test_clean_repo_still_deletes_out_of_scope_paths(self):
        """Clean Repo is an explicit destructive action, so it is unchanged."""
        previous = self._previous_full_scan()
        plan, _ = self._engine("override", ["esphome"], previous).plan()
        clean, _ = self._engine("override", ["esphome"], previous).clean_plan()
        self.assertEqual(plan.removed, [])
        self.assertTrue(clean.removed)

    def test_absolute_config_path_selects_the_config_root(self):
        engine = self._engine("override", ["/config"])
        self.assertEqual(engine._selections, (".",))
        self.assertTrue(engine._path_selected("template.yaml"))
        self.assertFalse(engine._path_selected("media/photo.jpg"))

    def test_absolute_mount_path_keeps_its_prefix(self):
        engine = self._engine("override", ["/media/photo.jpg"])
        self.assertTrue(engine._path_selected("media/photo.jpg"))
        self.assertFalse(engine._path_selected("photo.jpg"))

    def test_blank_selection_is_dropped_rather_than_becoming_the_root(self):
        engine = self._engine("override", ["", None])
        self.assertEqual(engine._selections, ())
        plan, index = engine.plan()
        self.assertEqual(plan.total_files, 0)
        self.assertEqual(index, {})

    def test_relative_folder_named_like_a_mount_is_untouched(self):
        """A "media" folder inside the config directory keeps meaning that folder."""
        (self.root / "media").mkdir()
        (self.root / "media" / "note.txt").write_text("hi\n", encoding="utf-8")
        engine = self._engine("override", ["media"])
        self.assertEqual(engine._selections, ("media",))
        self.assertTrue(engine._path_selected("media/note.txt"))


class OversizedFileTests(unittest.TestCase):
    """A file too large for GitHub is skipped, never attempted.

    GitHub answers a 422 for a file this size, and that error used to abort
    the entire run - so one archive another add-on had dropped into the config
    directory cost the user every other file in the sync.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "config"
        self.root = root
        root.mkdir()
        (root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
        # Sparse, so the fixture stays small on disk while the file is huge.
        with (root / "archive.tar.gz").open("wb") as handle:
            handle.truncate(MAX_SYNCABLE_BYTES + 1)

    def _engine(self, sync_paths=(".",), previous=None):
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            dry_run=True,
            sync_mode="override",
            sync_paths=tuple(sync_paths),
            # Flat layout: this test asserts config-root paths by name.
            repo_layout="flat",
        )
        return SyncEngine(config, previous_hash_index=previous or {})

    def test_oversized_file_is_skipped_and_reported(self):
        plan, index = self._engine().plan()
        self.assertEqual(plan.oversized, ["archive.tar.gz"])
        self.assertNotIn("archive.tar.gz", index)

    def test_oversized_file_does_not_sink_the_rest_of_the_run(self):
        plan, index = self._engine().plan()
        self.assertIn("configuration.yaml", index)
        self.assertEqual(plan.added, ["configuration.yaml"])
        self.assertEqual(plan.total_files, 1)

    def test_dry_run_message_names_the_skip(self):
        plan, _ = self._engine().plan()
        result = self._engine().run(plan)
        self.assertIn("too large for GitHub", result.message)
        self.assertEqual(result.skipped_count, 1)

    def test_oversized_file_already_in_the_repo_is_not_removed(self):
        previous = {"archive.tar.gz": "digest", "configuration.yaml": "digest"}
        plan, _ = self._engine(previous=previous).plan()
        self.assertEqual(plan.removed, [])

    def test_clean_repo_does_not_delete_an_oversized_file(self):
        """Deleting it would destroy the only copy - it cannot be re-uploaded."""
        previous = {"archive.tar.gz": "digest", "configuration.yaml": "digest"}
        plan, _ = self._engine(previous=previous).clean_plan()
        self.assertNotIn("archive.tar.gz", plan.removed)

    def test_clean_repo_still_deletes_files_that_really_are_gone(self):
        (self.root / "removed.yaml").write_text("x: 1\n", encoding="utf-8")
        previous = {"archive.tar.gz": "digest", "removed.yaml": "digest"}
        _, index = self._engine(previous=previous).plan()
        self.assertIn("removed.yaml", index)
        (self.root / "removed.yaml").unlink()
        plan, _ = self._engine(previous=previous).clean_plan()
        self.assertEqual(plan.removed, ["removed.yaml"])

    def test_out_of_scope_oversized_file_is_not_reported(self):
        plan, _ = self._engine(sync_paths=("configuration.yaml",)).plan()
        self.assertEqual(plan.oversized, [])

class RepoLayoutTests(unittest.TestCase):
    """The config directory sits under config/ rather than sharing the repo root.

    Flat layout put configuration.yaml and the add-on's own README.md in the
    same namespace, where one could overwrite the other. Prefixed keeps the
    mounts named as they always were and moves only the config root.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root = base / "config"
        (self.root / "blueprints").mkdir(parents=True)
        (self.root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
        (self.root / "blueprints" / "b.yaml").write_text("blueprint:\n", encoding="utf-8")
        self.addons = base / "addon_configs"
        (self.addons / "app").mkdir(parents=True)
        (self.addons / "app" / "config.yaml").write_text("k: v\n", encoding="utf-8")

    def _engine(self, layout, previous=None, sync_paths=(".", "addon_configs")):
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="t",
            config_root=str(self.root),
            addon_config_root=str(self.addons),
            dry_run=True,
            sync_mode="whitelist",
            sync_paths=tuple(sync_paths),
            repo_layout=layout,
            include_addon_configs=True,
            security_override_all_filters=True,
        )
        return SyncEngine(config, previous_hash_index=dict(previous or {}))

    def test_prefixed_is_the_default_layout(self) -> None:
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="t",
            config_root=str(self.root),
            dry_run=True,
        )
        self.assertEqual(config.repo_layout, "prefixed")

    def test_prefixed_puts_config_under_config_and_keeps_mount_names(self) -> None:
        _, index = self._engine("prefixed").plan()
        self.assertEqual(
            sorted(index),
            [
                "addon_configs/app/config.yaml",
                "config/blueprints/b.yaml",
                "config/configuration.yaml",
            ],
        )

    def test_flat_keeps_config_at_the_repository_root(self) -> None:
        _, index = self._engine("flat").plan()
        self.assertEqual(
            sorted(index),
            ["addon_configs/app/config.yaml", "blueprints/b.yaml", "configuration.yaml"],
        )

    def test_selecting_a_subfolder_of_the_config_root_still_works(self) -> None:
        """A partial pick narrows the config root without breaking the prefix."""
        _, index = self._engine("prefixed", sync_paths=("blueprints",)).plan()
        self.assertIn("config/blueprints/b.yaml", index)
        self.assertNotIn("config/configuration.yaml", index)

    def test_a_normal_sync_does_not_delete_root_files_it_cannot_see(self) -> None:
        """The point of the migration: switching layout alone moves nothing.

        The scanner only ever sees config/... keys once the prefix is on, so
        the old root paths look absent. The out-of-scope fix leaves them
        alone because they are still on disk.
        """
        previous = {"configuration.yaml": "old", "blueprints/b.yaml": "old"}
        plan, _ = self._engine("prefixed", previous=previous).plan()
        self.assertEqual(plan.removed, [])
        self.assertEqual(
            sorted(plan.added),
            [
                "addon_configs/app/config.yaml",
                "config/blueprints/b.yaml",
                "config/configuration.yaml",
            ],
        )

    def test_a_genuinely_deleted_file_is_still_removed_after_the_switch(self) -> None:
        previous = {"configuration.yaml": "old", "vanished.yaml": "old"}
        plan, _ = self._engine("prefixed", previous=previous).plan()
        self.assertEqual(plan.removed, ["vanished.yaml"])


class LayoutMigrationTests(unittest.TestCase):
    """The one deliberate exception: moving a flat repo onto config/."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root = base / "config"
        (self.root / "blueprints").mkdir(parents=True)
        (self.root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
        (self.root / "blueprints" / "b.yaml").write_text("blueprint:\n", encoding="utf-8")
        self.addons = base / "addon_configs"
        (self.addons / "app").mkdir(parents=True)
        (self.addons / "app" / "config.yaml").write_text("k: v\n", encoding="utf-8")
        self.flat_previous = {
            "configuration.yaml": "a",
            "blueprints/b.yaml": "b",
            "addon_configs/app/config.yaml": "c",
        }

    def _engine(self, previous, layout="prefixed"):
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="t",
            config_root=str(self.root),
            addon_config_root=str(self.addons),
            dry_run=True,
            sync_mode="whitelist",
            sync_paths=(".", "addon_configs"),
            repo_layout=layout,
            include_addon_configs=True,
            security_override_all_filters=True,
        )
        return SyncEngine(config, previous_hash_index=dict(previous))

    def test_migration_moves_config_files_and_leaves_mounts_alone(self) -> None:
        plan, _, held = self._engine(self.flat_previous).layout_migration()
        self.assertEqual(
            plan.added, ["config/blueprints/b.yaml", "config/configuration.yaml"]
        )
        self.assertEqual(plan.removed, ["blueprints/b.yaml", "configuration.yaml"])
        # The mount already has the right name, so it must not be touched.
        self.assertNotIn("addon_configs/app/config.yaml", plan.added + plan.removed)
        self.assertEqual(held, {"left_behind": [], "conflicts": []})

    def test_migration_on_an_already_migrated_repo_does_nothing(self) -> None:
        plan, _, held = self._engine(
            {"config/configuration.yaml": "a", "config/blueprints/b.yaml": "b"}
        ).layout_migration()
        self.assertEqual((plan.added, plan.removed), ([], []))
        self.assertEqual(held["conflicts"], [])

    def test_migration_refuses_when_the_destination_is_occupied(self) -> None:
        """Deleting the old path would destroy the only copy of the file."""
        plan, _, held = self._engine(
            {"configuration.yaml": "a", "config/configuration.yaml": "other"}
        ).layout_migration()
        self.assertEqual(held["conflicts"], ["configuration.yaml"])
        self.assertNotIn("configuration.yaml", plan.removed)
        self.assertNotIn("config/configuration.yaml", plan.added)

    def test_a_root_path_missing_from_disk_is_left_not_moved(self) -> None:
        plan, _, held = self._engine(
            dict(self.flat_previous, **{"vanished.yaml": "z"})
        ).layout_migration()
        self.assertEqual(held["left_behind"], ["vanished.yaml"])
        self.assertNotIn("vanished.yaml", plan.removed)

    def test_migration_is_refused_when_the_layout_is_already_flat(self) -> None:
        with self.assertRaises(SyncError) as caught:
            self._engine(self.flat_previous, layout="flat").layout_migration()
        self.assertIn("prefixed layout", str(caught.exception))

    def test_the_baseline_after_a_migration_produces_no_further_work(self) -> None:
        engine = self._engine(self.flat_previous)
        _, index, _ = engine.layout_migration()
        follow_up = SyncEngine(engine._config, previous_hash_index=index).plan()[0]  # pylint: disable=protected-access
        self.assertEqual((follow_up.added, follow_up.changed, follow_up.removed), ([], [], []))

class PrefixedParityTests(unittest.TestCase):
    """The rules that must hold in both layouts.

    The suites above assert config-root paths by name, so they are written
    against the flat layout. Prefixed is the new default, so the behaviour
    those tests protect is re-checked here with the prefix in place - a
    selection bug that only appears under config/ would otherwise ship
    uncaught.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root = base / "config"
        (self.root / "esphome").mkdir(parents=True)
        (self.root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
        (self.root / "esphome" / "living.yaml").write_text("sensor:\n", encoding="utf-8")
        self.addons = base / "addon_configs"
        (self.addons / "app").mkdir(parents=True)
        (self.addons / "app" / "config.yaml").write_text("k: v\n", encoding="utf-8")

    def _plan(self, mode, sync_paths=(), layout="prefixed", **kwargs):
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            addon_config_root=str(self.addons),
            dry_run=True,
            sync_mode=mode,
            sync_paths=tuple(sync_paths),
            repo_layout=layout,
            include_addon_configs=True,
            security_override_all_filters=True,
            **kwargs,
        )
        plan, _ = SyncEngine(config, previous_hash_index={}).plan()
        return set(plan.added)

    def test_blacklist_still_walks_the_config_root_under_the_prefix(self) -> None:
        keys = self._plan("blacklist")
        self.assertIn("config/configuration.yaml", keys)
        self.assertIn("config/esphome/living.yaml", keys)

    def test_whitelist_selection_is_scoped_under_the_prefix(self) -> None:
        keys = self._plan("whitelist", sync_paths=("esphome",))
        self.assertIn("config/esphome/living.yaml", keys)
        self.assertNotIn("config/configuration.yaml", keys)

    def test_a_mount_selection_does_not_pull_in_the_config_root(self) -> None:
        keys = self._plan("whitelist", sync_paths=("addon_configs",))
        self.assertEqual(keys, {"addon_configs/app/config.yaml"})

    def test_gitignore_still_applies_under_the_prefix(self) -> None:
        (self.root / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (self.root / "noisy.log").write_text("noise\n", encoding="utf-8")
        keys = self._plan("override", sync_paths=(".",))
        self.assertIn("config/configuration.yaml", keys)
        self.assertNotIn("config/noisy.log", keys)

    def test_an_oversized_file_is_skipped_under_the_prefix(self) -> None:
        with (self.root / "archive.tar.gz").open("wb") as handle:
            handle.truncate(MAX_SYNCABLE_BYTES + 1)
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            dry_run=True,
            sync_mode="override",
            sync_paths=(".",),
            repo_layout="prefixed",
        )
        plan, _ = SyncEngine(config, previous_hash_index={}).plan()
        self.assertEqual(plan.oversized, ["config/archive.tar.gz"])
        self.assertIn("config/configuration.yaml", plan.added)

    def test_the_runtime_floor_holds_under_the_prefix(self) -> None:
        (self.root / "home-assistant.log").write_text("log\n", encoding="utf-8")
        (self.root / ".storage").mkdir()
        (self.root / ".storage" / "core.config").write_text("{}", encoding="utf-8")
        keys = self._plan("override", sync_paths=(".",))
        self.assertNotIn("config/home-assistant.log", keys)
        self.assertFalse([k for k in keys if k.startswith("config/.storage/")])

    def test_both_layouts_select_the_same_files(self) -> None:
        """Only the prefix differs; what gets picked must not."""
        flat = self._plan("override", sync_paths=(".", "addon_configs"), layout="flat")
        prefixed = self._plan("override", sync_paths=(".", "addon_configs"), layout="prefixed")
        mounts = ("addon_configs/", "media/", "share/", "ssl/", "backups/", "www/")
        self.assertEqual(
            {k for k in flat if not k.startswith(mounts)},
            {k.removeprefix("config/") for k in prefixed if not k.startswith(mounts)},
        )
        self.assertEqual(
            {k for k in flat if k.startswith(mounts)},
            {k for k in prefixed if k.startswith(mounts)},
        )

class SingleCommitTests(unittest.TestCase):
    """A whole run is one commit, not one per file.

    Per-file commits cost three API calls a file, so a 224-file repository
    needed over 600 calls, tripped the rate limiter, and - if it failed partway
    - left the repository in a state that matched no plan the user had seen.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root = base / "config"
        (self.root / "blueprints").mkdir(parents=True)
        for name in ("a.yaml", "b.yaml", "c.yaml"):
            (self.root / name).write_text(name, encoding="utf-8")
        (self.root / "blueprints" / "d.yaml").write_text("d", encoding="utf-8")

    def _run(self, added, removed):
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            dry_run=False,
            sync_mode="whitelist",
            repo_layout="flat",
        )
        plan = SyncPlan(
            added=list(added), changed=[], removed=list(removed), total_files=4
        )
        client = _batch_client()
        with patch("sync.engine.GitHubClient", return_value=client):
            engine = SyncEngine(config, previous_hash_index={})
            return engine.run(plan), client

    def test_four_files_cost_four_blobs_and_three_committing_calls(self) -> None:
        result, client = self._run(
            ["a.yaml", "b.yaml", "c.yaml", "blueprints/d.yaml"], []
        )
        self.assertEqual(result.synced_count, 4)
        self.assertEqual(client.create_blob.call_count, 4)
        self.assertEqual(client.create_git_tree.call_count, 1)
        self.assertEqual(client.create_git_commit.call_count, 1)
        self.assertEqual(client.update_branch_ref.call_count, 1)
        # The old path called the contents API per file; nothing should.
        client.put_content.assert_not_called()
        client.delete_content.assert_not_called()

    def test_deletes_are_staged_in_the_same_commit(self) -> None:
        result, client = self._run(["a.yaml"], ["gone.yaml", "also-gone.yaml"])
        self.assertEqual(result.deleted_count, 2)
        self.assertEqual(client.create_git_commit.call_count, 1)
        entries = _staged_entries(client)
        deleted = [e for e in entries if e["sha"] is None]
        self.assertEqual(
            sorted(e["path"] for e in deleted), ["also-gone.yaml", "gone.yaml"]
        )

    def test_an_exec_bit_is_preserved(self) -> None:
        script = self.root / "hook.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o755)
        _, client = self._run(["hook.sh"], [])
        modes = {e["path"]: e["mode"] for e in _staged_entries(client)}
        self.assertEqual(modes["hook.sh"], "100755")

    def test_nothing_to_do_makes_no_commit_at_all(self) -> None:
        result, client = self._run([], [])
        self.assertEqual(result.synced_count, 0)
        client.create_git_tree.assert_not_called()
        client.create_git_commit.assert_not_called()
        client.update_branch_ref.assert_not_called()

    def test_the_commit_message_summarises_the_run(self) -> None:
        client = _batch_client()
        config = SyncConfig(
            repository="owner/repo",
            branch="main",
            token="token",
            config_root=str(self.root),
            dry_run=False,
            sync_mode="whitelist",
            repo_layout="flat",
        )
        plan = SyncPlan(added=["a.yaml", "b.yaml"], changed=[], removed=["old.yaml"], total_files=4)
        with patch("sync.engine.GitHubClient", return_value=client):
            SyncEngine(config, previous_hash_index={}).run(plan)
        message = client.create_git_commit.call_args.kwargs["message"]
        self.assertIn("update 2 files", message)
        self.assertIn("remove 1 file", message)


class RateGateLifecycleTests(unittest.TestCase):
    """A finished sync must not leave the shared rate-limit gate open.

    The gate is module-global and otherwise only clears as time passes, so a run
    that was cancelled or that gave up after the retry ceiling left it open. The
    next run - a manual one especially - then waited on a gate belonging to a
    sync that had already finished, reporting itself as running while doing
    nothing at all.
    """

    def setUp(self) -> None:
        reset_rate_limit_gate()
        self.addCleanup(reset_rate_limit_gate)

    def _engine(self, root: Path) -> SyncEngine:
        return SyncEngine(
            SyncConfig(
                repository="owner/repo",
                branch="main",
                token="token",
                config_root=str(root),
                dry_run=False,
                sync_mode="whitelist",
                repo_layout="flat",
            ),
            previous_hash_index={},
        )

    def test_a_completed_sync_leaves_no_gate_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.yaml").write_text("a", encoding="utf-8")
            _open_rate_gate(3600.0, reason="test")
            self.assertGreater(_gate_wait(), 0.0)

            with patch("sync.engine.GitHubClient", return_value=_batch_client()):
                self._engine(root).run(SyncPlan(added=["a.yaml"], changed=[], removed=[], total_files=1))

            self.assertEqual(_gate_wait(), 0.0)

    def test_a_failed_sync_also_leaves_no_gate_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.yaml").write_text("a", encoding="utf-8")
            _open_rate_gate(3600.0, reason="test")

            client = _batch_client()
            client.create_git_tree.side_effect = SyncError("boom")
            with patch("sync.engine.GitHubClient", return_value=client):
                with self.assertRaises(SyncError):
                    self._engine(root).run(SyncPlan(added=["a.yaml"], changed=[], removed=[], total_files=1))

            self.assertEqual(_gate_wait(), 0.0)

    def test_a_sync_says_what_it_is_doing_and_how_it_ended(self) -> None:
        """A sync that starts, runs and finishes has to be visible in the log."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.yaml").write_text("a", encoding="utf-8")
            with patch("sync.engine.GitHubClient", return_value=_batch_client()):
                with self.assertLogs("sync.engine", level="INFO") as captured:
                    self._engine(root).run(SyncPlan(added=["a.yaml"], changed=[], removed=[], total_files=1))

        text = "\n".join(captured.output)
        self.assertIn("Sync starting", text)
        self.assertIn("owner/repo", text)
        self.assertIn("Sync finished", text)
        self.assertIn("Upserted 1", text)

    def test_a_failure_is_logged_with_its_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.yaml").write_text("a", encoding="utf-8")
            client = _batch_client()
            client.create_git_tree.side_effect = SyncError("tree refused")
            with patch("sync.engine.GitHubClient", return_value=client):
                with self.assertLogs("sync.engine", level="ERROR") as captured:
                    with self.assertRaises(SyncError):
                        self._engine(root).run(SyncPlan(added=["a.yaml"], changed=[], removed=[], total_files=1))

        text = "\n".join(captured.output)
        self.assertIn("Sync failed", text)
        self.assertIn("tree refused", text)


if __name__ == "__main__":
    unittest.main()
