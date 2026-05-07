# Prisma — Nachrichten ohne Filter

> Derselbe Fakt. Zwanzig Quellen. Zeig mir den Unterschied.

**Prisma** aggregiert RSS-Feeds aus dem gesamten deutschen Medienspektrum — von links bis rechts, plus ÖRR und Agenturen — gruppiert die Artikel nach Thema und analysiert per KI, wie jedes Medium das gleiche Ereignis rahmt.

Das Ziel: Eigenständige Meinungsbildung statt vorgefertigter Einordnung.

---

## Was Prisma macht

Für jedes Thema liefert Prisma drei Blöcke:

1. **Faktenkern** — Was ist passiert? (sachlich, max. 3 Sätze)
2. **Framing** — Wie rahmt jede Quelle das Ereignis? Mit Bias-Score auf einer Links–Rechts-Skala und Kontroversitätsampel (🟢 Konsens / 🟡 mittel / 🔴 hoch)
3. **Wortwahl-Diff** — Wie nennen die Medien dasselbe? ("Feuerpause" vs. "Waffenstillstand")

---

## Pipeline

```
fetch_feeds.py        → RSS-Feeds abrufen (20 Quellen)
      ↓
cluster_topics.py     → Artikel nach Thema gruppieren (TF-IDF + Cosine-Similarity)
      ↓
analyze_framing.py    → Framing-Analyse per Claude API (claude-sonnet-4-6)
      ↓
api.py                → FastAPI-Backend mit SQLite
      ↓
frontend/             → Vanilla-JS-App mit Bootstrap
```

---

## Quellen

20 RSS-Feeds quer durchs politische Spektrum:

| Spektrum | Quellen |
|---|---|
| Öffentlich-rechtlich | Tagesschau, ZDF heute |
| Links | taz, Neues Deutschland |
| Mitte-Links | Spiegel, Zeit Online, Süddeutsche, Der Standard |
| Mitte | FAZ, NZZ, Handelsblatt, Watson.ch |
| Mitte-Rechts | Die Welt, Cicero |
| Rechts | Junge Freiheit, Tichys Einblick |
| Agentur | n-tv (dpa) |
| International | BBC News Europe, Politico Europe, The Guardian |

Quellen sind in [`sources.md`](sources.md) konfiguriert — neue Feeds lassen sich ohne Code-Änderung ergänzen.

---

## Setup

### Voraussetzungen

- Python 3.10+
- [Anthropic API Key](https://console.anthropic.com/)

### Installation

```bash
git clone https://github.com/dein-name/news-agent.git
cd news-agent
pip install -r requirements.txt
```

### API-Key konfigurieren

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

### Pipeline ausführen

```bash
# 1. Feeds abrufen
python fetch_feeds.py

# 2. Themen clustern
python cluster_topics.py

# 3. Framing analysieren (Claude API — kostenpflichtig, ca. $0.50–$1.00 pro Run)
python analyze_framing.py

# 4. App starten
uvicorn api:app --reload
```

Dann im Browser öffnen: [http://localhost:8000](http://localhost:8000)

---

## Kosten

Die Framing-Analyse verwendet `claude-sonnet-4-6`. Ein typischer Run mit ~40–50 Clustern kostet ca. **$0.50–$1.00**.

Das Fetch- und Cluster-Skript ist kostenlos (kein API-Aufruf).

---

## Technischer Stack

| Komponente | Technologie |
|---|---|
| RSS-Parsing | feedparser |
| Clustering | scikit-learn (TF-IDF + Cosine-Similarity) |
| LLM-Analyse | Anthropic SDK (claude-sonnet-4-6) |
| Datenbank | SQLite |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla JS, Bootstrap 5, Inter |

---

## Projektstruktur

```
news-agent/
├── fetch_feeds.py        # RSS-Feeds abrufen
├── cluster_topics.py     # Themen-Clustering
├── analyze_framing.py    # Framing-Analyse via Claude API
├── api.py                # FastAPI-Backend
├── db.py                 # SQLite-Datenbankschicht
├── sources.md            # Quellen-Konfiguration
├── requirements.txt
└── frontend/
    ├── index.html
    ├── app.js
    └── assets/
```

---

## Ideen & Roadmap

- [ ] Automatischer Tages-Cron (fetch → cluster → analyze)
- [ ] Embedding-basiertes Clustering für bessere Themen-Erkennung
- [ ] Volltextanalyse statt nur Titel
- [ ] Mobile App
- [ ] Mehr internationale Quellen

---

## Urheberrecht

© 2025 Steffen Heinz — Alle Rechte vorbehalten.

Der Code darf eingesehen, aber nicht ohne ausdrückliche Genehmigung kopiert, verwendet oder weiterverbreitet werden.
