# News-Agent — Projektkontext

## Projektziel

Ein automatisierter Pipeline-Agent, der RSS-Feeds aus deutschen Nachrichtenmedien quer durch das politische Spektrum (von links bis rechts, plus ÖRR und Agenturen) abruft, thematisch clustert und mittels Claude API analysiert.

Kernfrage pro Thema: **Was ist der gemeinsame Faktenkern? Wie unterscheidet sich das Framing? Welche Wortwahl wählen die einzelnen Häuser?**

Ziel ist eigenständige Meinungsbildung ohne vorgefertigte Einordnung.

---

## Aktueller Stand

### Phase 1 — RSS-Abruf ✅
`fetch_feeds.py` liest Quellen aus `sources.md`, fetcht RSS-Feeds und speichert Artikel als JSON in `data/`.
- 20 Quellen quer durchs Spektrum

### Phase 2 — Themen-Clustering ✅
`cluster_topics.py` gruppiert Artikel via TF-IDF + Cosine-Similarity in Cluster, bewertet Spektrum-Breite.

### Phase 3 — Framing-Analyse (Claude API) ✅
`analyze_framing.py` analysiert pro Cluster: Faktenkern, Framing-Unterschiede, Wortwahl-Diff.
- Modell: claude-sonnet-4-6
- Typisch: ~40–50 Cluster pro Run, davon ~40 mit Spektrum-Breite ≥ 2 analysiert
- Kosten: ca. $0.50–$1.00 pro Run
- Ausgabe in `data/framing_*.json` + SQLite

### Phase 4 — Backend & Frontend ✅
- `db.py`: SQLite-Persistenz (fetch_runs, clusters, framing_results, framing_sources, wortwahl_diffs)
- `api.py`: FastAPI-Backend mit Endpunkten für Topics, Framing, Export
- `frontend/`: Vanilla JS + Bootstrap 5 App mit Bias-Balken, Wortwahl-Diff, Favicon-Hover

### Phase 5 — Deployment & Automation ✅
- Hosting: Render (Free Tier), https://news-agent-a4p4.onrender.com
- CI/CD: GitHub Actions (`workflow_dispatch`) — Pipeline per Knopfdruck vom Handy startbar
- Auto-Deploy: Render deployt bei jedem Push auf `master`

---

## Technischer Stack

| Komponente | Technologie |
|---|---|
| Sprache | Python 3.11+ |
| RSS-Parsing | feedparser |
| Clustering | scikit-learn (TF-IDF + Cosine-Similarity) |
| LLM-Analyse | Anthropic SDK (claude-sonnet-4-6) |
| Datenbank | SQLite (stdlib) |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla JS, Bootstrap 5, Inter |
| CI/CD | GitHub Actions |
| Hosting | Render |

Datenfluss: `fetch_feeds.py` → `cluster_topics.py` → `analyze_framing.py` → `db.py` → `api.py` + `frontend/`

---

## Persönlicher Kontext

**Steffen Heinz**, 40, Rauenberg (Baden-Württemberg)

- Wing-Studium (ohne Abschluss)
- Gelernter Fotograf
- Arbeitslos seit 1.1.2026
- Plant Selbstständigkeit als **Immobilienfotograf mit KI-Pipeline**
- Frau verbeamtet (A13), ein Sohn
- ALG1: 360 €/Monat
- **Gründungszuschuss-Zeitfenster** läuft bis ca. August 2026
- Fernstudium **Digital Engineering** angestrebt (Wilhelm Büchner oder IU Internationale Hochschule)

### Offene TODOs

- [ ] IHK anrufen (Beratung Gründung / Businessplan)
- [ ] Makler-Kontakte reaktivieren (für Immobilienfotografie-Aufträge)
- [ ] Fernuni nachhaken (Zulassung / Studienberatung)
