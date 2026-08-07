## What this changes

<!-- One or two sentences. Link the issue if there is one: Closes #123 -->

## Why

## How it was verified

- [ ] `pytest` passes locally
- [ ] `ruff check .` is clean
- [ ] Added or updated tests for the change
- [ ] Ran the pipeline against `seeds.csv` end to end, if the pipeline changed

## Notes for the reviewer

<!-- Call it out explicitly if this touches either of these:
     - scoring weights in scoring.py, which make old and new reports incomparable
     - the cache schema or domain normalisation in cache.py, which orphans
       existing cache.db files -->
