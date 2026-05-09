import sqlite3
import json

DB_PATH = "cache.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        "INSERT OR IGNORE INTO domains (domain, status) VALUES (?, 'pending')",
        [(d,) for d in domains]
    )
    conn.commit()
    conn.close()


def get_pending():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT domain FROM domains WHERE status = 'pending'"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_result(domain, result):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE domains SET status = 'done', result_json = ? WHERE domain = ?",
        (json.dumps(result, ensure_ascii=False), domain)
    )
    conn.commit()
    conn.close()


def save_failure(domain, error):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE domains SET status = 'failed', error = ? WHERE domain = ?",
        (error, domain)
    )
    conn.commit()
    conn.close()


def reset_failed():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE domains SET status = 'pending', error = NULL WHERE status = 'failed'"
    )
    conn.commit()
    conn.close()


def get_all_results():
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM domains GROUP BY status"
    ).fetchall()
    conn.close()
    return dict(rows)