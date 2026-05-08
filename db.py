import hashlib
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
            framing        TEXT,
            bias_score     INTEGER
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
    # Migrationen: nicht-destruktive Spalten-Adds (idempotent dank try/except)
    for stmt in [
        "ALTER TABLE framing_sources ADD COLUMN bias_score INTEGER",
        "ALTER TABLE clusters ADD COLUMN content_hash TEXT",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Spalte existiert bereits

    # Indexe für Cache-Lookup-Performance
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_clusters_content_hash ON clusters(content_hash);
        CREATE INDEX IF NOT EXISTS idx_framing_results_cluster_id ON framing_results(cluster_id);
    """)
    conn.commit()

    # Einmalige Backfill: content_hash für Cluster die vor der Migration angelegt wurden
    _backfill_content_hashes(conn)


def _backfill_content_hashes(conn):
    """Setzt content_hash für Cluster nach, die ihn noch nicht haben (Migration)."""
    cluster_ids = [r[0] for r in conn.execute(
        "SELECT id FROM clusters WHERE content_hash IS NULL"
    ).fetchall()]
    if not cluster_ids:
        return 0

    count = 0
    for cid in cluster_ids:
        urls = [r[0] for r in conn.execute(
            "SELECT url FROM cluster_articles WHERE cluster_id=? AND url IS NOT NULL",
            (cid,)
        ).fetchall()]
        if not urls:
            continue
        chash = compute_cluster_hash([{"url": u} for u in urls])
        if chash:
            conn.execute("UPDATE clusters SET content_hash=? WHERE id=?", (chash, cid))
            count += 1
    if count > 0:
        conn.commit()
    return count


def compute_cluster_hash(articles):
    """Stabiler Inhalts-Hash eines Clusters basierend auf sortierten Artikel-URLs.
    Zwei Cluster mit denselben Artikeln → derselbe Hash, egal aus welchem Run."""
    urls = sorted(a.get("url", "") for a in articles if a.get("url"))
    if not urls:
        return None
    h = hashlib.sha256()
    for url in urls:
        h.update(url.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()[:16]


def find_cached_analysis(conn, content_hash):
    """Sucht eine vorherige erfolgreiche Framing-Analyse für denselben Cluster-Inhalt.
    Gibt das vollständige Analyse-Dict zurück oder None."""
    if not content_hash:
        return None
    fr = conn.execute("""
        SELECT fr.id, fr.faktenkern FROM framing_results fr
        JOIN clusters c ON fr.cluster_id = c.id
        WHERE c.content_hash = ? AND fr.error IS NULL AND fr.faktenkern IS NOT NULL
        ORDER BY fr.id DESC LIMIT 1
    """, (content_hash,)).fetchone()

    if not fr:
        return None

    sources = conn.execute(
        "SELECT quelle, spectrum_label, framing, bias_score FROM framing_sources WHERE result_id=?",
        (fr["id"],)
    ).fetchall()

    diffs = []
    for wd in conn.execute(
        "SELECT id, konzept FROM wortwahl_diffs WHERE result_id=?", (fr["id"],)
    ).fetchall():
        vars_ = conn.execute(
            "SELECT quelle, bezeichnung FROM wortwahl_vars WHERE diff_id=?", (wd["id"],)
        ).fetchall()
        diffs.append({
            "konzept": wd["konzept"],
            "varianten": [{"quelle": v["quelle"], "bezeichnung": v["bezeichnung"]} for v in vars_],
        })

    return {
        "faktenkern": fr["faktenkern"],
        "framing_unterschiede": [
            {"quelle": s["quelle"], "label": s["spectrum_label"],
             "framing": s["framing"], "bias_score": s["bias_score"]}
            for s in sources
        ],
        "wortwahl_diff": diffs,
    }


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
        chash = compute_cluster_hash(c["articles"])
        cur2 = conn.execute(
            """INSERT INTO clusters
               (run_id, local_id, label, spectrum_score, spectrum_labels, article_count, relevance_score, content_hash)
               VALUES (?,?,?,?,?,?,?,?)""",
            (run_id, c["id"], c["label"], c["spectrum_score"],
             json.dumps(c["spectrum_labels"], ensure_ascii=False),
             c["article_count"], c["relevance_score"], chash),
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
            if not fs.get("quelle") or not fs.get("framing"):
                continue  # skip incomplete entries (e.g. from truncated JSON)
            conn.execute(
                "INSERT INTO framing_sources (result_id, quelle, spectrum_label, framing, bias_score) VALUES (?,?,?,?,?)",
                (rid, fs["quelle"], fs.get("label"), fs["framing"], fs.get("bias_score")),
            )
        for wd in r.get("wortwahl_diff", []):
            if not wd.get("konzept"):
                continue
            cur3 = conn.execute(
                "INSERT INTO wortwahl_diffs (result_id, konzept) VALUES (?,?)",
                (rid, wd["konzept"]),
            )
            did = cur3.lastrowid
            for v in wd.get("varianten", []):
                if not v.get("quelle") or not v.get("bezeichnung"):
                    continue  # skip incomplete entries
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
