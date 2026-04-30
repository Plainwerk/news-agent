import json
import os
import sqlite3

DB_PATH = os.path.join("data", "news_agent.db")


def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS fetch_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at  TEXT NOT NULL,
            source_count INTEGER,
            article_count INTEGER,
            output_file TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS articles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER REFERENCES fetch_runs(id),
            title       TEXT,
            url         TEXT,
            source_name TEXT,
            source_label TEXT,
            published_at TEXT,
            summary     TEXT
        );
        CREATE TABLE IF NOT EXISTS cluster_runs (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_run_id            INTEGER REFERENCES fetch_runs(id),
            clustered_at            TEXT NOT NULL,
            cluster_count           INTEGER,
            article_count_clustered INTEGER,
            article_count_unclustered INTEGER,
            source_file             TEXT,
            output_file             TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS clusters (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id         INTEGER REFERENCES cluster_runs(id),
            local_id       INTEGER,
            label          TEXT,
            spectrum_score INTEGER,
            spectrum_labels TEXT,
            article_count  INTEGER,
            relevance_score INTEGER
        );
        CREATE TABLE IF NOT EXISTS cluster_articles (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id   INTEGER REFERENCES clusters(id),
            title        TEXT,
            url          TEXT,
            source_name  TEXT,
            source_label TEXT,
            published_at TEXT
        );
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_run_id        INTEGER REFERENCES cluster_runs(id),
            analyzed_at           TEXT NOT NULL,
            model                 TEXT,
            cluster_count_analyzed INTEGER,
            error_count           INTEGER,
            total_cost_usd        REAL,
            source_file           TEXT,
            output_file           TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS framing_results (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id     INTEGER REFERENCES analysis_runs(id),
            cluster_id INTEGER REFERENCES clusters(id),
            faktenkern TEXT,
            error      TEXT
        );
        CREATE TABLE IF NOT EXISTS framing_sources (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id      INTEGER REFERENCES framing_results(id),
            quelle         TEXT,
            spectrum_label TEXT,
            framing        TEXT
        );
        CREATE TABLE IF NOT EXISTS wortwahl_diffs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER REFERENCES framing_results(id),
            konzept   TEXT
        );
        CREATE TABLE IF NOT EXISTS wortwahl_vars (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            diff_id     INTEGER REFERENCES wortwahl_diffs(id),
            quelle      TEXT,
            bezeichnung TEXT
        );
    """)
    conn.commit()


def _norm(path):
    return os.path.normpath(path).replace("\\", "/") if path else None


def save_fetch_run(conn, payload, output_file):
    out = _norm(output_file)
    cur = conn.execute(
        "INSERT OR IGNORE INTO fetch_runs (fetched_at, source_count, article_count, output_file) VALUES (?,?,?,?)",
        (payload["fetched_at"], payload["source_count"], payload["article_count"], out),
    )
    conn.commit()
    if cur.lastrowid == 0:
        return conn.execute("SELECT id FROM fetch_runs WHERE output_file=?", (out,)).fetchone()["id"]
    run_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO articles (run_id, title, url, source_name, source_label, published_at, summary) VALUES (?,?,?,?,?,?,?)",
        [
            (run_id, a["title"], a["url"], a["source_name"], a["source_label"],
             a.get("published_at"), a.get("summary"))
            for a in payload["articles"]
        ],
    )
    conn.commit()
    return run_id


def save_cluster_run(conn, payload, output_file):
    out = _norm(output_file)
    src = _norm(payload.get("source_file"))
    row = conn.execute("SELECT id FROM fetch_runs WHERE output_file=?", (src,)).fetchone()
    fetch_run_id = row["id"] if row else None

    cur = conn.execute(
        """INSERT OR IGNORE INTO cluster_runs
           (fetch_run_id, clustered_at, cluster_count, article_count_clustered,
            article_count_unclustered, source_file, output_file)
           VALUES (?,?,?,?,?,?,?)""",
        (fetch_run_id, payload["clustered_at"], payload["cluster_count"],
         payload["article_count_clustered"], payload.get("article_count_unclustered"), src, out),
    )
    conn.commit()
    if cur.lastrowid == 0:
        return conn.execute("SELECT id FROM cluster_runs WHERE output_file=?", (out,)).fetchone()["id"]
    run_id = cur.lastrowid

    for c in payload["clusters"]:
        cur2 = conn.execute(
            """INSERT INTO clusters
               (run_id, local_id, label, spectrum_score, spectrum_labels, article_count, relevance_score)
               VALUES (?,?,?,?,?,?,?)""",
            (run_id, c["id"], c["label"], c["spectrum_score"],
             json.dumps(c["spectrum_labels"], ensure_ascii=False),
             c["article_count"], c["relevance_score"]),
        )
        cid = cur2.lastrowid
        conn.executemany(
            """INSERT INTO cluster_articles
               (cluster_id, title, url, source_name, source_label, published_at)
               VALUES (?,?,?,?,?,?)""",
            [(cid, a["title"], a["url"], a["source_name"], a["source_label"], a.get("published_at"))
             for a in c["articles"]],
        )
    conn.commit()
    return run_id


def save_analysis_run(conn, payload, output_file):
    out = _norm(output_file)
    src = _norm(payload.get("source_file"))
    row = conn.execute("SELECT id FROM cluster_runs WHERE output_file=?", (src,)).fetchone()
    cluster_run_id = row["id"] if row else None

    cur = conn.execute(
        """INSERT OR IGNORE INTO analysis_runs
           (cluster_run_id, analyzed_at, model, cluster_count_analyzed,
            error_count, total_cost_usd, source_file, output_file)
           VALUES (?,?,?,?,?,?,?,?)""",
        (cluster_run_id, payload["analyzed_at"], payload["model"],
         payload["cluster_count_analyzed"], payload["error_count"],
         payload["estimated_cost_usd"], src, out),
    )
    conn.commit()
    if cur.lastrowid == 0:
        return conn.execute("SELECT id FROM analysis_runs WHERE output_file=?", (out,)).fetchone()["id"]
    run_id = cur.lastrowid

    for r in payload["results"]:
        cid = _find_cluster_id(conn, cluster_run_id, r["cluster_id"])
        if "error" in r and "faktenkern" not in r:
            conn.execute(
                "INSERT INTO framing_results (run_id, cluster_id, error) VALUES (?,?,?)",
                (run_id, cid, r["error"]),
            )
            continue
        cur2 = conn.execute(
            "INSERT INTO framing_results (run_id, cluster_id, faktenkern) VALUES (?,?,?)",
            (run_id, cid, r.get("faktenkern")),
        )
        rid = cur2.lastrowid
        for fs in r.get("framing_unterschiede", []):
            conn.execute(
                "INSERT INTO framing_sources (result_id, quelle, spectrum_label, framing) VALUES (?,?,?,?)",
                (rid, fs["quelle"], fs.get("label"), fs["framing"]),
            )
        for wd in r.get("wortwahl_diff", []):
            cur3 = conn.execute(
                "INSERT INTO wortwahl_diffs (result_id, konzept) VALUES (?,?)",
                (rid, wd["konzept"]),
            )
            did = cur3.lastrowid
            for v in wd.get("varianten", []):
                conn.execute(
                    "INSERT INTO wortwahl_vars (diff_id, quelle, bezeichnung) VALUES (?,?,?)",
                    (did, v["quelle"], v["bezeichnung"]),
                )
    conn.commit()
    return run_id


def _find_cluster_id(conn, cluster_run_id, local_id):
    if cluster_run_id is None:
        return None
    row = conn.execute(
        "SELECT id FROM clusters WHERE run_id=? AND local_id=?",
        (cluster_run_id, local_id),
    ).fetchone()
    return row["id"] if row else None
