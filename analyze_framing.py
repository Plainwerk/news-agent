import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

import db

DATA_DIR = "data"
MODEL = "claude-sonnet-4-6"
MIN_SPECTRUM_SCORE = 2
CLI_TIMEOUT = 180  # Sekunden pro Cluster-Analyse (ohne Thinking ~20-60s)

# Tools, die Claude Code für einen reinen JSON-Extraktions-Task nie braucht.
# Verhindert teure Umwege (z.B. WebSearch zu Nachrichtenthemen).
DISALLOWED_TOOLS = [
    "WebSearch", "WebFetch", "Bash", "Read", "Glob", "Grep", "Edit", "Write", "TodoWrite",
]

# Wie viele Cluster gleichzeitig analysiert werden (jeder Call ist ein eigener
# claude-Prozess). 4 ist ein guter Kompromiss aus Tempo und Abo-Last; per
# Umgebungsvariable überschreibbar.
CONCURRENCY = int(os.environ.get("PRISMA_CONCURRENCY", "4"))

SYSTEM_PROMPT = """Du bist ein Werkzeug für Medienanalyse. Deine Aufgabe ist Beobachten, nicht Bewerten. Du beschreibst was sprachlich passiert — du interpretierst nicht, was es bedeutet.

Du bekommst Artikel-Titel mehrerer deutscher Medien zum selben Ereignis. Wichtig: Du analysierst ausschließlich diese Titel, nicht den allgemeinen Ruf der Quelle.

EINGABEFORMAT — wichtig zu verstehen:
Jede Artikelzeile beginnt mit "[Medienname / Spektrum-Label]" gefolgt vom Titel.
Beispiel: "[Tagesschau / öRR] Bilanz nach einem Jahr Schwarz-Rot"
→ Medienname = "Tagesschau", Spektrum-Label = "öRR", Titel = "Bilanz nach einem Jahr Schwarz-Rot"

In deiner JSON-Antwort sind quelle und label IMMER ZWEI GETRENNTE FELDER:
   "quelle": "Tagesschau"     ← NUR der Medienname, OHNE " / Label"
   "label":  "öRR"             ← NUR das Spektrum-Label

Antworte ausschließlich mit gültigem JSON in folgendem Format (kein Markdown, kein Kommentar davor oder danach):
{
  "faktenkern": "Was ist passiert? Nur gesicherte Fakten, 3-5 Sätze, ohne Wertung.",
  "framing_unterschiede": [
    {
      "quelle": "NUR der Medienname, z.B. 'Tagesschau' oder 'Junge Freiheit'",
      "label": "NUR das Spektrum-Label, z.B. 'links', 'mitte-rechts', 'öRR'",
      "framing": "Konkrete sprachliche Beobachtung dieses Titels, 3-5 Sätze.",
      "bias_score": 50
    }
  ],
  "wortwahl_diff": [
    {
      "konzept": "Was wird unterschiedlich benannt? (z.B. 'Bezeichnung der Person', 'Name des Vorgangs')",
      "varianten": [
        {"quelle": "Medienname", "bezeichnung": "exakter Begriff aus dem Titel"}
      ]
    }
  ]
}

═══════════════ REGELN ═══════════════

▸ FRAMING: Beschreibe konkret, was DIESER Titel sprachlich tut.

  Achte auf:
   • Wer wird als Subjekt/Handelnder genannt? Wer als Objekt/Opfer?
   • Welches Verb wird verwendet (aktiv/passiv, sachlich/emotional)?
   • Welche wertenden Adjektive oder Qualifikatoren stehen drin?
   • Was lässt der Titel weg, das andere Titel erwähnen?
   • Wird ein Aspekt des Ereignisses besonders hervorgehoben?

  Zitiere auffällige Begriffe direkt in 'einfachen Anführungszeichen'.

  TECHNISCH WICHTIG: Innerhalb der JSON-String-Werte NIEMALS gerade doppelte
  Anführungszeichen (") verwenden — sie zerbrechen das JSON. Für zitierte
  Begriffe ausschließlich einfache Anführungszeichen ' benutzen.

  NICHT erlaubt — das sind Interpretationen:
    ✗ "berichtet kritisch"
    ✗ "zeigt sich besorgt"
    ✗ "stellt positiv dar"
    ✗ "nimmt eine konservative Haltung ein"

  ERLAUBT — das sind Beobachtungen:
    ✓ "Verwendet den Begriff 'Versagen' statt 'Verzögerung'"
    ✓ "Nennt die Demonstranten 'Aktivisten', erwähnt keine Sachschäden"
    ✓ "Stellt das Opfer ins Subjekt, der Täter wird nur passiv erwähnt"
    ✓ "Hebt wirtschaftliche Folgen hervor, lässt humanitäre Aspekte weg"

▸ WORTWAHL_DIFF: Suche aktiv nach sprachlichen Unterschieden zwischen den Titeln. Sei gründlich — auch subtile Unterschiede zählen.

  Typische Kategorien von Unterschieden (das sind BEISPIELE, nicht alles):
   • Verben: töten / ermorden / sterben / umkommen / hinrichten
   • Tätigkeiten: protestieren / demonstrieren / randalieren / aufbegehren
   • Personenbezeichnungen: Aktivist / Demonstrant / Krawallmacher / Anhänger
   • Ereignisnamen: Aufstand / Revolte / Unruhen / Protest / Krise
   • Bewegungs-/Handlungsverben: verfolgen / jagen / nachsetzen / fahnden
   • Wertende Adjektive: rechtsextrem / national-konservativ / patriotisch
   • Tatbeschreibungen: Anschlag / Vorfall / Tat / Übergriff / Angriff

  Aufgaben:
   1. Identifiziere Konzepte (Person, Handlung, Ereignis), die in mehreren Titeln vorkommen
   2. Vergleiche, wie unterschiedliche Quellen diese benennen
   3. Trage jede gefundene Variation ein

  Bei jeder Variante: exakter Begriff aus dem Titel, nicht umschrieben.
  Leer [] nur wenn Titel wirklich identische Sprache verwenden.

▸ BIAS_SCORE: Bewerte ausschließlich diesen einen Titel.

  Skala 0-100:
   •   0 = das linke Extrem (politisch-emotional aufgeladen, klar links)
   •  50 = sachlich-neutral, keine erkennbare politische Rahmung
   • 100 = das rechte Extrem (politisch-emotional aufgeladen, klar rechts)

  WICHTIG: Das Medium spielt KEINE Rolle.
   • Junge Freiheit schreibt einen sachlichen Wirtschafts-Titel → 50
   • taz schreibt einen sachlichen Wirtschafts-Titel → 50
   • Junge Freiheit schreibt einen emotional aufgeladenen Migrations-Titel → 80-90
   • taz schreibt einen emotional aufgeladenen Sozialgerechtigkeits-Titel → 10-20

  Bewertung anhand des Titels selbst — nicht anhand des erwarteten Ruf der Quelle. Wenn ein Titel komplett neutral und sachlich ist, vergib 50, egal welches Medium ihn geschrieben hat.

  Nutze die volle Skala. Bei mehreren ähnlich-gelagerten Titeln dürfen Scores natürlich nah beieinander liegen.

  PFLICHT: Jeder Eintrag in framing_unterschiede MUSS ein bias_score enthalten. Kein Eintrag ohne bias_score.

▸ framing_unterschiede: Genau EIN Eintrag pro Medienname. Wenn eine Quelle mehrere Titel beigetragen hat, fasse ihr Framing in EINEM Eintrag zusammen — kein "(Kehrtwende)", "(Teil 2)" o.ä. im quelle-Feld. Nur Quellen aufführen, die tatsächlich eigene Artikel beigetragen haben.

▸ Antworte auf Deutsch."""


def find_latest_clusters_file(data_dir=DATA_DIR):
    files = [
        os.path.join(data_dir, f) for f in os.listdir(data_dir)
        if f.startswith("clusters_") and f.endswith(".json")
        and os.path.getsize(os.path.join(data_dir, f)) > 0
    ]
    if not files:
        raise FileNotFoundError(f"Keine clusters_*.json in {data_dir}/ gefunden.")
    return max(files, key=os.path.getmtime)


def load_clusters(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_cluster_prompt(cluster):
    lines = [
        f'Thema: "{cluster["label"]}"',
        f'Artikel-Anzahl: {cluster["article_count"]}',
        f'Politisches Spektrum vertreten: {", ".join(cluster["spectrum_labels"])}',
        "",
        "Artikel-Titel nach Quelle:",
    ]
    for a in cluster["articles"]:
        lines.append(f'  [{a["source_name"]} / {a["source_label"]}] {a["title"]}')
    return "\n".join(lines)


def _clean_quelle(name):
    """Bereinigt KI-generierte Quellennamen:
    - 'Tagesschau / öRR' → ('Tagesschau', 'öRR')
    - 'ZDF heute (Kehrtwende)' → ('ZDF heute', None)
    """
    if not name:
        return name, None
    # Parenthetical qualifier entfernen: "ZDF heute (Kehrtwende)" → "ZDF heute"
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
    # " / Label"-Suffix entfernen: "Tagesschau / öRR" → ("Tagesschau", "öRR")
    if " / " in name:
        name_part, _, label_part = name.partition(" / ")
        return name_part.strip(), label_part.strip()
    return name, None


def _sanitize_analysis(analysis):
    """Defensive Bereinigung: quelle = nur Medienname, label = nur Spektrum."""
    for fs in analysis.get("framing_unterschiede", []):
        cleaned, label_from_quelle = _clean_quelle(fs.get("quelle", ""))
        fs["quelle"] = cleaned
        if label_from_quelle and not fs.get("label"):
            fs["label"] = label_from_quelle
    for wd in analysis.get("wortwahl_diff", []):
        for v in wd.get("varianten", []):
            cleaned, _ = _clean_quelle(v.get("quelle", ""))
            v["quelle"] = cleaned
    return analysis


# ──────────────────────────────────────────────────────────────────────────────
# LLM-Engine: lokale Claude-Code-CLI statt metered Anthropic-API.
# Die Analyse läuft über das Claude-Monatsabo auf diesem PC — kein API-Key,
# keine Pro-Call-Abrechnung. Voraussetzung: `claude` installiert und angemeldet.
# ──────────────────────────────────────────────────────────────────────────────

def find_claude_cli():
    path = shutil.which("claude")
    if not path:
        raise RuntimeError(
            "Claude-Code-CLI nicht gefunden (PATH). Installieren und mit `claude` einmal "
            "anmelden — die Analyse läuft über dein Abo, nicht über einen API-Key."
        )
    return path


def call_claude_cli(claude_path, user_prompt, model=MODEL, timeout=CLI_TIMEOUT):
    """Ruft `claude -p` headless auf und gibt den reinen Antworttext zurück.

    Schlank konfiguriert, damit die Calls schnell sind (sonst Minuten statt
    Sekunden pro Cluster):
    - `--system-prompt SYSTEM_PROMPT` ersetzt den agentischen Claude-Code-Default
      durch die reine Analyse-Anweisung (kein Tool-/Agent-Scaffold).
    - `--strict-mcp-config` ohne MCP-Config → es werden keine MCP-Server geladen.
    - `--disallowed-tools …` verhindert Tool-Umwege (z.B. WebSearch).
    - MAX_THINKING_TOKENS=0 schaltet Extended Thinking ab — das war die
      eigentliche Bremse (3x langsamer, ~2300 Denk-Tokens pro Cluster umsonst).

    WICHTIG: ANTHROPIC_API_KEY wird aus der Subprozess-Umgebung entfernt, damit
    Claude Code das Abo verwendet und NICHT den metered API-Key (sonst leckt die
    Abrechnung über den Key statt übers Abo).
    """
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env["MAX_THINKING_TOKENS"] = "0"

    cmd = [
        claude_path, "-p",
        "--output-format", "json",
        "--model", model,
        "--strict-mcp-config",
        "--disallowed-tools", *DISALLOWED_TOOLS,
        "--system-prompt", SYSTEM_PROMPT,
    ]
    proc = subprocess.run(
        cmd,
        input=user_prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude-CLI Exit {proc.returncode}: {(proc.stderr or '').strip()[:400]}"
        )
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude-CLI lieferte kein JSON-Envelope: {proc.stdout[:300]}")

    if envelope.get("is_error"):
        raise RuntimeError(f"claude-CLI meldet Fehler: {str(envelope.get('result'))[:300]}")
    return envelope.get("result", "") or ""


def extract_json_object(text):
    """Holt das JSON-Objekt aus der Modellantwort — robust gegen Markdown-Fences,
    Text drumherum und (ohne Thinking häufiger) unescapte Anführungszeichen in
    String-Werten. Versucht erst strikt zu parsen, dann json-repair als Netz."""
    text = (text or "").strip()
    fence = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Keine JSON-Struktur in der Antwort gefunden")
    snippet = text[start:end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        # z.B. gerade " innerhalb eines Werts -> json-repair flickt das Escaping
        from json_repair import repair_json
        repaired = repair_json(snippet)
        return json.loads(repaired)


def is_valid_analysis(a):
    """Ersetzt das früher per tool_choice erzwungene Schema: prüft Pflichtfelder."""
    if not isinstance(a, dict) or "faktenkern" not in a:
        return False
    fu = a.get("framing_unterschiede")
    if not isinstance(fu, list) or not fu:
        return False
    for e in fu:
        if not isinstance(e, dict):
            return False
        if not all(k in e for k in ("quelle", "label", "framing", "bias_score")):
            return False
    return True


def analyze_cluster(claude_path, cluster):
    """Analysiert einen Cluster über die Claude-CLI. Ein Retry bei ungültigem Output."""
    # SYSTEM_PROMPT läuft über den --system-prompt-Flag (siehe call_claude_cli);
    # hier nur noch die konkreten Cluster-Daten.
    base_prompt = (
        build_cluster_prompt(cluster)
        + "\n\nGib AUSSCHLIESSLICH das JSON-Objekt zurück — kein Markdown-Codeblock, "
          "kein erklärender Text davor oder danach."
    )

    last_err = None
    for attempt in range(2):
        prompt = base_prompt
        if attempt == 1:
            prompt += (
                "\n\nHINWEIS: Die vorige Antwort war ungültig. Antworte JETZT ausschließlich "
                "mit dem reinen JSON-Objekt; jeder Eintrag in framing_unterschiede braucht "
                "quelle, label, framing und bias_score."
            )
        raw = call_claude_cli(claude_path, prompt)
        try:
            analysis = extract_json_object(raw)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = f"Parse-Fehler: {e}"
            continue
        if not is_valid_analysis(analysis):
            last_err = "Pflichtfelder fehlen in der Analyse"
            continue
        return _sanitize_analysis(analysis)

    raise ValueError(last_err or "Analyse fehlgeschlagen")


def main():
    claude_path = find_claude_cli()

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = find_latest_clusters_file()

    print("Prisma — Framing-Analyse (über Claude-Abo, kein API-Key)")
    print("=" * 50)
    print(f"Eingabe:  {input_file}")
    print(f"Modell:   {MODEL}")
    print(f"CLI:      {claude_path}\n")

    data = load_clusters(input_file)
    all_clusters = data["clusters"]
    relevant = [c for c in all_clusters if c["spectrum_score"] >= MIN_SPECTRUM_SCORE]

    print(f"{len(all_clusters)} Cluster geladen")
    print(f"{len(relevant)} Cluster mit Spektrum-Breite >= {MIN_SPECTRUM_SCORE} (werden analysiert)\n")

    if not relevant:
        print("Keine relevanten Cluster gefunden.")
        return

    # 1) Cache-Lookups seriell vorab (SQLite-Connection ist nicht thread-safe).
    db_conn = db.get_connection()
    db.init_db(db_conn)
    cached_map = {}        # idx -> Analyse aus Cache
    todo = []              # [(idx, cluster)] die übers Abo analysiert werden
    for idx, cluster in enumerate(relevant):
        cached = None
        try:
            chash = db.compute_cluster_hash(cluster["articles"])
            if chash:
                cached = db.find_cached_analysis(db_conn, chash)
        except Exception:
            cached = None
        if cached:
            cached_map[idx] = cached
        else:
            todo.append((idx, cluster))
    db_conn.close()

    cache_hits = len(cached_map)
    total = len(todo)
    print(f"{cache_hits} aus Cache, {total} werden übers Abo analysiert "
          f"(parallel, {CONCURRENCY} gleichzeitig, Thinking aus)\n")

    # 2) Analysen parallel — analyze_cluster ruft nur subprocess + Parsing, keine DB.
    def work(item):
        idx, cluster = item
        try:
            return idx, ("ok", analyze_cluster(claude_path, cluster))
        except subprocess.TimeoutExpired:
            return idx, ("err", f"CLI-Timeout nach {CLI_TIMEOUT}s")
        except Exception as e:
            return idx, ("err", str(e))

    analyzed_map = {}
    if todo:
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            futs = [ex.submit(work, item) for item in todo]
            for fut in concurrent.futures.as_completed(futs):
                idx, outcome = fut.result()
                analyzed_map[idx] = outcome
                done += 1
                label = relevant[idx]["label"][:50]
                status = "OK" if outcome[0] == "ok" else f"FEHLER: {outcome[1][:50]}"
                print(f"  [{done:2}/{total}] {label} … {status}", flush=True)

    # 3) Ergebnisse in Original-Reihenfolge zusammenführen.
    results = []
    error_count = 0
    cli_calls = 0
    for idx, cluster in enumerate(relevant):
        base = {
            "cluster_id": cluster["id"],
            "label": cluster["label"],
            "spectrum_score": cluster["spectrum_score"],
            "spectrum_labels": cluster["spectrum_labels"],
            "article_count": cluster["article_count"],
        }
        if idx in cached_map:
            c = cached_map[idx]
            results.append({**base,
                            "faktenkern": c["faktenkern"],
                            "framing_unterschiede": c["framing_unterschiede"],
                            "wortwahl_diff": c["wortwahl_diff"]})
            continue
        kind, value = analyzed_map[idx]
        if kind == "ok":
            cli_calls += 1
            results.append({**base,
                            "faktenkern": value.get("faktenkern", ""),
                            "framing_unterschiede": value.get("framing_unterschiede", []),
                            "wortwahl_diff": value.get("wortwahl_diff", [])})
        else:
            error_count += 1
            results.append({"cluster_id": cluster["id"], "label": cluster["label"], "error": value})

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_file = os.path.join(DATA_DIR, f"framing_{timestamp}.json")

    payload = {
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": input_file,
        "model": MODEL,
        "billing": "claude-subscription",
        "cluster_count_analyzed": len(results),
        "error_count": error_count,
        "estimated_cost_usd": 0.0,  # über Abo abgerechnet, keine Pro-Call-Kosten
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    db_conn.close()

    success_count = len(results) - error_count
    print(f"\nGespeichert: {output_file}")
    print(f"{success_count} analysiert ({cache_hits} aus Cache, {cli_calls} per Claude-Abo), {error_count} Fehler")
    print("Abrechnung: über Claude-Monatsabo (kein API-Key, keine Pro-Call-Kosten)\n")

    successes = [r for r in results if "error" not in r]
    if successes:
        print("Top-3-Cluster mit bias_scores:")
        for r in successes[:3]:
            print(f"\n  Thema: \"{r['label'][:70]}\"")
            print(f"  Faktenkern: {r['faktenkern'][:120]}...")
            for fs in r.get("framing_unterschiede", []):
                score = fs.get("bias_score")
                score_str = f"  bias={score:3d}" if score is not None else "  bias= ?"
                print(f"    {fs['quelle'][:30]:<30} ({fs.get('label','?'):>12}){score_str}  {fs['framing'][:60]}...")

    try:
        conn = db.get_connection()
        db.init_db(conn)
        db.save_analysis_run(conn, payload, output_file)
        conn.close()
        print("\nDB: gespeichert")
    except Exception as e:
        print(f"\nDB-Warnung: {e}")


if __name__ == "__main__":
    main()
