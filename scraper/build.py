"""
Genera docs/data.json a partire dalle fonti.
Questo è lo script che il "robot" (GitHub Actions) lancia a intervalli.

Eseguilo a mano con:  python scraper/build.py
"""

import datetime as _dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402

# Dove scriviamo l'output: dentro docs/, la cartella che GitHub Pages pubblica.
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
OUT_FILE = os.path.join(OUT_DIR, "data.json")


def main():
    elementi = sources.fetch_all()

    # Ordiniamo: prima gli elementi con data (più recenti in cima), poi senza.
    def chiave(e):
        return (e.get("data") or "", )
    elementi.sort(key=chiave, reverse=True)

    payload = {
        "aggiornato": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "conteggio": len(elementi),
        "elementi": elementi,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\nScritti {len(elementi)} elementi in {OUT_FILE}")


if __name__ == "__main__":
    main()
