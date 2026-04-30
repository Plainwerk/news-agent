import feedparser
import html
import json
import os
import re
import socket
from datetime import datetime, timezone

import db


SOURCES_FILE = "sources.md"
DATA_DIR = "data"


def load_sources(path=SOURCES_FILE):
    sources = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            if set(line.replace("|", "").replace(" ", "")) <= {"-"}:
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) != 3:
                continue
            name, url, label = parts
            if name.lower() == "name":
                continue
            if url.startswith("http"):
                sources.append({"name": name, "url": url, "label": label})
    return sources


def fetch_feed(source):
    try:
        socket.setdefaulttimeout(15)
        feed = feedparser.parse(source["url"], agent="news-agent/1.0")
        if feed.bozo and len(feed.entries) == 0:
            return [], f"Kein Inhalt: {type(feed.bozo_exception).__name__}"

        articles = []
        for entry in feed.entries:
            title = entry.get("title") or None
            url = entry.get("link") or None

            summary = entry.get("summary") or entry.get("description") or None
            if summary:
                summary = re.sub(r"<[^>]+>", " ", summary)
                summary = html.unescape(summary)
                summary = re.sub(r"\s+", " ", summary).strip() or None

            published_at = None
            if entry.get("published_parsed"):
                try:
                    published_at = datetime(
                        *entry.published_parsed[:6], tzinfo=timezone.utc
                    ).isoformat()
                except Exception:
                    pass

            articles.append({
                "title": title,
                "url": url,
                "source_name": source["name"],
                "source_label": source["label"],
                "published_at": published_at,
                "summary": summary,
            })
        return articles, None

    except Exception as e:
        return [], str(e)


def save_articles(all_articles, errors, source_count):
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = os.path.join(DATA_DIR, f"articles_{timestamp}.json")
    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "source_count": source_count,
        "article_count": len(all_articles),
        "errors": errors,
        "articles": all_articles,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filename, payload


def main():
    print("News Agent — RSS Fetch")
    print("=" * 40)

    sources = load_sources()
    print(f"{len(sources)} Quellen geladen aus {SOURCES_FILE}\n")

    all_articles = []
    errors = {}

    for source in sources:
        print(f"  Abrufen: {source['name']} ...", end=" ", flush=True)
        articles, error = fetch_feed(source)
        if error:
            print(f"FEHLER ({error})")
            errors[source["name"]] = error
        else:
            print(f"{len(articles)} Artikel")
            all_articles.extend(articles)

    print()
    filename, payload = save_articles(all_articles, errors, len(sources))

    print(f"Gespeichert: {filename}")
    print(f"Artikel gesamt: {len(all_articles)}")
    if errors:
        print(f"Fehler bei {len(errors)} Quelle(n): {', '.join(errors.keys())}")
    else:
        print("Alle Quellen erfolgreich abgerufen.")

    try:
        conn = db.get_connection()
        db.init_db(conn)
        db.save_fetch_run(conn, payload, filename)
        conn.close()
        print("DB: gespeichert")
    except Exception as e:
        print(f"DB-Warnung: {e}")


if __name__ == "__main__":
    main()
