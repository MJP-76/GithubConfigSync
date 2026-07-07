# GitHub Config Sync — Project Plan & Tracker

Use this as the single source of truth for **where we are**, **what is next**, and **what is done**.

---

## Status Snapshot

- **Current milestone:** `v0.1.3 — Security + Auth`
- **Track:** Home Assistant Integration + Home Assistant Add-on (Ingress Web UI)
- **Release cadence:** Dev pre-releases per milestone increment
- **Version state:** See auto-managed tracker below.

<!-- VERSION:START -->
- Integration version: `0.0.24`
- Add-on version: `0.1.7`
- Channel: `stable`
- Release tag: `v0.0.24`
<!-- VERSION:END -->

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

- [x] Complete `v0.1.2` and publish next dev release
- [x] Start `v0.1.3` auth/security hardening

## Next Up

- [ ] Continue `v0.1.3` security/auth hardening follow-ups
- [ ] Prep `v0.1.4` integration ↔ add-on contract follow-up work

## Blockers / Decisions Needed

- [x] Sync engine direction: **git-native engine**
- [x] Minimum supported Home Assistant version: `2026.06.2`

---

## Release Checklist (Per Tag)

- [ ] Version bumped (integration/add-on as applicable)
- [ ] Run `python3 scripts/sync_versions.py ...` for stable/dev channel
- [ ] Validation/CI green
- [ ] Docs updated (features + migration notes)
- [ ] Tag created and pushed
- [ ] GitHub Release created (pre-release or stable)
- [ ] Tracker updated in this file
