# GitHub Config Sync — Project Plan & Tracker

Use this as the single source of truth for **where we are**, **what is next**, and **what is done**.

---

## Status Snapshot

- **Current milestone:** `v0.4.0 — RC release`
- **Last updated:** 2026-07-15
- **Track:** Home Assistant Integration + Home Assistant Add-on (Ingress Web UI)
- **Latest shipped improvements:** autosave in the UI, bundled starter files, fast git-tree Clean Repo, and dry-run feedback in manual sync
- **Current operator UX:** Device Login section first, existing/create repo flow, troubleshooting auth overrides hidden by default
- **Version state:** stable and RC share the mainline version; dev remains the prerelease/testing track.
- **Release tracks:** stable and RC ship from the main repository, dev carries prerelease work.
- **Versioning rule:** keep numeric versions only, and bump them in sequence for stable, RC, and dev releases.

<!-- VERSION:START -->
- Integration version: `0.4.2-dev`
- Add-on version: `0.4.2-dev`
- Channel: `dev`
- Release tag: `v0.4.2-dev`
<!-- VERSION:END -->

---

## Cross-device handoff (use this first on another machine)

1. Open this file (`PROJECT_PLAN.md`) and read **Status Snapshot** + **Active Sprint Tracker**.
2. Verify the latest tag/release in GitHub and keep this tracker aligned with the shipped version lines.
3. Update this file after each shipped change so the tracker stays in sync.
4. Ship stable and RC releases from the main repo; keep dev work in `GithubConfigSync-dev` until promoted.

**Current repo context**

- Integration path: `custom_components/github_config_sync/`
- Add-on path: `addons/github-config-sync/`
- Add-on web app: `addons/github-config-sync/rootfs/app/`
- Version sync script: `scripts/sync_versions.py`

---

## Work completed so far (history + outcomes)

### Integration and platform foundations

- [x] Fixed integration load errors caused by stale constants/imports.
- [x] Completed integration/repo rename and branding alignment to **Github Config Sync**.
- [x] Stabilized config flow behavior and handler compatibility.
- [x] Implemented GitHub OAuth Device Flow for the integration setup path.
- [x] Added HACS + Hassfest validation workflow and metadata scaffolding.

### Add-on architecture and runtime

- [x] Built Home Assistant add-on scaffold (`addons/github-config-sync/`) with ingress UI.
- [x] Added API/runtime surfaces: options, status, health, sync trigger.
- [x] Introduced structured sync core (`sync/engine`, `sync/github_client`, `sync/models`, `sync/errors`).
- [x] Added hash-index based file diffing (added/changed/removed) and runtime summaries.
- [x] Added sync test coverage for hashing, planning, and API behavior.

### Major production fixes shipped

- [x] Fixed add-on image/base compatibility and build failures.
- [x] Resolved PEP 668 packaging issue by installing Flask via Alpine package (`py3-flask`) instead of system pip.
- [x] Added add-on `CHANGELOG.md` so Supervisor can resolve changelog metadata.
- [x] Fixed UI non-JSON parsing failure handling.
- [x] Fixed ingress API 404 behavior by using ingress-aware API paths in frontend.

### UX work discussed and implemented

- [x] Moved Device Flow controls to a dedicated top section.
- [x] Hid token/client ID inputs behind troubleshooting controls by default.
- [x] Added repository mode UX: choose **existing repo** (picker) or **create new repo**.
- [x] Added backend repo endpoints for list/create and UI wiring to persist selected repo.

### Release and process

- [x] Published iterative stable releases through `v0.0.23` (add-on `0.1.6`).
- [x] Added/used automated version sync script across integration/add-on/docs.
- [x] Added this in-repo tracker as the canonical cross-device status document.

### Security focused

- [x] Forced private GitHub repository creation.
- [x] Added warnings against public repositories and two-way sync risk.
- [x] Added a hard filter for obvious sensitive Home Assistant files and paths.
- [x] Documented that remote deletes do not remove local files.
- [ ] Lock down local API endpoints with Supervisor/Ingress header checks and review diagnostics exposure.
- [ ] Revisit mount-point path resolution and path ancestry checks for any user-controlled filesystem inputs.
- [ ] Tighten diagnostics redaction to strip auth headers, URLs, and token-shaped secrets before export.
- [ ] Review whether any additional secret-scanning or blocklist patterns should be added later.

---

## What we agreed in discussion (product decisions)

- Device Flow is the default auth path for both integration and add-on UX.
- Token/client ID should not be front-and-center for normal users.
- Repository selection should be guided (picker/create) instead of manual-only typing.
- Keep both Hassfest and HACS validation in place while integration distribution continues.
- Keep stable / RC / dev version lines explicit so the repo can ship the right track from the right repository.

---

## Milestone Roadmap

## v0.1.0 — Foundation

- [x] Custom integration scaffold in `custom_components/github_config_sync`
- [x] Config flow + token handling foundations
- [x] HACS metadata and validation workflow
- [x] GitHub release/tag pipeline established

## v0.1.1 — Compliance Fixes

- [x] Config flow schema/runtime stability fixes
- [x] OAuth/device-flow parsing corrections
- [x] Home Assistant-compatible auth flow iteration
- [x] Dev release line advanced through `v0.0.18-dev`

## v0.1.2 — Sync Engine Hardening

- [x] Add-on scaffold with ingress UI (`addons/github-config-sync`)
- [x] Add-on repository metadata (`repository.yaml`)
- [x] Add-on API endpoints (`/api/health`, `/api/options`, `/api/status`, `/api/sync`)
- [x] Hash-based changed-file detection (added/changed/removed)
- [x] Real GitHub upsert/delete sync path integrated in runtime endpoint
- [x] Structured sync module boundaries (`github_client`, `sync_engine`, models, errors)
- [x] Tests for hash diff + sync planning + API happy path/error path
- [x] End-to-end dry-run and live-run verification notes in docs

## v0.1.3 — Security + Auth

- [x] Token never persisted/logged in plaintext beyond required runtime paths
- [x] OAuth path hardened with clear fallback/error handling
- [x] Repository/auth diagnostics surfaced in status and diagnostics bundle
- [x] Security notes in docs (`SECURITY.md` or equivalent section)

## v0.1.4 — Integration ↔ Add-on Contract

- [x] Define stable local API contract between integration and add-on
- [x] Expose add-on health/sync status in HA entities
- [x] Diagnostics export bundle (config + status + sanitized logs)

## v0.1.5 — Quality Gate

- [x] Unit tests for sync engine + API + config validation
- [x] CI includes integration checks + add-on checks + tests
- [x] Release checklist enforced for each tag
- [x] Migration notes template for every milestone release

## v0.1.6 — Release Bump

- [x] Version tracker synced across integration, add-on, runtime, and docs
- [x] Changelog updated for the release bump
- [x] Release checklist verified against the current repo state

## v0.1.7 — Post-Release Cleanup

- [x] Documentation tracker cleanup completed
- [x] Add-on auth/repo-picker runbook content reflected in docs
- [x] HACS metadata requirements validated against repo settings
- [x] HASSfest badge added to README files

## v0.1.8 — Roadmap Closure

- [x] Security/auth hardening work completed and folded into shipped docs/code
- [x] Integration ↔ add-on API contract/status work completed and reflected in docs/code

## v0.1.9 — Planning Decisions Closed

- [x] Add-on sync strategy decided
- [x] Minimum supported Home Assistant version decided
- [x] Repo picker filtering/pagination decision closed

## v0.1.10 — Repo Picker Selection Fix

- [x] Newly created repositories are selected automatically in the repo picker

## v0.1.11 — Sync Performance Planning

- [x] Track future upload/snapshot performance improvements for later implementation

## v0.1.12 — Clean Upload Snapshot Safety

- [x] Clean upload preserves version snapshots and only clears the live tree

## v0.1.13 — Clean Upload App Safety

- [x] Clean upload preserves app README and required app folders

## Active Sprint Tracker (Now)

## Completed

- [x] Validate HACS metadata requirements tied to GitHub repo settings (description/topics/brands)
- [x] Add hassfest badge with the other badges on all README pages
- [x] Close add-on sync strategy decision
- [x] Close minimum supported Home Assistant version decision
- [x] Close repo picker org filtering/pagination decision
- [x] Auto-select newly created repository in the repo picker
- [x] Track future upload/snapshot performance improvements for later implementation
- [x] Clean upload preserves version snapshots and only clears the live tree
- [x] Clean upload preserves app README and required app folders

## In Progress

- [ ] Normalize the version tracker across the stable, RC, and dev release lines.
- [ ] Close the remaining security hardening follow-ups in the tracker.
- [ ] Keep the project-plan handoff aligned with the active release track.

---

## Immediate execution plan (next working session)

1. Normalize the mixed version lines in the docs/tracker so stable, RC, and dev are explicit and consistent.
2. Review and trim the remaining security hardening checklist items into concrete implementation tasks.
3. Keep the release tracker aligned with the active main/dev repos after any shipped change.

---

## Release Checklist (Per Tag)

- [ ] Version bumped (integration/add-on as applicable)
- [ ] Run `python3 scripts/sync_versions.py ...` for numeric sequence channel
- [ ] Validation/CI green
- [ ] Docs updated (features + migration notes)
- [ ] Tag created and pushed
- [ ] GitHub Release created (pre-release or stable)
- [ ] Tracker updated in this file
