from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
import importlib.util

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sync.hashing import build_hash_index, diff_hash_indexes

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

    def test_default_ignore_patterns_cover_common_home_assistant_files(self) -> None:
        self.assertIn("secrets.yaml", DEFAULT_IGNORE_PATTERNS)
        self.assertIn("ip_bans.yaml", DEFAULT_IGNORE_PATTERNS)
        self.assertIn("known_devices.yaml", DEFAULT_IGNORE_PATTERNS)
        self.assertIn(".storage/", DEFAULT_IGNORE_PATTERNS)
        self.assertIn(".cloud/", DEFAULT_IGNORE_PATTERNS)

    def test_diff_hash_indexes_returns_expected_added_changed_removed(self) -> None:
        previous = {"a.yaml": "1", "b.yaml": "2"}
        current = {"b.yaml": "3", "c.yaml": "4"}

        added, changed, removed = diff_hash_indexes(previous, current)

        self.assertEqual(added, ["c.yaml"])
        self.assertEqual(changed, ["b.yaml"])
        self.assertEqual(removed, ["a.yaml"])


if __name__ == "__main__":
    unittest.main()
