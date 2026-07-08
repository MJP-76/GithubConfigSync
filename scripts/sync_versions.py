#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

MANIFEST_PATH = REPO_ROOT / "custom_components/github_config_sync/manifest.json"
ADDON_CONFIG_PATH = REPO_ROOT / "addons/github-config-sync/config.yaml"
SERVER_PATH = REPO_ROOT / "addons/github-config-sync/rootfs/app/server.py"
DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "addons/github-config-sync/README.md",
    REPO_ROOT / "PROJECT_PLAN.md",
]

VERSION_BLOCK_PATTERN = re.compile(
    r"<!-- VERSION:START -->.*?<!-- VERSION:END -->",
    flags=re.DOTALL,
)


def _assert_simple_version(value: str, flag_name: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError(f"{flag_name} must be in x.y.z format (no suffix): {value}")


def _channelize(version: str, channel: str) -> str:
    if channel == "stable":
        return version
    if channel == "rc":
        return f"{version}-rc"
    return f"{version}-dev"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _replace_manifest_version(content: str, integration_version: str) -> str:
    data = json.loads(content)
    data["version"] = integration_version
    return json.dumps(data, indent=2) + "\n"


def _replace_yaml_version(content: str, addon_version: str) -> str:
    updated, count = re.subn(
        r'(?m)^version:\s*"[^"]+"$',
        f'version: "{addon_version}"',
        content,
        count=1,
    )
    if count != 1:
        raise ValueError("Could not find add-on version line in config.yaml")
    return updated


def _replace_server_version(content: str, addon_version: str) -> str:
    updated, count = re.subn(
        r'(?m)^APP_VERSION\s*=\s*"[^"]+"$',
        f'APP_VERSION = "{addon_version}"',
        content,
        count=1,
    )
    if count != 1:
        raise ValueError("Could not find APP_VERSION line in server.py")
    return updated


def _replace_doc_block(content: str, integration_version: str, addon_version: str, channel: str) -> str:
    block = "\n".join(
        [
            "<!-- VERSION:START -->",
            f"- Integration version: `{integration_version}`",
            f"- Add-on version: `{addon_version}`",
            f"- Channel: `{channel}`",
            f"- Release tag: `v{integration_version}`",
            "<!-- VERSION:END -->",
        ]
    )
    updated, count = VERSION_BLOCK_PATTERN.subn(block, content, count=1)
    if count != 1:
        raise ValueError("Could not find VERSION block in documentation")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize integration/add-on/app/doc version numbers.",
    )
    parser.add_argument("--integration", required=True, help="Base integration version in x.y.z format")
    parser.add_argument("--addon", help="Base add-on version in x.y.z format (defaults to --integration)")
    parser.add_argument(
        "--channel",
        choices=["stable", "rc", "dev"],
        required=True,
        help="Release channel; rc/dev append suffixes to versions.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: fail if files would change, do not write.",
    )
    args = parser.parse_args()

    _assert_simple_version(args.integration, "--integration")
    addon_base = args.addon or args.integration
    _assert_simple_version(addon_base, "--addon")

    integration_version = _channelize(args.integration, args.channel)
    addon_version = _channelize(addon_base, args.channel)

    planned_updates: dict[Path, str] = {}
    planned_updates[MANIFEST_PATH] = _replace_manifest_version(_read(MANIFEST_PATH), integration_version)
    planned_updates[ADDON_CONFIG_PATH] = _replace_yaml_version(_read(ADDON_CONFIG_PATH), addon_version)
    planned_updates[SERVER_PATH] = _replace_server_version(_read(SERVER_PATH), addon_version)
    for path in DOC_PATHS:
        planned_updates[path] = _replace_doc_block(
            _read(path),
            integration_version=integration_version,
            addon_version=addon_version,
            channel=args.channel,
        )

    changed_paths = [path for path, new_content in planned_updates.items() if _read(path) != new_content]

    if args.check:
        if changed_paths:
            for path in changed_paths:
                print(f"out-of-sync: {path.relative_to(REPO_ROOT)}")
            return 1
        print("version sync check passed")
        return 0

    for path in changed_paths:
        _write(path, planned_updates[path])
        print(f"updated: {path.relative_to(REPO_ROOT)}")

    if not changed_paths:
        print("no changes required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
