from __future__ import annotations

from pathlib import Path
import runpy
import sys

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

runpy.run_path(str(APP_ROOT / "github_sync_app" / "server.py"), run_name="__main__")
