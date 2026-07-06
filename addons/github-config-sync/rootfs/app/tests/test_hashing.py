from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sync.hashing import build_hash_index, diff_hash_indexes


class HashingTests(unittest.TestCase):
    def test_build_hash_index_ignores_runtime_and_cache_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "automations.yaml").write_text("id: a", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "x.pyc").write_bytes(b"pyc")
            (root / ".storage").mkdir()
            (root / ".storage" / "core.config_entries").write_text("{}", encoding="utf-8")
            (root / "home-assistant.log").write_text("log", encoding="utf-8")

            index = build_hash_index(root)

            self.assertIn("automations.yaml", index)
            self.assertNotIn("__pycache__/x.pyc", index)
            self.assertNotIn(".storage/core.config_entries", index)
            self.assertNotIn("home-assistant.log", index)

    def test_diff_hash_indexes_returns_expected_added_changed_removed(self) -> None:
        previous = {"a.yaml": "1", "b.yaml": "2"}
        current = {"b.yaml": "3", "c.yaml": "4"}

        added, changed, removed = diff_hash_indexes(previous, current)

        self.assertEqual(added, ["c.yaml"])
        self.assertEqual(changed, ["b.yaml"])
        self.assertEqual(removed, ["a.yaml"])


if __name__ == "__main__":
    unittest.main()
