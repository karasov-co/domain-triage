# Domain Triage — AI Automation Command Center

[English](README.md) | Русский

Pipeline для триажа списка доменов: на входе CSV из 100 доменов, на выходе — оценка каждого по шкале 1–10, рекомендация что с ним делать (outreach / manual review / skip), и читаемый отчёт.

**Производительность:** 100 доменов за ~20 секунд (10 параллельных потоков).
**Устойчивость:** упавшие домены не валят скрипт, попадают в отчёт. Поддерживается докачка и rerun-failed.

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

| Флаг | Назначение |
|---|---|
| `--seeds PATH` | путь к CSV (по умолчанию `seeds.csv`) |
| `--limit N` | обработать только первые N доменов |
| `--workers N` | количество параллельных потоков (по умолчанию 10) |
| `--rerun-failed` | повторить только упавшие домены |

**Типичные сценарии:**

```bash
rm -f cache.db && python main.py --limit 5    # быстрый тест
rm -f cache.db && python main.py              # полный прогон
python main.py --rerun-failed                 # повтор только failed
```

---

## Структура проекта

```
domain-triage/
├── seeds.csv          # вход
├── cache.py           # SQLite state machine (pending/done/failed)
├── checker.py         # HTTP + retry + парсинг (status, title, html_size, tld, parking)
├── scoring.py         # rule-based 1–10 + bucket + action
├── main.py            # оркестратор: CLI, параллельность, output
├── cache.db           # БД с состоянием (создаётся автоматически)
└── output/
    ├── results.csv    # все домены, отсортированы по score
    ├── failed.csv     # только упавшие, с причиной
    └── summary.md     # отчёт для человека
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

## Что проверял и почему

Для каждого домена собираю минимально достаточный набор сигналов, который позволяет принять решение **«стоит ли тратить время человека на этот домен»**.

| Сигнал | Зачем |
|---|---|
| **HTTP status** | Базовый признак «жив ли сайт». 200 ≠ хорошо, но 4xx/5xx = почти точно мимо. |
| **Final URL после редиректов** | Помогает увидеть, куда реально ведёт домен (например, на чужой shop). |
| **Response time** | Быстрый ответ → реальный сайт; медленный → возможно заглушка/честный пот, нужен ручной взгляд. |
| **HTML size** | Очень маленький HTML (<1 KB) часто признак паркинга или ошибки. |
| **`<title>`** | Главный текстовый сигнал. Отсутствие title = слабый сайт или ошибка. |
| **TLD** | Спам-TLD (.xyz, .top, .tk, .click и т.д.) — слабый негативный сигнал. |
| **Parking keywords** | Прямые маркеры паркинга в HTML («domain for sale», «buy this domain» и т.д.). |

---

## Что НЕ стал проверять и почему

| Не делал | Почему |
|---|---|
| **WHOIS / возраст домена** | Дополнительная сетевая нагрузка, rate limits у whois-серверов, добавляет 1–3s/домен. На 100 доменах не критично, но MVP без него уже информативен. |
| **DNS-records (MX, SPF, etc.)** | Нужно для оценки «настоящий ли это бизнес», но требует отдельной библиотеки и удваивает время. Оставил на v2. |
| **Скриншот сайта** | Дорогой headless browser (Playwright). Ценность есть для UI-обзора, но сильно замедляет. |
| **Языковая детекция / тематика** | Это уже работа для LLM-обогащения top-bucket доменов. На уровне «отсеять мусор» не нужно. |
| **SSL certificate validity** | Косвенно покрыто: невалидный SSL → SSLError → попадает в failed. Глубокий разбор сертификата — overkill. |
| **robots.txt / sitemap.xml** | Сигнал «сайт настроен серьёзно», но дорогой по дополнительным запросам. На v2. |

Принцип: **в MVP только то, что отвечает на главный вопрос — выкинуть или оставить для review**. Всё, что про «классификация бизнеса/индустрии» — это уже следующий слой (LLM-enrichment).

---

## Логика scoring

**Подход — rule-based** (не ML). Причины:

- Объяснимость: каждый score сопровождается полем `reason` («+50 base, +20 HTTP 200, −15 spammy TLD»), что важно для доверия пользователя.
- Нет labeled данных для ML.
- Легко калибровать: один файл `scoring.py`, табличка весов.

**Формула:** старт 50, дальше плюсы и минусы, на выходе clip(0, 100), потом маппинг на 1–10 (`score_1_10 = round(score/10)`).

| Сигнал | Дельта |
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
| `<title>` присутствует | +10 |
| HTML size >5 KB | +5 |
| HTML size <1 KB | −10 |
| Parked domain | −25 |
| Spammy TLD | −15 |

**Bucket** — техническая категория по score: `high` (≥75), `medium` (≥50), `low` (≥25), `skip` (<25).

**Action** — бизнес-рекомендация, **учитывает контекст**:

- `parked=True` → action=`skip` независимо от score (бизнес-правило перебивает число).
- `error` есть → `investigate` если score≥25, иначе `skip`.
- Иначе по score: `review_for_outreach` / `manual_review` / `deprioritize` / `skip`.

Разделение bucket/action — это **separation of concerns**: завтра поменяются бизнес-правила outreach, поменяется только `get_suggested_action`, аналитика по buckets останется нетронутой.

---

## Что бы добавил, если бы было ещё 2 дня

**День 1 — точность scoring:**

- WHOIS-обогащение: возраст домена, регистратор. Молодой домен на .xyz через NameSilo = сильный спам-сигнал.
- Контентные сигналы: detect contact form, copyright year в футере, наличие /about /pricing страниц.
- Снятие HTML-снапшота для каждого done-домена в отдельную папку — пригодится для последующего ML/LLM.

**День 2 — LLM-обогащение и интеграции:**

- Для top-bucket доменов: пропустить homepage через LLM с промптом «классифицируй индустрию, оцени серьёзность 1–10, вытащи value proposition в одном предложении». Это даёт **персонализацию для outreach**.
- Webhook в n8n / Make: после прогона отправлять `summary.md` в Slack-канал, top-10 в CRM как новые leads.
- Pytest-покрытие для checker и cache (сейчас тесты только в scoring).

---

## Где сломается код на 5 000 доменов

Прогноз по слоям:

**1. Время.** Сейчас 5 dom/s. На 5 000 → ~17 минут с 10 потоками. Терпимо, но долго.

- Решение: поднять `--workers` до 30–50. Дальше упрёмся в локальный DNS / rate limits.
- Радикально: переход с threads на **async** (`aiohttp` + `asyncio`) — даёт +10× при той же памяти.

**2. SQLite writes.** SQLite не умеет concurrent writes — потоки сериализуются на write lock. На 5 000 заметно. На 50 000 — критично.

- Решение: batch insert (`executemany`) или переход на Postgres.

**3. Memory.** `get_all_results()` тянет всё в память. На 5K — десятки MB, ок. На 100K — сотни MB, нужен streaming-генератор.

**4. Rate limiting от целевых сайтов.** При 30+ потоках с одного IP некоторые сервера начнут банить (Cloudflare, Akamai). Часть «живых» доменов ложно попадёт в failed.

- Решение: прокси-пул, ротация User-Agent, задержка между запросами на один и тот же домен.

**5. DNS.** Локальный resolver не любит шквал запросов.

- Решение: in-process DNS cache (`aiodns`) или системный resolver с кешем.

**Последовательность миграции при росте:** workers → async → Postgres → прокси-пул. **Сначала измерить, потом оптимизировать** — не делать всё сразу.

---

## Какие допущения сделал из-за размытости ТЗ

1. **Score 1–10:** реализован как `round(score_0_100 / 10)`. Внутри держу 0–100 для гранулярности (легче калибровать веса), наружу даю 1–10 как в ТЗ.
2. **«Интересен для ручного просмотра»** интерпретирую как «может быть лидом для outreach» — отсюда action `review_for_outreach` для high-bucket.
3. **Триаж = бинарное «выкинуть/оставить»**, не классификация по индустрии. Классификация — отдельный слой (LLM), не в MVP.
4. **Парковочные ключевые слова** — английские, фиксированный список. Русские/мультиязычные — out of scope.
5. **Spammy TLD list** — ручной, основан на общеизвестных репутационных рейтингах (.tk, .ml, .ga, .cf, .xyz, .top и т.д.). Не претендует на полноту.
6. **Только HTTPS:** все запросы идут на `https://`. Если домен живёт только на HTTP — будет в failed. На v2 — fallback HTTP→HTTPS.
7. **Timeout 10s** — компромисс между строгостью и терпимостью к медленным серверам.
8. **3 retry** для transient errors (timeout, connection error). Permanent errors (SSL, redirects, 4xx) не повторяю — бессмысленно.
9. **Парковки в реальном `seeds.csv`:** все «парковочные» домены в наборе оказались NXDOMAIN (физически не зарегистрированы), а не live-паркинги. Они корректно ловятся как `connection_error` → `action=skip`. `detect_parking` реализован для случаев live-паркингов с keywords/title-эвристиками, но в данном наборе срабатывать ему не на чем. На реальных датасетах с Sedo/GoDaddy parking — будет работать.

---

## Бонусы (всё реализовано)

- ✅ **Обработка ошибок:** упавшие домены не крашат скрипт, попадают в `failed.csv` и в summary с причиной. Двухуровневая защита: специфические `except` в `check_domain` + safety net `except Exception` в `process_domain`.
- ✅ **`--rerun-failed`:** переводит failed → pending, обрабатывает только их. Уже сделанные домены не трогаются.
- ✅ **Кеширование уже проверенных:** SQLite с PK на domain + `INSERT OR IGNORE`. Повторный `python main.py` ничего не пере-обрабатывает (idempotent). Прерывание на середине → продолжение с того же места.
- ✅ **Параллелизм:** `ThreadPoolExecutor` с настраиваемым `--workers` (default 10). Дал 12× speedup на 100 доменах.
- ⚠️ **Rate limiting** реализован частично (через ограничение workers). Per-domain rate limit и прокси-пул — на v2.

---

## Как расширил бы это до v2 с n8n / Make / Slack / CRM

**Архитектура v2:**

```
Trigger (n8n cron / webhook)
  ↓
Domain Triage container (наш Python)
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
Slack notification: «Триаж завершён, N новых лидов в CRM»
```

**Конкретно:**

- **n8n** — оркестрация: cron → HTTP-trigger на наш скрипт (обёрнутый в FastAPI) → парсинг output.
- **Make** — простые интеграции: новая строка в Google Sheets с `action=skip` → ничего, с `review_for_outreach` → создать лид.
- **Slack** — webhook: после каждого прогона `summary.md` рендерится в Block Kit и постится в канал.
- **CRM** — для каждого домена с `action=review_for_outreach` создаётся deal с pre-filled полями.

Главная идея v2: **наш скрипт становится одним шагом в большой цепочке**, а не одиночным CLI.

---

## Зависимости

**Внешние** (`requirements.txt`):

- `requests` — HTTP-клиент
- `beautifulsoup4` — HTML-парсинг
- `lxml` — быстрый парсер
- `tqdm` — прогресс-бар

**Стандартная библиотека:** `csv`, `sqlite3`, `argparse`, `concurrent.futures`, `json`, `time`, `os`.
