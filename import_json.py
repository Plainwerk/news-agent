import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import db

DATA_DIR = "data"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_files(prefix):
    return sorted(
        os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR)
        if f.startswith(prefix) and f.endswith(".json")
        and os.path.getsize(os.path.join(DATA_DIR, f)) > 0
    )


def main():
    conn = db.get_connection()
    db.init_db(conn)

    print("News Agent — JSON → SQLite Import")
    print("=" * 40)

    article_files = find_files("articles_")
    print(f"\nFetch-Runs ({len(article_files)} Dateien):")
    for f in article_files:
        payload = load_json(f)
        run_id = db.save_fetch_run(conn, payload, f)
        print(f"  {os.path.basename(f)} → run_id={run_id} ({payload['article_count']} Artikel)")

    cluster_files = find_files("clusters_")
    print(f"\nCluster-Runs ({len(cluster_files)} Dateien):")
    for f in cluster_files:
        payload = load_json(f)
        run_id = db.save_cluster_run(conn, payload, f)
        print(f"  {os.path.basename(f)} → run_id={run_id} ({payload['cluster_count']} Cluster)")

    framing_files = find_files("framing_")
    print(f"\nAnalyse-Runs ({len(framing_files)} Dateien):")
    for f in framing_files:
        payload = load_json(f)
        run_id = db.save_analysis_run(conn, payload, f)
        print(f"  {os.path.basename(f)} → run_id={run_id} ({payload['cluster_count_analyzed']} analysiert)")

    conn.close()
    print("\nFertig.")


if __name__ == "__main__":
    main()
