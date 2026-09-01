# Installation

!!! info "This is an add-on, not a HACS integration"

    Install it from the Add-on Store. The legacy HACS integration is kept only
    to redirect installs to the add-on.

## Install

1. In Home Assistant, open **Settings → Add-ons → Add-on Store → Repositories**.
2. Add this repository URL: `https://github.com/MJP-76/GithubConfigSync`.
3. Install **Github Config Sync** and start it.
4. Open the app web UI (ingress), configure repository settings, and complete
   GitHub Device Flow login.

## Getting started

1. Open the app UI from the Add-on page.
2. Complete GitHub Device Flow login.
3. Pick an existing repository or create a new one.
4. Run a **dry run** first to confirm the scan looks correct.
5. Switch to a **live run** when ready.

!!! tip "Why start with a dry run?"

    A dry run shows you exactly what would be uploaded, changed, or deleted —
    without touching the remote. Confirm the plan looks right before enabling
    live syncs, especially on a freshly adopted repository.

## After a release

After a release, Home Assistant may need a rebuild/reinstall to pick up UI
changes from the add-on image.