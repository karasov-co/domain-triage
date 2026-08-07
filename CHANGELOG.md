# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-08-07

First tagged release. The pipeline has been working since May; this release
marks the point where it is documented and maintained as a project rather than
a script.

### Added

- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), and this
  changelog.
- Issue and pull request templates.
- Dependabot, monthly, for pip and GitHub Actions.
- Python 3.14 added to the CI matrix, alongside 3.12 and 3.13.

### Changed

- CI now uses `actions/checkout@v5` and `actions/setup-python@v6`, with pip
  caching keyed on `requirements.txt`.
- README links to the contributing guide and this changelog. The CI badge
  pointed at the repository's former owner (`vkarasovpm-dotcom`) and now points
  at `karasov-co`; it had been resolving only through a GitHub rename redirect.

### Existing behaviour at 1.0.0

Recorded here so later entries have a baseline:

- Reads a CSV of domains, checks each over HTTP, and scores it 0–100 with an
  explanation attached to every adjustment, then maps that to a 1–10 score, a
  priority bucket, and a suggested action.
- 10 parallel workers; roughly 100 domains in 20 seconds.
- SQLite cache with resume and rerun-failed support, so an interrupted run
  picks up where it stopped.
- Failed domains are reported, not fatal — one unreachable host cannot end a
  run.
- Outputs `results.csv`, `failed.csv` and a readable `summary.md`.
- 46 tests covering the scoring rules and the cache layer, none of which touch
  the network.

[Unreleased]: https://github.com/karasov-co/domain-triage/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/karasov-co/domain-triage/releases/tag/v1.0.0
