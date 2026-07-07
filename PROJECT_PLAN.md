# GitHub Config Sync — Project Plan & Tracker

Use this as the single source of truth for **where we are**, **what is next**, and **what is done**.

---

## Status Snapshot

- **Current milestone:** `v0.1.3 — Security + Auth`
- **Last updated:** 2026-07-07
- **Track:** Home Assistant Integration + Home Assistant Add-on (Ingress Web UI)
- **Latest shipped improvements:** Add-on Device Flow auth + ingress path fix + repo picker/create flow
- **Current operator UX:** Device Login section first, existing/create repo flow, troubleshooting auth overrides hidden by default
- **Version state:** See auto-managed tracker below.

<!-- VERSION:START -->
- Integration version: `0.2.14`
- Add-on version: `0.2.14`
- Channel: `stable`
- Release tag: `v0.2.14`
<!-- VERSION:END -->

---

## Cross-device handoff (use this first on another machine)

1. Open this file (`PROJECT_PLAN.md`) and read **Status Snapshot** + **Active Sprint Tracker**.
2. Verify the latest tag/release in GitHub (`v0.0.23` at time of writing).
3. Continue from the top unchecked item in **In Progress**.
4. After finishing work, update this file and ship via: version bump → tag → GitHub release.

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

---

## What we agreed in discussion (product decisions)

- Device Flow is the default auth path for both integration and add-on UX.
- Token/client ID should not be front-and-center for normal users.
- Repository selection should be guided (picker/create) instead of manual-only typing.
- Keep both Hassfest and HACS validation in place while integration distribution continues.

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

## v0.1.2 — Sync Engine Hardening (IN PROGRESS)

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

## Active Sprint Tracker (Now)

## In Progress

- [ ] Add end-to-end dry-run and live-run verification notes in docs (close `v0.1.2`)
- [ ] Add runbook section for add-on auth/repo-picker workflow and common recovery steps
- [ ] Validate HACS metadata requirements tied to GitHub repo settings (description/topics/brands)

## Next Up

1. [ ] Close remaining `v0.1.2` docs/runbook items and release.
2. [ ] Start `v0.1.3` security/auth hardening (token handling + diagnostics).
3. [ ] Define `v0.1.4` integration↔add-on API contract and expose HA-side health/status.

## Blockers / Decisions Needed

- [ ] Decide whether add-on sync should use **GitHub Contents API only** or support **git-native engine** later
- [ ] Decide minimum supported Home Assistant version for add-on/integration pairing policy
- [ ] Decide whether repo picker should support org filtering + pagination in UI

---

## Immediate execution plan (next working session)

1. Write docs section: dry-run vs live-run verification steps with expected outputs and failure handling.
2. Add runbook: Device Flow/auth troubleshooting, ingress/API troubleshooting, repo picker/create troubleshooting.
3. Confirm repository-level HACS prerequisites in GitHub settings (description/topics/brands) and reflect status here.
4. Ship next release after docs/runbook updates and tracker refresh.

---

## Release Checklist (Per Tag)

- [ ] Version bumped (integration/add-on as applicable)
- [ ] Run `python3 scripts/sync_versions.py ...` for stable/dev channel
- [ ] Validation/CI green
- [ ] Docs updated (features + migration notes)
- [ ] Tag created and pushed
- [ ] GitHub Release created (pre-release or stable)
- [ ] Tracker updated in this file
