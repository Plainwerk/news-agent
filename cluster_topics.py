import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


DATA_DIR = "data"
SIMILARITY_THRESHOLD = 0.20  # Erhöhen → weniger, schärfere Cluster; senken → mehr, breitere
MIN_CLUSTER_SIZE = 2

EXCLUDE_KEYWORDS = [
    "bundesliga", "champions league", "europa league", "formel 1", "formel1",
    "tour de france", "olympia", "weltmeisterschaft", "europameisterschaft",
    "fußball", "tennis", "basketball", "handball", "schwimmen", "leichtathletik",
    "oscars", "grammy", "golden globe", "fashion week", "berlinale",
    "rezept", "wetter", "horoskop", "tv-tipp", "fernsehen",
    "promi", "klatsch", "boulevard",
]


def find_latest_articles_file(data_dir=DATA_DIR):
    files = [
        os.path.join(data_dir, f) for f in os.listdir(data_dir)
        if f.startswith("articles_") and f.endswith(".json")
        and os.path.getsize(os.path.join(data_dir, f)) > 0
    ]
    if not files:
        raise FileNotFoundError(f"Keine articles_*.json in {data_dir}/ gefunden.")
    return max(files, key=os.path.getmtime)


def load_articles(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["articles"]


def is_excluded(title):
    if not title:
        return True
    title_lower = title.lower()
    return any(kw in title_lower for kw in EXCLUDE_KEYWORDS)


def build_clusters(sim_matrix, threshold):
    n = sim_matrix.shape[0]
    visited = [False] * n
    clusters = []
    for i in range(n):
        if visited[i]:
            continue
        group = [i]
        visited[i] = True
        queue = [i]
        while queue:
            node = queue.pop(0)
            for j in range(n):
                if not visited[j] and sim_matrix[node, j] >= threshold:
                    visited[j] = True
                    group.append(j)
                    queue.append(j)
        clusters.append(group)
    return clusters


def pick_label(indices, articles, sim_matrix):
    if len(indices) == 1:
        return articles[indices[0]].get("title") or ""
    best_idx = max(
        indices,
        key=lambda i: np.mean([sim_matrix[i, j] for j in indices if j != i]),
    )
    return articles[best_idx].get("title") or ""


def score_cluster(cluster_articles):
    labels = sorted({a["source_label"] for a in cluster_articles})
    spectrum_score = len(labels)
    relevance_score = spectrum_score * 10 + len(cluster_articles)
    return spectrum_score, relevance_score, labels


def main():
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = find_latest_articles_file()

    print("News Agent — Themen-Clustering")
    print("=" * 40)
    print(f"Eingabe: {input_file}")

    articles = load_articles(input_file)
    print(f"{len(articles)} Artikel geladen")

    filtered = [a for a in articles if not is_excluded(a.get("title"))]
    print(f"{len(articles) - len(filtered)} Artikel herausgefiltert (Sport/Kultur/Boulevard)")
    print(f"{len(filtered)} Artikel für Clustering\n")

    if len(filtered) < 2:
        print("Zu wenige Artikel für Clustering.")
        return

    titles = [a.get("title") or "" for a in filtered]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
    tfidf_matrix = vectorizer.fit_transform(titles)
    sim_matrix = cosine_similarity(tfidf_matrix)

    raw_clusters = build_clusters(sim_matrix, SIMILARITY_THRESHOLD)

    clusters = []
    for indices in raw_clusters:
        if len(indices) < MIN_CLUSTER_SIZE:
            continue
        cluster_articles = [filtered[i] for i in indices]
        label = pick_label(indices, filtered, sim_matrix)
        spectrum_score, relevance_score, spectrum_labels = score_cluster(cluster_articles)
        clusters.append({
            "label": label,
            "article_count": len(cluster_articles),
            "spectrum_score": spectrum_score,
            "spectrum_labels": spectrum_labels,
            "relevance_score": relevance_score,
            "articles": [
                {
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "source_name": a.get("source_name"),
                    "source_label": a.get("source_label"),
                    "published_at": a.get("published_at"),
                }
                for a in cluster_articles
            ],
        })

    clusters.sort(key=lambda c: c["relevance_score"], reverse=True)
    for i, c in enumerate(clusters, start=1):
        c["id"] = i

    clustered_count = sum(c["article_count"] for c in clusters)
    unclustered_count = len(filtered) - clustered_count

    timestamp = os.path.basename(input_file).replace("articles_", "").replace(".json", "")
    output_file = os.path.join(DATA_DIR, f"clusters_{timestamp}.json")

    payload = {
        "clustered_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": input_file,
        "cluster_count": len(clusters),
        "article_count_clustered": clustered_count,
        "article_count_unclustered": unclustered_count,
        "clusters": clusters,
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"{len(clusters)} Cluster gefunden")
    print(f"{unclustered_count} Artikel ohne Cluster (Einzelmeldungen)")
    print(f"Gespeichert: {output_file}\n")

    print("Top-5-Themen:")
    for c in clusters[:5]:
        print(f"  {c['id']}. \"{c['label']}\"")
        print(f"     {c['article_count']} Artikel · Spektrum: {c['spectrum_score']} ({', '.join(c['spectrum_labels'])})")


if __name__ == "__main__":
    main()
