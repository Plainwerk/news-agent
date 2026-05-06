# News-Agent — Projektkontext

## Projektziel

Ein automatisierter Pipeline-Agent, der RSS-Feeds aus deutschen Nachrichtenmedien quer durch das politische Spektrum (von links bis rechts, plus ÖRR und Agenturen) abruft, thematisch clustert und mittels Claude API analysiert.

Kernfrage pro Thema: **Was ist der gemeinsame Faktenkern? Wie unterscheidet sich das Framing? Welche Wortwahl wählen die einzelnen Häuser?**

Ziel ist eigenständige Meinungsbildung ohne vorgefertigte Einordnung.

---

## Aktueller Stand

### Phase 1 — RSS-Abruf ✅
`fetch_feeds.py` liest Quellen aus `sources.md`, fetcht RSS-Feeds und speichert Artikel als JSON in `data/`.

### Phase 2 — Themen-Clustering ✅
`cluster_topics.py` gruppiert Artikel via TF-IDF + Cosine-Similarity in Cluster, bewertet Spektrum-Breite.

### Phase 3 — Framing-Analyse (Claude API) ✅
`analyze_framing.py` analysiert pro Cluster: Faktenkern, Framing-Unterschiede, Wortwahl-Diff.
- Letzter Run: 35/38 Cluster erfolgreich (3 JSON-Parse-Fehler, mittlerweile mit `json_repair` gefixt)
- Ausgabe in `data/framing_*.json`

### Phase 4 — SQLite & App (in Arbeit)
Persistente Datenbank statt Einzel-JSONs, Streamlit-Viewer mit Filter/Suche.

---

## Technischer Stack

| Komponente | Technologie |
|---|---|
| Sprache | Python 3.14 |
| RSS-Parsing | feedparser |
| Clustering | scikit-learn (TF-IDF + Cosine-Similarity) |
| LLM-Analyse | Anthropic SDK (claude-sonnet-4-6) |
| Datenbank (Phase 4) | SQLite (stdlib) |
| App (Phase 4) | Streamlit |
| Umgebung | python-dotenv, .env für API-Key |

Datenfluss: `fetch_feeds.py` → `cluster_topics.py` → `analyze_framing.py` → (Phase 4: SQLite + Streamlit-App)

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
- [ ] Anthropic Support kontaktieren wegen Billing-Problem (gestern gelöst, evtl. trotzdem dokumentieren)
