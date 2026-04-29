# News Agent

Ein Python-Skript, das RSS-Feeds aus deutschen Medien quer durchs politische Spektrum abruft und aufbereitet — von links bis rechts, plus ÖRR und Agenturen.

## Ziel

Zu jedem wichtigen Thema verschiedene Perspektiven nebeneinander sehen:
Was ist der gemeinsame Faktenkern? Wie unterscheidet sich das Framing? Welche Wortwahl wählen die einzelnen Häuser?

Ziel ist eigenständige Meinungsbildung — keine vorgefertigte Einordnung.

## Phasen

### Phase 1 — RSS-Abruf ✅
RSS-Feeds aus `sources.md` abrufen, Artikel mit Metadaten (Titel, URL, Quelle, Spektrum-Label, Datum) als JSON speichern.

### Phase 2 — Themen-Clustering
Artikel nach Ereignis gruppieren, sodass pro Thema sichtbar ist, wer was berichtet hat.

### Phase 3 — Framing-Analyse (Claude API)
Pro Cluster drei Blöcke:
1. Gemeinsamer Faktenkern (max. 3 Sätze)
2. Was nur bestimmte Häuser zusätzlich betonen
3. Wortwahl-Diff (wie nennen die Häuser dasselbe?)

### Phase 4 — SQLite & App
Persistente Datenbank statt JSON, Themen-Filter, App-Anbindung, YouTube-Pipeline.

## Quellen-Konfiguration

Alle Feeds sind in `sources.md` definiert. Dort lassen sich Quellen leicht ergänzen oder entfernen — das Fetch-Skript liest sie automatisch ein.

## Setup

```bash
pip install -r requirements.txt
```

## Nutzung

```bash
python fetch_feeds.py
```

Artikel werden im Ordner `data/` als JSON-Dateien abgelegt.

## Projektstruktur

```
news-agent/
├── README.md           # Diese Datei
├── sources.md          # Quellen-Konfiguration (Name, Feed-URL, Spektrum-Label)
├── requirements.txt    # Python-Abhängigkeiten
├── fetch_feeds.py      # Haupt-Skript: RSS abrufen und als JSON speichern
└── data/               # Ausgabe-Ordner (wird von .gitignore ausgeschlossen)
```
