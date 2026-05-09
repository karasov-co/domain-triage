import csv
import os
import time
import argparse
from datetime import datetime
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

from cache import init_db, add_domains, get_pending, save_result, save_failure, stats, get_all_results
from checker import check_domain
from scoring import calculate_score, get_priority_bucket, get_suggested_action

def load_seeds(path="seeds.csv"):
    domains = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            domain = row[0].strip()
            if not domain or domain.lower() in ("domain", "domains"):
                continue
            domains.append(domain)
    return domains

def process_domain(domain):
    try:
        facts = check_domain(domain)
        score, reason = calculate_score(facts)
        bucket = get_priority_bucket(score)
        action = get_suggested_action(score, facts)

        result = {
            **facts,
            "score": score,
            "score_1_10": round(score / 10),
            "reason": reason,
            "bucket": bucket,
            "action": action,
        }

        if facts.get("error"):
            save_failure(domain, facts["error"])
        else:
            save_result(domain, result)

        return result

    except Exception as e:
        save_failure(domain, f"pipeline_error: {type(e).__name__}: {e}")
        return None
    
def write_results_csv(results, path="output/results.csv"):
    fields = [
        "domain", "status", "score", "score_1_10", "bucket", "action",
        "http_status", "final_url", "response_time_ms",
        "title", "html_size", "tld", "spammy_tld", "is_parked",
        "reason", "error",
    ]
    sorted_results = sorted(
        results,
        key=lambda r: (r.get("status") != "done", -(r.get("score") or 0)),
    )

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in sorted_results:
            writer.writerow(r)
    print(f"      Wrote {len(sorted_results)} rows → {path}")

def write_failed_csv(results, path="output/failed.csv"):
    failed = [r for r in results if r.get("status") == "failed"]
    fields = ["domain", "error"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in failed:
            writer.writerow(r)
    print(f"      Wrote {len(failed)} rows → {path}")

def write_summary_md(results, elapsed_sec, path="output/summary.md"):
    total = len(results)
    done = [r for r in results if r.get("status") == "done"]
    failed = [r for r in results if r.get("status") == "failed"]

    bucket_counts = Counter(r.get("bucket") for r in done)
    action_counts = Counter(r.get("action") for r in done)
    error_counts = Counter(r.get("error") for r in failed).most_common(10)

    top_domains = sorted(done, key=lambda r: -(r.get("score") or 0))[:10]

    lines = []
    lines.append(f"# Domain Triage — Summary")
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"\n## Overview")
    lines.append(f"- **Total domains:** {total}")
    lines.append(f"- **Successfully processed:** {len(done)}")
    lines.append(f"- **Failed:** {len(failed)}")
    lines.append(f"- **Elapsed:** {elapsed_sec:.1f} sec ({total/elapsed_sec:.1f} dom/s)")

    lines.append(f"\n## Priority buckets")
    for bucket in ("high", "medium", "low", "skip"):
        lines.append(f"- **{bucket}:** {bucket_counts.get(bucket, 0)}")

    lines.append(f"\n## Suggested actions")
    for action, count in action_counts.most_common():
        lines.append(f"- `{action}`: {count}")

    lines.append(f"\n## Top 10 domains by score")
    lines.append(f"\n| Domain | Score | Bucket | Action | Title |")
    lines.append(f"|---|---|---|---|---|")
    for r in top_domains:
        title = (r.get("title") or "")[:50].replace("|", "/")
        lines.append(
            f"| {r['domain']} | {r.get('score_1_10')} | {r['bucket']} | {r['action']} | {title} |"
        )

    lines.append(f"\n## Top errors")
    if error_counts:
        for err, count in error_counts:
            lines.append(f"- `{err}`: {count}")
    else:
        lines.append("- No failures 🎉")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"      Wrote summary → {path}")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Domain Triage — оценивает список доменов и выдаёт отчёт."
    )
    parser.add_argument(
        "--seeds",
        default="seeds.csv",
        help="Путь к CSV-файлу со списком доменов (по умолчанию: seeds.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Обработать только первые N доменов (для тестов)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Количество параллельных потоков (по умолчанию: 10)",
    )
    parser.add_argument(
        "--rerun-failed",
        action="store_true",
        help="Перевести failed-домены обратно в pending и обработать заново",
    )
    return parser.parse_args()

def main():
    args = parse_args()
    t0 = time.time()

    print("[1/5] Init DB...")
    init_db()

    print("[2/5] Loading seeds...")
    domains = load_seeds(args.seeds)
    if args.limit:
        domains = domains[:args.limit]
        print(f"      Limit applied: using only first {args.limit} domains")
    print(f"      Loaded {len(domains)} domains")

    print("[3/5] Adding to cache...")
    add_domains(domains)

    if args.rerun_failed:
        from cache import reset_failed
        reset_failed()
        print("      Reset failed → pending (--rerun-failed)")

    pending = get_pending()
    print(f"      Pending: {len(pending)} domains")

    if not pending:
        print("\n[!] Nothing to process. All domains already done.")
        print("    Use --rerun-failed to retry failures, or rm cache.db to start fresh.")
        elapsed = time.time() - t0
    else:
        print(f"[4/5] Processing in parallel ({args.workers} workers)...")
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_domain, d): d for d in pending}
            for future in tqdm(as_completed(futures), total=len(futures), desc="Checking"):
                domain = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"\n[!] Unexpected error for {domain}: {e}")
        elapsed = time.time() - t0

    print(f"[5/5] Writing output...")
    os.makedirs("output", exist_ok=True)
    results = get_all_results()
    write_results_csv(results)
    write_failed_csv(results)
    write_summary_md(results, elapsed)

    print(f"\n=== Done in {elapsed:.1f}s ===")
    print("Stats:", stats())

if __name__ == "__main__":
    main()