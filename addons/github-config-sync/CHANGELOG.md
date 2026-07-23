# Changelog

## 1.0.20

- Added `.ruff.toml` to the built-in ignore defaults.

## 1.0.19

- Made repository selection auto-save with the rest of the settings and removed the separate Save Settings button.

## 1.0.18

- Clean Repo now emits live delete counts in the activity panel while it wipes the remote tree.

## 1.0.17

- Startup now falls back to a supported-repo refresh if the cache is empty.

## 1.0.16

- Removed the all-repos button and fixed the supported-repo picker refresh path.

## 1.0.15

- Startup now loads cached supported repos, and the manual button refreshes the supported repo list.

## 1.0.14

- Added a startup repo list plus an on-demand add-on repo filter to avoid probing on load.

## 1.0.13

- Published a fresh dev release for the repo picker fix.

## 1.0.12

- Restored a safe repo picker filter that only shows add-on-style repositories without probing repo contents.

## 1.0.11

- Bumped the dev lane again so Home Assistant gets a fresh add-on index entry.

## 1.0.10

- Synced the embedded app version with the published add-on version so HA stops showing the old build number.

## 1.0.9

- Moved the live activity status into a single panel for both upload and delete work.
- Added clean repo status details to the same activity panel.

## 1.0.8

- Cleared stale startup sync state on app boot.
- Removed the repo list contents probe so the picker no longer burns GitHub rate limit on load.

## 1.0.7

- Fixed the stale running upload state so rebuilds clear canceled runs.
- Added a retry for DELETE content requests when GitHub returns a stale SHA conflict.

## 1.0.6

- Fixed startup flicker by only showing Ready after startup loads finish successfully.
- Fixed repo picker rate-limit errors so they no longer crash the page.
- Made the repo picker header stay on one line with the load button beside it.

## 1.0.5

- Added default ignore rules for common Home Assistant runtime, editor, and secret files.
- Added sensitive-file scanning so suspicious files are skipped and reported in a root warning file.
- Kept the repo picker and load button on one line in the UI.

## 1.0.4

- Added repo marker support so clean actions can verify add-on-managed repositories.
- Filtered unsafe repositories out of the repo picker.
- Made Clean Repo do a full remote reset, then restore the skeleton and refresh the marker.
- Made Clean Upload refresh the repo marker after the live upload finishes.

## 1.0.3

- Removed the Latest changes panel from the app UI.
- Fixed stale state so a new sync clears the previous result and scan.

## 1.0.2

- Fixed upload progress so the remaining counters count down during the run.
- Kept the repo picker and load button on one line.

## 1.0.1

- Fixed the startup crash caused by the new sensitive upload warning path.

## 1.0.0

- Promoted the main repo to the first stable release.
