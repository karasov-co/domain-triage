# Domain Triage — AI Automation Command Center

[![CI](https://github.com/karasov-co/domain-triage/actions/workflows/ci.yml/badge.svg)](https://github.com/karasov-co/domain-triage/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

English | [Русский](README.ru.md)

Pipeline for triaging a list of domains: takes a CSV of 100 domains as input, and outputs a score for each on a 1–10 scale, a recommendation of what to do with it (outreach / manual review / skip), and a readable report.

**Performance:** 100 domains in ~20 seconds (10 parallel workers).
**Resilience:** failed domains don't crash the script — they land in the report. Resuming and rerun-failed are supported.

---

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python main.py

cat output/summary.md
open output/results.csv
```

---

## CLI

```bash
python main.py [--seeds PATH] [--limit N] [--workers N] [--rerun-failed]
```

| Flag | Purpose |
|---|---|
| `--seeds PATH` | path to the CSV (default `seeds.csv`) |
| `--limit N` | process only the first N domains |
| `--workers N` | number of parallel workers (default 10) |
| `--rerun-failed` | retry only the failed domains |

**Typical scenarios:**

```bash
rm -f cache.db && python main.py --limit 5    # quick test
rm -f cache.db && python main.py              # full run
python main.py --rerun-failed                 # retry failed only
```

---

## Project structure

```
domain-triage/
├── seeds.csv          # input
├── cache.py           # SQLite state machine (pending/done/failed)
├── checker.py         # HTTP + retry + parsing (status, title, html_size, tld, parking)
├── scoring.py         # rule-based 1–10 + bucket + action
├── main.py            # orchestrator: CLI, parallelism, output
├── cache.db           # state DB (created automatically)
└── output/
    ├── results.csv    # all domains, sorted by score
    ├── failed.csv     # only the failed ones, with a reason
    └── summary.md     # human-readable report
```

**Pipeline:**

```
seeds.csv → cache (pending) → ThreadPool(10) → [checker → scoring] → cache (done/failed) → output/*
```

---

## Tests

```bash
pytest -v
```

---

## What I checked and why

For each domain I collect the minimally sufficient set of signals needed to decide **"is it worth spending a human's time on this domain."**

| Signal | Why |
|---|---|
| **HTTP status** | Basic "is the site alive" signal. 200 ≠ good, but 4xx/5xx = almost certainly a miss. |
| **Final URL after redirects** | Helps see where the domain actually leads (e.g. to someone else's shop). |
| **Response time** | Fast response → a real site; slow → possibly a stub/honest sweat, needs a manual look. |
| **HTML size** | Very small HTML (<1 KB) is often a sign of parking or an error. |
| **`<title>`** | The main text signal. Missing title = weak site or an error. |
| **TLD** | Spammy TLDs (.xyz, .top, .tk, .click, etc.) — a weak negative signal. |
| **Parking keywords** | Direct parking markers in the HTML ("domain for sale", "buy this domain", etc.). |

---

## What I did NOT check and why

| Skipped | Why |
|---|---|
| **WHOIS / domain age** | Extra network load, rate limits on whois servers, adds 1–3s/domain. Not critical at 100 domains, but the MVP is already informative without it. |
| **DNS records (MX, SPF, etc.)** | Needed to assess "is this a real business," but requires a separate library and doubles the time. Left for v2. |
| **Website screenshot** | An expensive headless browser (Playwright). There's value for a UI overview, but it slows things down a lot. |
| **Language detection / topic** | That's already work for LLM enrichment of top-bucket domains. Not needed at the "filter out the junk" level. |
| **SSL certificate validity** | Indirectly covered: invalid SSL → SSLError → lands in failed. A deep certificate breakdown is overkill. |
| **robots.txt / sitemap.xml** | A signal that "the site is seriously set up," but expensive in extra requests. For v2. |

Principle: **in the MVP, only what answers the main question — discard or keep for review**. Everything about "business/industry classification" is already the next layer (LLM enrichment).

---

## Scoring logic

**Approach — rule-based** (not ML). Reasons:

- Explainability: every score comes with a `reason` field ("+50 base, +20 HTTP 200, −15 spammy TLD"), which matters for user trust.
- No labeled data for ML.
- Easy to calibrate: one file, `scoring.py`, a small table of weights.

**Formula:** start at 50, then pluses and minuses, output clipped to (0, 100), then mapped to 1–10 (`score_1_10 = round(score/10)`).

| Signal | Delta |
|---|---|
| HTTP 200 | +20 |
| HTTP 3xx | +5 |
| HTTP 4xx | −10 |
| HTTP 5xx | −15 |
| Connection error | −30 |
| Timeout | −20 |
| Other request error | −15 |
| Response <1s | +5 |
| Response >5s | −5 |
| `<title>` present | +10 |
| HTML size >5 KB | +5 |
| HTML size <1 KB | −10 |
| Parked domain | −25 |
| Spammy TLD | −15 |

**Bucket** — a technical category based on score: `high` (≥75), `medium` (≥50), `low` (≥25), `skip` (<25).

**Action** — a business recommendation, **context-aware**:

- `parked=True` → action=`skip` regardless of score (the business rule overrides the number).
- `error` present → `investigate` if score≥25, otherwise `skip`.
- Otherwise by score: `review_for_outreach` / `manual_review` / `deprioritize` / `skip`.

Splitting bucket/action is **separation of concerns**: tomorrow the outreach business rules will change, and only `get_suggested_action` will change — the bucket analytics stay untouched.

---

## What I would add given 2 more days

**Day 1 — scoring accuracy:**

- WHOIS enrichment: domain age, registrar. A young domain on .xyz via NameSilo = a strong spam signal.
- Content signals: detect contact form, copyright year in the footer, presence of /about /pricing pages.
- Taking an HTML snapshot for each done domain into a separate folder — useful for later ML/LLM work.

**Day 2 — LLM enrichment and integrations:**

- For top-bucket domains: run the homepage through an LLM with a prompt like "classify the industry, rate seriousness 1–10, extract the value proposition in one sentence." This gives **personalization for outreach**.
- Webhook into n8n / Make: after a run, send `summary.md` to a Slack channel, top-10 to the CRM as new leads.
- Pytest coverage for checker and cache (currently tests exist only for scoring).

---

## Where the code breaks at 5,000 domains

Forecast by layer:

**1. Time.** Currently 5 dom/s. At 5,000 → ~17 minutes with 10 workers. Tolerable, but slow.

- Fix: raise `--workers` to 30–50. Beyond that we hit local DNS / rate limits.
- Radical fix: switch from threads to **async** (`aiohttp` + `asyncio`) — gives +10× at the same memory footprint.

**2. SQLite writes.** SQLite doesn't do concurrent writes — threads serialize on the write lock. Noticeable at 5,000. Critical at 50,000.

- Fix: batch insert (`executemany`) or switch to Postgres.

**3. Memory.** `get_all_results()` pulls everything into memory. At 5K — tens of MB, fine. At 100K — hundreds of MB, needs a streaming generator.

**4. Rate limiting from target sites.** With 30+ workers from a single IP, some servers will start banning (Cloudflare, Akamai). Some "live" domains will falsely land in failed.

- Fix: proxy pool, User-Agent rotation, a delay between requests to the same domain.

**5. DNS.** The local resolver doesn't like a burst of requests.

- Fix: an in-process DNS cache (`aiodns`) or a system resolver with caching.

**Migration sequence as it grows:** workers → async → Postgres → proxy pool. **Measure first, optimize second** — don't do it all at once.

---

## Assumptions made due to ambiguous requirements

1. **Score 1–10:** implemented as `round(score_0_100 / 10)`. Internally I keep 0–100 for granularity (easier to calibrate weights), externally I expose 1–10 as in the spec.
2. **"Interesting for manual review"** I interpret as "could be a lead for outreach" — hence the `review_for_outreach` action for the high bucket.
3. **Triage = a binary "discard/keep"**, not an industry classification. Classification is a separate layer (LLM), not in the MVP.
4. **Parking keywords** — English, a fixed list. Russian/multilingual is out of scope.
5. **Spammy TLD list** — manual, based on well-known reputation ratings (.tk, .ml, .ga, .cf, .xyz, .top, etc.). Not meant to be exhaustive.
6. **HTTPS only:** all requests go to `https://`. If a domain only lives on HTTP — it ends up in failed. For v2 — an HTTP→HTTPS fallback.
7. **10s timeout** — a compromise between strictness and tolerance for slow servers.
8. **3 retries** for transient errors (timeout, connection error). Permanent errors (SSL, redirects, 4xx) aren't retried — pointless.
9. **Parking in the real `seeds.csv`:** all the "parked" domains in the set turned out to be NXDOMAIN (not physically registered), not live parking pages. They're correctly caught as `connection_error` → `action=skip`. `detect_parking` is implemented for live-parking cases with keyword/title heuristics, but in this dataset there's nothing for it to trigger on. On real datasets with Sedo/GoDaddy parking, it will work.

---

## Bonuses (all implemented)

- ✅ **Error handling:** failed domains don't crash the script, they land in `failed.csv` and in the summary with a reason. Two-tier protection: specific `except` clauses in `check_domain` + a safety net `except Exception` in `process_domain`.
- ✅ **`--rerun-failed`:** moves failed → pending, processes only those. Already-done domains aren't touched.
- ✅ **Caching of already-checked domains:** SQLite with a PK on domain + `INSERT OR IGNORE`. Running `python main.py` again reprocesses nothing (idempotent). An interruption mid-run → resumes from the same place.
- ✅ **Parallelism:** `ThreadPoolExecutor` with a configurable `--workers` (default 10). Gave a 12× speedup on 100 domains.
- ⚠️ **Rate limiting** is partially implemented (via limiting workers). Per-domain rate limiting and a proxy pool — for v2.

---

## How I would extend this to v2 with n8n / Make / Slack / CRM

**v2 architecture:**

```
Trigger (n8n cron / webhook)
  ↓
Domain Triage container (our Python)
  ↓
output/results.csv
  ↓
Google Sheets / Airtable
  ↓
Filter: action = review_for_outreach
  ↓
LLM enrichment (industry, value prop, persona)
  ↓
HubSpot / Pipedrive (create lead)
  ↓
Slack notification: "Triage complete, N new leads in the CRM"
```

**Specifically:**

- **n8n** — orchestration: cron → HTTP trigger to our script (wrapped in FastAPI) → parse the output.
- **Make** — simple integrations: a new row in Google Sheets with `action=skip` → nothing, with `review_for_outreach` → create a lead.
- **Slack** — webhook: after each run, `summary.md` is rendered into Block Kit and posted to the channel.
- **CRM** — for each domain with `action=review_for_outreach` a deal is created with pre-filled fields.

The main idea of v2: **our script becomes one step in a larger chain**, not a standalone CLI.

---

## Dependencies

**External** (`requirements.txt`):

- `requests` — HTTP client
- `beautifulsoup4` — HTML parsing
- `lxml` — fast parser
- `tqdm` — progress bar

**Standard library:** `csv`, `sqlite3`, `argparse`, `concurrent.futures`, `json`, `time`, `os`.

---

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
Participants are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Release history is in [CHANGELOG.md](CHANGELOG.md).

---

## License

[MIT](LICENSE) © Vitalii Karasov
