import json
import os
import sqlite3
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = os.path.join("data", "news_agent.db")

app = FastAPI(title="News Agent")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _parse_labels(raw):
    try:
        return json.loads(raw or "[]")
    except Exception:
        return []


def _parse_sources(raw):
    if not raw:
        return []
    seen = set()
    sources = []
    for entry in raw.split(','):
        parts = entry.split('|')
        if len(parts) < 2:
            continue
        name, label = parts[0].strip(), parts[1].strip()
        bias = int(parts[2]) if len(parts) > 2 and parts[2].strip().lstrip('-').isdigit() else None
        if name and name not in seen:
            seen.add(name)
            sources.append({"name": name, "label": label, "bias_score": bias})
    return sources


def _topic_dict(row):
    return {
        "id": row["id"],
        "label": row["label"],
        "spectrum_score": row["spectrum_score"],
        "spectrum_labels": _parse_labels(row["spectrum_labels"]),
        "article_count": row["article_count"],
        "relevance_score": row["relevance_score"],
        "faktenkern": row["faktenkern"],
        "framing_count": row["framing_count"],
        "sources": _parse_sources(row["sources_raw"]),
    }


_TOPICS_SELECT = """
    SELECT c.id, c.label, c.spectrum_score, c.spectrum_labels,
           c.article_count, c.relevance_score,
           fr.faktenkern,
           COUNT(fs.id) AS framing_count,
           GROUP_CONCAT(fs.quelle || '|' || COALESCE(fs.spectrum_label,'') || '|' || COALESCE(CAST(fs.bias_score AS TEXT),'')) AS sources_raw
    FROM clusters c
    JOIN cluster_runs cr ON c.run_id = cr.id
    LEFT JOIN framing_results fr ON fr.id = (
        SELECT MAX(id) FROM framing_results
        WHERE cluster_id = c.id AND error IS NULL
    )
    LEFT JOIN framing_sources fs ON fs.result_id = fr.id
"""


@app.get("/api/topics/today")
def topics_today():
    with get_db() as conn:
        row = conn.execute("SELECT MAX(id) AS id FROM cluster_runs").fetchone()
        if not row or row["id"] is None:
            return []
        latest = row["id"]
        rows = conn.execute(
            _TOPICS_SELECT + "WHERE cr.id = ? GROUP BY c.id ORDER BY c.relevance_score DESC",
            (latest,),
        ).fetchall()
    return [_topic_dict(r) for r in rows]


@app.get("/api/dates")
def dates():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT substr(clustered_at, 1, 10) AS date FROM cluster_runs ORDER BY date DESC"
        ).fetchall()
    return [r["date"] for r in rows]


@app.get("/api/topics")
def topics(label: str = None, date: str = None):
    with get_db() as conn:
        where = "WHERE 1=1"
        params: list = []
        if date:
            where += " AND cr.clustered_at LIKE ?"
            params.append(date + "%")
        if label:
            where += """ AND c.id IN (
                SELECT cc.id FROM clusters cc, json_each(cc.spectrum_labels)
                WHERE json_each.value = ?
            )"""
            params.append(label)
        rows = conn.execute(
            _TOPICS_SELECT + f"{where} GROUP BY c.id ORDER BY c.relevance_score DESC",
            params,
        ).fetchall()
    return [_topic_dict(r) for r in rows]


def _fetch_topic_data(conn, topic_id: int) -> dict:
    cluster = conn.execute("SELECT * FROM clusters WHERE id=?", (topic_id,)).fetchone()
    if not cluster:
        raise HTTPException(status_code=404, detail="Topic nicht gefunden")

    result = conn.execute(
        "SELECT * FROM framing_results WHERE cluster_id=? ORDER BY id DESC LIMIT 1",
        (topic_id,),
    ).fetchone()

    framing_sources = []
    wortwahl_diffs = []
    if result:
        framing_sources = conn.execute(
            "SELECT * FROM framing_sources WHERE result_id=?", (result["id"],)
        ).fetchall()
        for wd in conn.execute(
            "SELECT * FROM wortwahl_diffs WHERE result_id=?", (result["id"],)
        ).fetchall():
            vars_ = conn.execute(
                "SELECT * FROM wortwahl_vars WHERE diff_id=?", (wd["id"],)
            ).fetchall()
            wortwahl_diffs.append({
                "konzept": wd["konzept"],
                "varianten": [{"quelle": v["quelle"], "bezeichnung": v["bezeichnung"]} for v in vars_],
            })

    articles = conn.execute(
        "SELECT * FROM cluster_articles WHERE cluster_id=?", (topic_id,)
    ).fetchall()

    return {
        "id": topic_id,
        "label": cluster["label"],
        "spectrum_score": cluster["spectrum_score"],
        "spectrum_labels": _parse_labels(cluster["spectrum_labels"]),
        "article_count": cluster["article_count"],
        "faktenkern": result["faktenkern"] if result else None,
        "error": result["error"] if result else None,
        "framing_sources": [
            {
                "quelle": fs["quelle"],
                "spectrum_label": fs["spectrum_label"],
                "framing": fs["framing"],
                "bias_score": fs["bias_score"],
            }
            for fs in framing_sources
        ],
        "wortwahl_diffs": wortwahl_diffs,
        "articles": [
            {
                "title": a["title"],
                "url": a["url"],
                "source_name": a["source_name"],
                "source_label": a["source_label"],
            }
            for a in articles
        ],
    }


@app.get("/api/topics/{topic_id}/framing")
def topic_framing(topic_id: int):
    with get_db() as conn:
        return _fetch_topic_data(conn, topic_id)


@app.get("/api/topics/{topic_id}/export", response_class=PlainTextResponse)
def topic_export(topic_id: int):
    with get_db() as conn:
        data = _fetch_topic_data(conn, topic_id)

    lines = [
        f"THEMA: {data['label']}",
        f"Spektrum: {', '.join(data['spectrum_labels'])} · {data['article_count']} Artikel",
        "",
        "FAKTENKERN:",
        data.get("faktenkern") or "(keine Analyse verfügbar)",
        "",
    ]

    if data["framing_sources"]:
        lines.append("FRAMING:")
        for fs in data["framing_sources"]:
            lines.append(f"- {fs['quelle']} ({fs['spectrum_label']}): {fs['framing']}")
        lines.append("")

    if data["wortwahl_diffs"]:
        lines.append("WORTWAHL:")
        for wd in data["wortwahl_diffs"]:
            lines.append(f"- {wd['konzept']}:")
            for v in wd["varianten"]:
                lines.append(f'    {v["quelle"]}: "{v["bezeichnung"]}"')
        lines.append("")

    return "\n".join(lines)


# StaticFiles-Mount muss als letztes registriert werden
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
