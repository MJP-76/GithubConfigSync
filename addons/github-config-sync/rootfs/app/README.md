# Github Config Sync
[![CI](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml/badge.svg)](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml)
[![HASSfest](https://img.shields.io/badge/HASSfest-validated-success.svg)](https://developers.home-assistant.io/docs/creating_integration_manifest/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Compatible-03a9f4.svg)](https://www.home-assistant.io/)
[![HA Ready](https://img.shields.io/badge/Home%20Assistant-Ready-03a9f4.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![Manifest](https://img.shields.io/badge/Manifest-validated-success.svg)](https://developers.home-assistant.io/docs/creating_integration_manifest/)
[![Release](https://img.shields.io/github/v/tag/MJP-76/GithubConfigSync?label=release)](https://github.com/MJP-76/GithubConfigSync/releases)

Home Assistant custom integration for syncing the Home Assistant config folder to GitHub. This is a config sync tool, not a backup tool. <strong style="color:#ef4444">Danger Zone:</strong> <strong>Use a private GitHub repository only.</strong> Use caution with any two-way sync or other tools that can also write to the Home Assistant config tree, because they can cause local config loss or unexpected deletions.

This documentation and code were drafted with AI assistance and then reviewed/edited by the maintainer.
