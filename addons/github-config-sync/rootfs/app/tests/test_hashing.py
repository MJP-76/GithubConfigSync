from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
import importlib.util

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sync.hashing import GitIgnoreMatcher, build_hash_index, diff_hash_indexes, _is_file_sensitive, scan_sensitive_files, is_ignored, IGNORE_DIRS, IGNORE_PATTERNS

CONST_PATH = Path(__file__).resolve().parents[5] / "custom_components/github_config_sync/const.py"
CONST_SPEC = importlib.util.spec_from_file_location("github_config_sync_const", CONST_PATH)
if CONST_SPEC is None or CONST_SPEC.loader is None:
    raise unittest.SkipTest("Could not load const module")
_const = importlib.util.module_from_spec(CONST_SPEC)
CONST_SPEC.loader.exec_module(_const)
DEFAULT_IGNORE_PATTERNS = _const.DEFAULT_IGNORE_PATTERNS


class HashingTests(unittest.TestCase):
    def test_build_hash_index_ignores_runtime_and_cache_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "automations.yaml").write_text("id: a", encoding="utf-8")
            (root / "appdaemon").mkdir()
            (root / "appdaemon" / "apps").mkdir(parents=True)
            (root / "appdaemon" / "appdaemon.yaml").write_text("secrets: true", encoding="utf-8")
            (root / "appdaemon" / "apps" / "lights.yaml").write_text("app: demo", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "x.pyc").write_bytes(b"pyc")
            (root / ".storage").mkdir()
            (root / ".storage" / "core.config_entries").write_text("{}", encoding="utf-8")
            (root / ".cache").mkdir()
            (root / ".cache" / "brands").mkdir(parents=True)
            (root / ".cache" / "brands" / "icon.png").write_bytes(b"png")
            (root / "home-assistant.log").write_text("log", encoding="utf-8")

            index = build_hash_index(root)

            self.assertIn("automations.yaml", index)
            self.assertIn("appdaemon/appdaemon.yaml", index)
            self.assertIn("appdaemon/apps/lights.yaml", index)
            self.assertNotIn("__pycache__/x.pyc", index)
            self.assertNotIn(".storage/core.config_entries", index)
            self.assertNotIn(".cache/brands/icon.png", index)
            self.assertNotIn("home-assistant.log", index)

    def test_build_hash_index_ignores_sensitive_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "secrets.yaml").write_text("token: hidden", encoding="utf-8")
            (root / "my-secret-notes.yaml").write_text("token: hidden", encoding="utf-8")
            (root / ".storage").mkdir()
            (root / ".storage" / "core.config").write_text("{}", encoding="utf-8")

            index = build_hash_index(root)

            self.assertNotIn("secrets.yaml", index)
            self.assertNotIn("my-secret-notes.yaml", index)
            self.assertNotIn(".storage/core.config", index)

    def test_build_hash_index_ignores_sensitive_name_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "password.txt").write_text("hello", encoding="utf-8")
            (root / "api_key.yaml").write_text("key: 123", encoding="utf-8")
            (root / "oauth_token.json").write_text("token: abc", encoding="utf-8")
            (root / "safe.yaml").write_text("value: 1", encoding="utf-8")

            index = build_hash_index(root)

            self.assertNotIn("password.txt", index)
            self.assertNotIn("api_key.yaml", index)
            self.assertNotIn("oauth_token.json", index)
            self.assertIn("safe.yaml", index)

    def test_build_hash_index_ignores_sensitive_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.yaml").write_text("bearer ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890abcdefghijklmnopqrstuvwxyz", encoding="utf-8")
            (root / "safe.yaml").write_text("value: 1", encoding="utf-8")

            index = build_hash_index(root)

            self.assertNotIn("config.yaml", index)
            self.assertIn("safe.yaml", index)

    def test_is_file_sensitive_checks_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sensitive = root / "config.yaml"
            sensitive.write_text("password=secret123", encoding="utf-8")
            safe = root / "safe.yaml"
            safe.write_text("value: 1", encoding="utf-8")

            self.assertTrue(_is_file_sensitive(root, sensitive))
            self.assertFalse(_is_file_sensitive(root, safe))

    def test_ignore_patterns_match_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "HOME-ASSISTANT.LOG").write_text("log", encoding="utf-8")
            (root / "Database.DB").write_bytes(b"data")
            (root / "safe.yaml").write_text("value: 1", encoding="utf-8")

            index = build_hash_index(root)

            self.assertNotIn("HOME-ASSISTANT.LOG", index)
            self.assertNotIn("Database.DB", index)
            self.assertIn("safe.yaml", index)

    def test_scan_sensitive_files_skips_hard_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "big.db").write_text("password=secret123", encoding="utf-8")
            (root / "token.txt").write_text("abc", encoding="utf-8")
            (root / "safe.yaml").write_text("value: 1", encoding="utf-8")

            flagged = scan_sensitive_files(root)

            self.assertNotIn("big.db", flagged)
            self.assertIn("token.txt", flagged)
            self.assertNotIn("safe.yaml", flagged)

    def test_scan_sensitive_files_bounds_content_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "notes.txt"
            path.write_text("a" * (2 * 1024 * 1024) + "bearer ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", encoding="utf-8")

            flagged = scan_sensitive_files(root)

            self.assertEqual(flagged, [])

    def test_default_ignore_patterns_cover_common_home_assistant_files(self) -> None:
        self.assertIn("secrets.yaml", DEFAULT_IGNORE_PATTERNS)
        self.assertIn("ip_bans.yaml", DEFAULT_IGNORE_PATTERNS)
        self.assertIn("known_devices.yaml", DEFAULT_IGNORE_PATTERNS)
        self.assertIn(".storage/", DEFAULT_IGNORE_PATTERNS)
        self.assertIn(".cloud/", DEFAULT_IGNORE_PATTERNS)
        self.assertIn(".ruff.toml", DEFAULT_IGNORE_PATTERNS)
        self.assertIn("core.config_entries", DEFAULT_IGNORE_PATTERNS)
        self.assertIn(".env", DEFAULT_IGNORE_PATTERNS)

    def test_key_and_certificate_material_is_hard_ignored(self) -> None:
        for path in (
            "ssl/cert.pem",
            "ssl/privkey.key",
            "certs/chain.crt",
            "certs/fullchain.p12",
            "server.der",
            "id_rsa",
            "id_ed25519",
            "backup/authorized.pub",
        ):
            self.assertTrue(is_ignored(path), f"{path} should be ignored")
        self.assertFalse(is_ignored("configuration.yaml"))
        self.assertFalse(is_ignored("automations.yaml"))

    def test_key_and_certificate_files_never_enter_hash_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            (root / "cert.pem").write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
            (root / "privkey.key").write_text("PRIVATE KEY", encoding="utf-8")
            (root / "chain.crt").write_text("CERT", encoding="utf-8")
            (root / "id_ed25519").write_text("KEY", encoding="utf-8")
            (root / "server.pub").write_text("PUB", encoding="utf-8")
            (root / ".ssh").mkdir()
            (root / ".ssh" / "authorized_keys").write_text("ssh-rsa AAAA", encoding="utf-8")

            index = build_hash_index(root)

            self.assertEqual(list(index.keys()), ["configuration.yaml"])

    def test_ignore_dirs_have_no_option_key_leftovers(self) -> None:
        self.assertNotIn("include_ssl", IGNORE_DIRS)
        self.assertNotIn("include_addon_configs", IGNORE_DIRS)
        self.assertIn(".ssh", IGNORE_DIRS)
        self.assertIn("*.pem", IGNORE_PATTERNS)
        self.assertIn("*.key", IGNORE_PATTERNS)
        self.assertIn("*.crt", IGNORE_PATTERNS)

    def test_diff_hash_indexes_returns_expected_added_changed_removed(self) -> None:
        previous = {"a.yaml": "1", "b.yaml": "2"}
        current = {"b.yaml": "3", "c.yaml": "4"}

        added, changed, removed = diff_hash_indexes(previous, current)

        self.assertEqual(added, ["c.yaml"])
        self.assertEqual(changed, ["b.yaml"])
        self.assertEqual(removed, ["a.yaml"])

    def test_gitignore_matcher_directory_pattern_ignores_subtree(self) -> None:
        matcher = GitIgnoreMatcher()
        matcher.add_text("www/community/\n")

        self.assertTrue(matcher.match("www/community/Drag-And-Drop-Card/drag-and-drop-card.js.gz"))
        self.assertTrue(matcher.match("www/community/x.js"))
        self.assertFalse(matcher.match("www/other/file.js"))
        self.assertFalse(matcher.match("configuration.yaml"))

    def test_gitignore_matcher_basename_and_negation_rules(self) -> None:
        matcher = GitIgnoreMatcher()
        matcher.add_text("*.log\n!keep.log\n")

        self.assertTrue(matcher.match("error.log"))
        self.assertTrue(matcher.match("logs/error.log"))
        self.assertFalse(matcher.match("keep.log"))
        self.assertFalse(matcher.match("logs/keep.log"))

    def test_gitignore_matcher_anchored_file_pattern_and_last_rule_wins(self) -> None:
        matcher = GitIgnoreMatcher()
        matcher.add_text("config/settings\nsecrets.yaml\n!config/settings\n")

        self.assertFalse(matcher.match("config/settings"))
        self.assertFalse(matcher.match("other/config/settings"))
        self.assertTrue(matcher.match("secrets.yaml"))
        self.assertTrue(matcher.match("nested/secrets.yaml"))
        self.assertTrue(matcher.match("config/secrets.yaml"))

    def test_gitignore_matcher_ignores_comments_and_honors_case(self) -> None:
        matcher = GitIgnoreMatcher()
        matcher.add_text("# comment only\nSecrets.YAML\n")

        self.assertTrue(matcher.match("Secrets.YAML"))
        self.assertFalse(matcher.match("secrets.yaml"))

    def test_gitignore_matcher_empty_or_missing_file_matches_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            matcher = GitIgnoreMatcher.from_file(Path(tmp) / ".gitignore")
            self.assertFalse(matcher.has_rules)
            self.assertFalse(matcher.match("anything.txt"))
        empty = GitIgnoreMatcher()
        empty.add_text("   \n# just a comment\n")
        self.assertFalse(empty.has_rules)


if __name__ == "__main__":
    unittest.main()
