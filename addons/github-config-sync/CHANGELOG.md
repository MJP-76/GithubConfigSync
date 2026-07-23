# Changelog

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
