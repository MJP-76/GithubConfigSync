from __future__ import annotations

import json
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path

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
        self._orig_config_root = server.CONFIG_ROOT

        server.DATA_DIR = self._data_dir
        server.SUPERVISOR_OPTIONS_PATH = self._data_dir / "options.json"
        server.WEBUI_OPTIONS_PATH = self._data_dir / "webui_options.json"
        server.STATE_PATH = self._data_dir / "state.json"
        server.LOG_PATH = self._data_dir / "sync.log"
        server.HASH_INDEX_PATH = self._data_dir / "hash_index.json"
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


if __name__ == "__main__":
    unittest.main()
