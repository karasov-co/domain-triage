import json
import sqlite3

DB_PATH = "cache.db"

# main.py writes from 10 worker threads at once. SQLite's default busy timeout
# is 5s, which a burst of concurrent writers can exceed -- and the resulting
# "database is locked" surfaces as a lost domain, not a retry.
BUSY_TIMEOUT_SECONDS = 30


def _connect():
    return sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT_SECONDS)


def init_db():
    conn = _connect()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            domain TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            result_json TEXT,
            error TEXT
        )
    """)
    conn.commit()
    conn.close()


def add_domains(domains):
    normalized = []
    for d in domains:
        d = d.lower().strip().replace("https://", "").replace("http://", "").rstrip("/")
        if d:
            normalized.append((d,))
    conn = _connect()
    conn.executemany(
        "INSERT OR IGNORE INTO domains (domain, status) VALUES (?, 'pending')",
        normalized
    )
    conn.commit()
    conn.close()


def get_pending():
    conn = _connect()
    rows = conn.execute(
        "SELECT domain FROM domains WHERE status = 'pending'"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_result(domain, result):
    conn = _connect()
    conn.execute(
        "UPDATE domains SET status = 'done', result_json = ? WHERE domain = ?",
        (json.dumps(result, ensure_ascii=False), domain)
    )
    conn.commit()
    conn.close()


def save_failure(domain, error, result=None):
    """Record a failed domain.

    `result` is optional because a pipeline error has no facts to store. When
    the checker did produce facts, pass them: the score, bucket and action were
    already computed, and dropping them left every failed row in the report with
    empty score columns.
    """
    conn = _connect()
    if result is None:
        conn.execute(
            "UPDATE domains SET status = 'failed', error = ? WHERE domain = ?",
            (error, domain)
        )
    else:
        conn.execute(
            "UPDATE domains SET status = 'failed', error = ?, result_json = ? WHERE domain = ?",
            (error, json.dumps(result, ensure_ascii=False), domain)
        )
    conn.commit()
    conn.close()


def reset_failed():
    conn = _connect()
    conn.execute(
        "UPDATE domains SET status = 'pending', error = NULL WHERE status = 'failed'"
    )
    conn.commit()
    conn.close()


def get_all_results():
    conn = _connect()
    rows = conn.execute(
        "SELECT domain, status, result_json, error FROM domains"
    ).fetchall()
    conn.close()

    out = []
    for domain, status, result_json, error in rows:
        record = {"domain": domain, "status": status, "error": error}
        if result_json:
            record.update(json.loads(result_json))
        out.append(record)
    return out


def stats():
    conn = _connect()
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM domains GROUP BY status"
    ).fetchall()
    conn.close()
    return dict(rows)