import json
import os
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
import anthropic
from json_repair import repair_json

import db

load_dotenv(override=True)

DATA_DIR = "data"
MODEL = "claude-sonnet-4-6"
MIN_SPECTRUM_SCORE = 2

# Kosten pro 1M Tokens (Sonnet 4.6)
COST_INPUT = 3.00 / 1_000_000
COST_OUTPUT = 15.00 / 1_000_000
COST_CACHE_WRITE = 3.75 / 1_000_000
COST_CACHE_READ = 0.30 / 1_000_000

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

  Zitiere auffällige Begriffe direkt in „Anführungszeichen".

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


def parse_json_response(text):
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(repair_json(text))


def _clean_quelle(name):
    """Bereinigt KI-generierte Quellennamen:
    - 'Tagesschau / öRR' → ('Tagesschau', 'öRR')
    - 'ZDF heute (Kehrtwende)' → ('ZDF heute', None)
    """
    import re
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


def analyze_cluster(client, cluster):
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": build_cluster_prompt(cluster),
        }],
    )

    text = response.content[0].text
    analysis = _sanitize_analysis(parse_json_response(text))

    usage = response.usage
    return analysis, {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }


def calc_cost(usage):
    return (
        usage["input_tokens"] * COST_INPUT
        + usage["output_tokens"] * COST_OUTPUT
        + usage["cache_creation_input_tokens"] * COST_CACHE_WRITE
        + usage["cache_read_input_tokens"] * COST_CACHE_READ
    )


def add_usage(total, delta):
    for k in total:
        total[k] += delta[k]


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("FEHLER: ANTHROPIC_API_KEY nicht gesetzt.")
        print("Lege eine .env-Datei an: ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = find_latest_clusters_file()

    print("News Agent — Framing-Analyse")
    print("=" * 40)
    print(f"Eingabe:  {input_file}")
    print(f"Modell:   {MODEL}\n")

    data = load_clusters(input_file)
    all_clusters = data["clusters"]
    relevant = [c for c in all_clusters if c["spectrum_score"] >= MIN_SPECTRUM_SCORE]

    print(f"{len(all_clusters)} Cluster geladen")
    print(f"{len(relevant)} Cluster mit Spektrum-Breite ≥ {MIN_SPECTRUM_SCORE} (werden analysiert)\n")

    if not relevant:
        print("Keine relevanten Cluster gefunden.")
        return

    client = anthropic.Anthropic(api_key=api_key)

    # DB-Connection für Cache-Lookup
    db_conn = db.get_connection()

    results = []
    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    error_count = 0
    cache_hits = 0

    for i, cluster in enumerate(relevant, start=1):
        short_label = cluster["label"][:55]
        print(f"  [{i:2}/{len(relevant)}] {short_label}...", end=" ", flush=True)

        # Idempotenz-Check: schon mal analysiert?
        chash = db.compute_cluster_hash(cluster["articles"])
        cached = db.find_cached_analysis(db_conn, chash) if chash else None

        if cached:
            cache_hits += 1
            results.append({
                "cluster_id": cluster["id"],
                "label": cluster["label"],
                "spectrum_score": cluster["spectrum_score"],
                "spectrum_labels": cluster["spectrum_labels"],
                "article_count": cluster["article_count"],
                "faktenkern": cached["faktenkern"],
                "framing_unterschiede": cached["framing_unterschiede"],
                "wortwahl_diff": cached["wortwahl_diff"],
                "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            })
            print("CACHE  (0 tok, $0.00)")
            continue

        try:
            analysis, usage = analyze_cluster(client, cluster)
            add_usage(total_usage, usage)

            results.append({
                "cluster_id": cluster["id"],
                "label": cluster["label"],
                "spectrum_score": cluster["spectrum_score"],
                "spectrum_labels": cluster["spectrum_labels"],
                "article_count": cluster["article_count"],
                "faktenkern": analysis.get("faktenkern", ""),
                "framing_unterschiede": analysis.get("framing_unterschiede", []),
                "wortwahl_diff": analysis.get("wortwahl_diff", []),
                "usage": usage,
            })

            cache_hit = usage["cache_read_input_tokens"] > 0
            cache_info = " [cache-hit]" if cache_hit else ""
            print(f"OK  ({usage['input_tokens']}+{usage['output_tokens']} tok){cache_info}")

        except json.JSONDecodeError as e:
            error_count += 1
            print(f"JSON-Fehler: {e}")
            results.append({
                "cluster_id": cluster["id"],
                "label": cluster["label"],
                "error": f"JSON-Parse-Fehler: {e}",
            })

        except anthropic.RateLimitError:
            print("Rate-Limit — 60s warten...")
            time.sleep(60)
            try:
                analysis, usage = analyze_cluster(client, cluster)
                add_usage(total_usage, usage)
                results.append({
                    "cluster_id": cluster["id"],
                    "label": cluster["label"],
                    "spectrum_score": cluster["spectrum_score"],
                    "spectrum_labels": cluster["spectrum_labels"],
                    "article_count": cluster["article_count"],
                    "faktenkern": analysis.get("faktenkern", ""),
                    "framing_unterschiede": analysis.get("framing_unterschiede", []),
                    "wortwahl_diff": analysis.get("wortwahl_diff", []),
                    "usage": usage,
                })
                print(f"OK (nach Retry)")
            except Exception as e2:
                error_count += 1
                print(f"FEHLER nach Retry: {e2}")
                results.append({
                    "cluster_id": cluster["id"],
                    "label": cluster["label"],
                    "error": str(e2),
                })

        except anthropic.APIStatusError as e:
            error_count += 1
            print(f"API-Fehler {e.status_code}: {e.message}")
            results.append({
                "cluster_id": cluster["id"],
                "label": cluster["label"],
                "error": f"API {e.status_code}: {e.message}",
            })

        except anthropic.APIConnectionError as e:
            error_count += 1
            print(f"Verbindungsfehler: {e}")
            results.append({
                "cluster_id": cluster["id"],
                "label": cluster["label"],
                "error": str(e),
            })

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_file = os.path.join(DATA_DIR, f"framing_{timestamp}.json")

    payload = {
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": input_file,
        "model": MODEL,
        "cluster_count_analyzed": len(results),
        "error_count": error_count,
        "total_usage": total_usage,
        "estimated_cost_usd": round(calc_cost(total_usage), 6),
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    total_cost = calc_cost(total_usage)
    success_count = len(results) - error_count
    api_calls = success_count - cache_hits

    print(f"\nGespeichert: {output_file}")
    print(f"{success_count} analysiert ({cache_hits} aus Cache, {api_calls} per API), {error_count} Fehler\n")

    print("Token-Verbrauch:")
    print(f"  Input (unkached):   {total_usage['input_tokens']:>8,}")
    print(f"  Output:             {total_usage['output_tokens']:>8,}")
    print(f"  Cache-Write:        {total_usage['cache_creation_input_tokens']:>8,}")
    print(f"  Cache-Read:         {total_usage['cache_read_input_tokens']:>8,}")
    print(f"\nGeschätzte Kosten:    ${total_cost:.4f}")
    if cache_hits > 0:
        avg_cost_per_call = total_cost / api_calls if api_calls > 0 else 0.018
        saved = cache_hits * avg_cost_per_call
        print(f"Gespart durch Cache:  ${saved:.4f} ({cache_hits} Cluster nicht erneut analysiert)")

    successes = [r for r in results if "error" not in r]
    if successes:
        print("\nTop-3-Cluster mit bias_scores:")
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
