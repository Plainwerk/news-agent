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

SYSTEM_PROMPT = """Du bist ein Medienanalyse-Experte. Du analysierst, wie verschiedene deutsche Nachrichtenmedien über dasselbe Ereignis berichten.

Deine Aufgabe: Für einen gegebenen Nachrichten-Cluster erstellst du eine strukturierte Framing-Analyse basierend ausschließlich auf den gegebenen Artikel-Titeln.

Antworte ausschließlich mit gültigem JSON in folgendem Format (kein Markdown, kein Kommentar davor oder danach):
{
  "faktenkern": "Sachliche Zusammenfassung des Ereignisses in maximal 3 Sätzen.",
  "framing_unterschiede": [
    {
      "quelle": "Name des Mediums",
      "label": "Spektrum-Label (z.B. links, mitte-rechts, öRR)",
      "framing": "Wie dieses Medium das Ereignis rahmt: Was wird betont, welche Perspektive wird eingenommen?",
      "bias_score": 50
    }
  ],
  "wortwahl_diff": [
    {
      "konzept": "Worum handelt es sich? (z.B. 'Bezeichnung der Person', 'Name des Vorgangs')",
      "varianten": [
        {"quelle": "Medienname", "bezeichnung": "Wie dieses Medium es nennt"}
      ]
    }
  ]
}

Regeln:
- framing_unterschiede: Nur Quellen aufführen, die tatsächlich eigene Artikel beigetragen haben.
- wortwahl_diff: Nur befüllen, wenn Medien dasselbe Konzept unterschiedlich benennen. Sonst leeres Array [].
- Gib zusätzlich für jede Quelle einen bias_score von 0 bis 100 an, basierend ausschließlich auf dem konkreten Inhalt und der Wortwahl dieses Artikels — nicht auf dem generellen Ruf der Quelle. 0 = sehr linke Rahmung, 50 = neutral/sachlich, 100 = sehr rechte Rahmung. Sei präzise und begründe dich am Text.
- Antworte auf Deutsch."""


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


def analyze_cluster(client, cluster):
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
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
    analysis = parse_json_response(text)

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

    results = []
    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    error_count = 0

    for i, cluster in enumerate(relevant, start=1):
        short_label = cluster["label"][:55]
        print(f"  [{i:2}/{len(relevant)}] {short_label}...", end=" ", flush=True)

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

    print(f"\nGespeichert: {output_file}")
    print(f"{success_count} analysiert, {error_count} Fehler\n")

    print("Token-Verbrauch:")
    print(f"  Input (unkached):   {total_usage['input_tokens']:>8,}")
    print(f"  Output:             {total_usage['output_tokens']:>8,}")
    print(f"  Cache-Write:        {total_usage['cache_creation_input_tokens']:>8,}")
    print(f"  Cache-Read:         {total_usage['cache_read_input_tokens']:>8,}")
    print(f"\nGeschätzte Kosten:    ${total_cost:.4f}")

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
