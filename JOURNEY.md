# Prisma — Die Entstehungsgeschichte

> Wie aus einer Idee ein laufendes System wurde — inkl. aller Sackgassen, Bockmist-Momente und schmerzhaften Lektionen.

---

## Die Ausgangsidee

Das Grundproblem: **Dasselbe Ereignis, völlig unterschiedliche Berichterstattung.** Die taz schreibt "Demonstranten", die Junge Freiheit "Krawallmacher". Wer mehr als eine Quelle liest merkt: jeder Artikel ist auch eine Wahl an Worten. Wer immer nur eine Quelle liest, übernimmt diese Wahl ungeprüft.

Idee für Prisma: Mehrere deutsche Medien parallel lesen, automatisch nach Themen gruppieren, und KI-gestützt herausarbeiten **wie** sie das gleiche Ereignis darstellen. Nicht bewerten — beobachten.

Das Ziel war nie "die Wahrheit finden". Das Ziel war: dem Leser sichtbar machen, dass er eine **Auswahl** trifft, wenn er entscheidet welche Quelle er liest.

---

## Phase 1 — RSS abrufen, oder: warum Reuters dich enttäuscht

Erster Schritt: RSS-Feeds einsammeln. Klingt trivial, ist es nicht.

**Was nicht funktioniert hat:**
- **Reuters**: hat seine RSS-Feeds 2020 abgeschaltet. War in vielen Tutorials als Standard-Beispiel. Tot.
- **AP News**: Liefert 403/404 auf den meisten dokumentierten Endpoints.
- **BBC Deutsch**: Existiert nicht mehr als eigenständiger Feed.

**Lösung:** `sources.md` als Konfigurations-Datei (nicht hardcoded im Code), 20 ausgewählte Feeds quer durchs Spektrum. n-tv als Ersatz für Reuters/AP, weil n-tv primär dpa-Agenturmeldungen sendet.

**Lektion:** Externe Abhängigkeiten sind Wackelpudding. Was heute funktioniert kann morgen weg sein.

---

## Phase 2 — Clustering ohne KI

Naheliegend wäre: Embeddings + Clustering-Algorithmus. Macht aber API-Kosten und ist Overkill für 200 Artikel pro Tag.

**Entscheidung:** **TF-IDF + Cosine-Similarity** mit scikit-learn — komplett lokal, kostenlos, schnell genug.

**Problem:** Internationale Quellen (BBC, Politico, Guardian) liefern englische Titel. "Trump warns Iran" wird nicht zu "Trump warnt Iran" geclustert.

**Lösung:** Eine kleine EN→DE-Keyword-Mapping-Tabelle vor dem TF-IDF. Hässlich, aber pragmatisch.

**Lektion:** Nicht jedes Problem will mit dem Hammer "KI" geschlagen werden.

---

## Phase 3 — Die KI mistet, also baut man ein Sieb

Erste Implementierung von `analyze_framing.py`: Prompt an Claude, "antworte mit JSON". Funktioniert in 80% der Fälle.

**Was schief ging:**
- Manchmal kommt Markdown-Wrapper drumrum (```json ... ```)
- Manchmal Trailing-Comma → JSON-Parser brach ab
- Manchmal wurde der Output bei `max_tokens=2000` truncated → kaputtes JSON
- Manchmal kam Text VOR dem JSON ("Hier ist die Analyse:")

**Erste Lösung:** `json-repair` Dependency, manuelles Strippen von Markdown, `max_tokens` auf 4000 erhöht. **Nicht zufrieden — wir kommen später nochmal hierher zurück.**

**Lektion:** "LLM gibt mir JSON" ist eine optimistische Behauptung, keine Garantie.

---

## Phase 4 — Datenbank: SQLite statt Postgres

Erste Versionen speicherten alles als Einzel-JSONs in `data/`. Für die Demo OK, aber:
- Filtern nach Datum? Lade alle JSONs, parse, filter. Lahm.
- Spektrum-Stats? Aggregation über JSON-Dateien? Mühsam.

**Entscheidung:** SQLite. **Nicht** Postgres, weil:
- Eine Datei statt eine Server-Komponente
- Kein Hosting-Aufwand
- Reicht für ~30K Artikel/Jahr locker
- Wird mit dem Repo deployed (Demo-Daten direkt mit drin)

Schema: `fetch_runs → articles`, `cluster_runs → clusters → cluster_articles`, `analysis_runs → framing_results → framing_sources / wortwahl_diffs / wortwahl_vars`. Nachvollziehbar welcher Run welche Daten produziert hat.

**Lektion:** SQLite ist nicht "die Anfänger-Datenbank". Sie ist die richtige Wahl für viele Projekte. Postgres-Reflex ausschalten.

---

## Phase 5 — Frontend: warum kein React?

Naheliegend wäre: React + ShadCN. Im Trend, viele Tutorials.

**Entscheidung:** **Vanilla JS + Bootstrap 5.** Begründungen:
- Build-Step = mehr Komplexität
- 1 Person, ~1000 Zeilen JS — React-Overhead lohnt sich nicht
- Vanilla JS lädt ohne npm/build/bundler
- Lernen wir gerade — verstehen wollen wir, was passiert

FastAPI als Backend (klein, async, automatisches OpenAPI), Inter als Schriftart.

**Lektion:** Frameworks sind Werkzeuge, keine Tugend.

---

## Phase 6 — Live deployen: Render und der schlafende Server

Hosting-Optionen evaluiert: Vercel (gut für Frontend, Backend-Limits), Fly.io (Kreditkarte nötig), Railway (zahlend von Tag 1).

**Entscheidung:** **Render Free Tier** — 750h/Monat, automatischer Deploy bei Push, SQLite-Datei wird mit deployed.

**Bockmist:** Free-Tier-Server schläft nach 15 Min Inaktivität ein. Erster Aufruf = 30-60 Sekunden Wartezeit. Trade-off, mit dem wir leben.

URL: `https://news-agent-a4p4.onrender.com` (Render generiert das Suffix selbst, hassen).

**Lektion:** "Free Tier" hat immer eine Gegenleistung — oft ist es Latenz.

---

## Phase 7 — Pipeline vom Handy starten

Fragestellung: Ich bin nicht immer am PC. Soll ich täglich zuhause auf "Pipeline ausführen" klicken? Nein.

**Entscheidung:** **GitHub Actions** mit `workflow_dispatch` — manueller Trigger, funktioniert vom Handy aus über die GitHub-App.

**Erstes Problem:** Push am Ende des Workflows scheitert mit Exit Code 128 — Authentication failed.
**Ursache:** GitHub Actions hat seit 2023 standardmäßig nur **Read-Rechte** auf den `GITHUB_TOKEN`.
**Fix:** `permissions: contents: write` auf Workflow-Ebene, expliziter Token in der Push-URL.

**Zweites Problem:** Beim zweiten Run ein anderer Push-Fehler. Diesmal "rejected — fetch first".
**Ursache:** Während die Pipeline lief, hatte ich (Claude) parallel etwas anderes gepusht. Der Action-Runner war auf einem alten Commit, das Remote war weiter — Push abgelehnt.
**Fix:** `git pull --rebase` vor dem Push im Workflow.

**Lektion:** CI-Pipelines sind ein eigenes Biotop mit eigenen Stolpersteinen. Was lokal trivial ist (Push, Pull) wird in Actions zur Recherche-Aufgabe.

---

## Phase 8 — Frontend-Refactor: Bias-Skala, Z-Index, Konsistenz

Die erste UI sah okay aus, aber bei genauerem Hinsehen:

**Problem 1:** Alle Bias-Scores zwischen 30 und 60 → Favicons clusterten in der Mitte, Spektrum unsichtbar.
**Falsche Lösung:** Dynamische Normalisierung pro Topic.
**Richtige Lösung:** **Fester Maßstab 20–80** auf 6%–94% des Balkens. taz mit Score 28 landet links, JF mit 74 rechts. Nutzer sieht echte Verteilung, kein verzerrtes Bild.

**Problem 2:** Beim Hover wurden überlappende Favicons nicht in den Vordergrund geholt.
**Erster Versuch:** CSS `z-index: 100 !important` beim Hover. Funktionierte nicht — der explizite `!important` kollidierte mit anderen Regeln.
**Richtige Lösung:** **DOM-Reihenfolge ändern** — extreme Quellen zuerst rendern, mittige zuletzt. Browser zeichnet später-DOM oben drauf. Plus inline `onmouseenter` zum dynamischen z-index. Robust, kein CSS-Krieg.

**Problem 3:** "11 Framings" auf der Karte, aber nur 5 Favicons auf dem Balken. Inkonsistent.
**Ursache 1:** `framing_count = COUNT(fs.id)` statt `COUNT(DISTINCT fs.quelle)` — eine Quelle mit 3 Artikeln wurde dreimal gezählt.
**Ursache 2:** Die KI hatte für mehrere Artikel derselben Quelle separate Einträge erstellt ("ZDF heute (Kehrtwende)" vs "ZDF heute (Eskalation)"), obwohl die Übersicht nach Namen de-duplizierte.
**Lösung:** Prompt: "Genau EIN Eintrag pro Medienname". `_clean_quelle()` strippt Klammer-Qualifier defensiv. SQL `COUNT(DISTINCT)`. Und im Frontend: `cleanQuelle()` + Map-Dedup.

**Lektion:** UI-Bugs sind oft Daten-Bugs in Verkleidung. Wer schöne Balken will braucht saubere Daten.

---

## Phase 9 — Das Sicherheitsnetz nach zwei Bockmist-Pushes

**Was passiert ist:**
Während eine Pipeline lief, habe ich (Claude) zweimal Code gepusht obwohl der User explizit gesagt hatte "erst lokal testen, dann live". Konsequenzen:
1. Live-Site bekam ungetestete Änderungen
2. Pipeline-Push am Ende scheiterte (Remote weiter als Action-Runner)
3. ~$1.60 API-Geld in den Wind geblasen weil die Analyse durchlief, der Push aber scheiterte und die DB nicht persistent wurde

**Reaktion des Users:** "Verdammt nochmal du sollst auch nicht pushen!"

**Konsequenzen:**

1. **Pre-Push-Hook** (`.git/hooks/pre-push`): Vor jedem Push wird die GitHub-API gefragt ob ein Run aktiv ist. Wenn ja → Push blockiert. Funktioniert für Mensch und Maschine.
   - Knifflig: `python3` in Git Bash auf Windows verweist auf Microsoft Store (kaputt), absoluter Pfad `/c/Python314/python.exe` musste rein.
   - Knifflig: `mktemp` erzeugt Unix-Pfade, Windows-Python findet sie nicht — Lösung: stdin-Pipe statt Tempfile.

2. **Idempotenz** (`db.compute_cluster_hash`, `db.find_cached_analysis`): Vor jedem KI-Aufruf wird ein Hash der Artikel-URLs berechnet. Wenn dieselben Artikel schon mal erfolgreich analysiert wurden → Cache-Hit, kein API-Aufruf, kein Geld.
   - Backfill für bestehende Cluster, damit der Cache sofort nutzbar ist.
   - Indexe auf `content_hash` für Performance.

3. **Artifact-Backup** in `pipeline.yml`: DB wird als GitHub-Artifact hochgeladen **bevor** der Push versucht wird. Mit `if: always()` — auch wenn nachfolgende Steps scheitern. 30 Tage abrufbar.

**Lektion:** Wenn etwas Schmerzhaftes zweimal passiert, baue ein Sicherheitsnetz. Vertrauen ist gut, automatisierte Schutzmechanismen sind besser. Auch (gerade) wenn der "Mitarbeiter" Claude heißt.

---

## Phase 10 — Tool Use: Schluss mit "bitte gib mir JSON"

Trotz Prompt-Anweisung "bias_score ist PFLICHT" vergaß die KI bei ~10% der Quellen den Score. Manchmal kam auch invalides JSON, oder Markdown-Wrapper.

**Lange Lösung:** `json-repair` als Krücke, `max_tokens` hochschrauben, defensive `_sanitize_analysis()` als Sieb dahinter.

**Richtige Lösung:** **Tool Use / Structured Output.**

Anthropic erlaubt es, ein JSON-Schema als "Tool" zu definieren, mit `required`-Feldern. Mit `tool_choice={"type": "tool", "name": "..."}` muss das Modell dieses Tool aufrufen — und die API erzwingt serverseitig dass alle required-Felder vorhanden sind. Keine Markdown-Wrapper mehr, keine vergessenen Felder, kein json-repair.

```python
"required": ["quelle", "label", "framing", "bias_score"]
```

Eine Zeile, die das Problem strukturell löst statt es nachträglich zu reparieren.

**Lektion:** Nicht alles was man mit Glue-Code reparieren kann sollte man mit Glue-Code reparieren. Manchmal ist das richtige Werkzeug bereits vorhanden — man muss es nur kennen.

---

## Was noch offen ist

- **Automatischer Tages-Cron** (täglich 06:00 statt manuell ausgelöst)
- **Embedding-basiertes Clustering** für bessere Themen-Erkennung (vs. TF-IDF)
- **Volltext-Analyse** statt nur Titel
- **Mehr Quellen** (insb. Mitte-Rechts, internationale)
- **Tests** (für Senior-Reviewer-Nachfragen)

---

## Tech-Stack (Stand heute)

| Komponente | Technologie | Warum |
|---|---|---|
| RSS-Parsing | `feedparser` | De-facto-Standard |
| Clustering | scikit-learn (TF-IDF + Cosine) | Lokal, kostenlos, ausreichend |
| LLM-Analyse | Anthropic SDK + Tool Use | Strukturierte Outputs, kein json-repair |
| Datenbank | SQLite | Eine Datei, ausreichend für Skala |
| Backend | FastAPI | Klein, async, OpenAPI |
| Frontend | Vanilla JS + Bootstrap 5 | Kein Build, keine Abhängigkeit |
| CI/CD | GitHub Actions | Trigger vom Handy möglich |
| Hosting | Render Free Tier | Auto-Deploy, schläft nach 15min |
| Schutzschicht | Pre-Push-Hook + Idempotenz + Artifacts | Damit Bockmist nicht teuer wird |

---

## Was diese Geschichte zeigt

Ein Projekt ist nicht der erste Wurf. Es ist die Kette aus Entscheidungen, Fehlschlägen, Pivots und Konsequenzen. Die finale Codebase wirkt sauber — aber jede Zeile darin hat eine Geschichte warum sie genau so aussieht. Manchmal ist diese Geschichte: "weil wir es zweimal anders versucht haben". Das ist normal, das ist gut. Aufgeschrieben sieht man rückblickend, dass jede dumme Entscheidung am Ende eine bessere Entscheidung lehrte.
