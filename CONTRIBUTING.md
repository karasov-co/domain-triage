# Contributing

Thanks for taking a look. Domain Triage is a small pipeline with one job:
turn a CSV of domains into scores, buckets and a readable report, without
falling over when individual domains misbehave.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

Python 3.12 or newer.

```bash
git clone https://github.com/karasov-co/domain-triage.git
cd domain-triage

python3 -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

## Running the tests

```bash
pytest                           # whole suite
pytest test_scoring.py           # scoring rules only
pytest -k cache                  # cache layer only
```

The suite does not make network requests — `checker.py` is stubbed wherever
scoring or the cache needs a result. Please keep it that way: a test that
actually resolves a domain is slow, flaky, and depends on someone else's
uptime.

## Linting

```bash
ruff check .
ruff check --fix .
```

Rule configuration lives in `ruff.toml`. Two rules are switched off on
purpose, and the file explains why — broad `except` clauses are the deliberate
safety net that keeps one bad domain from killing a run, and the summary
timestamp is meant to be local wall-clock time.

CI runs `ruff check` and `pytest` on Python 3.12, 3.13 and 3.14. Both must be
green before a pull request can merge.

## Submitting a change

1. Branch off `main`.
2. Make the change, and add a test that fails without it.
3. Run `pytest` and `ruff check .`.
4. Add an entry under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md).
5. Open a pull request and fill in the template.

## Two things to be careful with

**The scoring weights.** `calculate_score` in `scoring.py` starts every domain
at 50 and adds or subtracts fixed amounts, each one recorded in `reasons` so a
score can always be explained. If you change a weight, change it in one place
and update the tests that pin it — a silent reweighting makes old reports
incomparable with new ones. Keep appending a reason for every adjustment.

**The cache schema.** `cache.py` stores one row per domain in SQLite, keyed by
a normalised domain string. Resume and rerun-failed both depend on the `status`
column. Adding a column is fine; changing the key normalisation will orphan
every existing `cache.db`, so it needs a migration note in the changelog.

## Reporting a bug

Include the domain that triggered it where you can. A failing domain is
usually reproducible, and it is far faster to fix with the actual input than
without it. If the domain is client-confidential, say so and describe the
shape of the response instead.
