"""
Fonti dati per il tracker fumetti — versione a FEED RSS (affidabile).

Perche' i feed: i siti di Bonelli e Bugs sono shop in JavaScript, difficili e
fragili da "scrapare". Entrambi pero' pubblicano un feed RSS ufficiale, che e'
testo strutturato, stabile e facile da leggere. Usiamo quelli.

Ogni funzione restituisce dict con:
  tipo ("uscita"|"news"), editore, serie, titolo, data (YYYY-MM-DD), cover, link, fonte
"""

import re
import sys
import time

import requests
import feedparser

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
}
TIMEOUT = 25

# Feed degli EDITORI -> vanno nella scheda "Ultime uscite"
PUBLISHER_FEEDS = [
    {"url": "https://www.sergiobonelli.it/feed/", "editore": "Bonelli",     "fonte": "Sergio Bonelli Editore"},
    {"url": "https://www.bugscomics.com/feed/",   "editore": "Bugs Comics", "fonte": "Bugs Comics"},
]

# Feed di NOTIZIE -> scheda "Notizie", filtrati per parola chiave
NEWS_FEEDS = [
    "https://www.lospaziobianco.it/feed/",
    "https://www.fumettologica.it/feed/",
]
PAROLE = ["dylan dog", "bellasalma", "bonelli", "bugs comics", "sclavi", "samuel stern"]


def _fetch_feed(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] {url} -> {e}", file=sys.stderr)
        return None


def _cover(entry):
    for key in ("media_content", "media_thumbnail"):
        v = entry.get(key)
        if v and isinstance(v, list) and v and v[0].get("url"):
            return v[0]["url"]
    html = ""
    if entry.get("content"):
        html = entry["content"][0].get("value", "")
    html = html or entry.get("summary", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    return m.group(1) if m else ""


def _data(entry):
    if entry.get("published_parsed"):
        return time.strftime("%Y-%m-%d", entry.published_parsed)
    return ""


def _serie(testo):
    if re.search(r"dylan\s*dog", testo, re.I):
        return "Dylan Dog"
    if re.search(r"bellasalma", testo, re.I):
        return "Toni Bellasalma"
    return ""


def fetch_publisher(feed):
    out = []
    parsed = _fetch_feed(feed["url"])
    if not parsed:
        return out
    for e in parsed.entries[:25]:
        titolo = (e.get("title") or "").strip()
        if not titolo:
            continue
        cats = " ".join(t.get("term", "") for t in e.get("tags", []) if isinstance(t, dict))
        out.append({
            "tipo": "uscita",
            "editore": feed["editore"],
            "serie": _serie(titolo + " " + cats),
            "titolo": titolo,
            "data": _data(e),
            "cover": _cover(e),
            "link": e.get("link", ""),
            "fonte": feed["fonte"],
        })
    return out


def fetch_news():
    out = []
    for url in NEWS_FEEDS:
        parsed = _fetch_feed(url)
        if not parsed:
            continue
        fonte = parsed.feed.get("title", url)
        for e in parsed.entries[:40]:
            titolo = e.get("title", "")
            testo = (titolo + " " + e.get("summary", "")).lower()
            if not any(k in testo for k in PAROLE):
                continue
            out.append({
                "tipo": "news",
                "editore": fonte,
                "serie": _serie(titolo),
                "titolo": titolo,
                "data": _data(e),
                "cover": _cover(e),
                "link": e.get("link", ""),
                "fonte": fonte,
            })
    return out


def fetch_all():
    tutto = []
    for feed in PUBLISHER_FEEDS:
        print(f"-> {feed['editore']} ...")
        try:
            d = fetch_publisher(feed)
            print(f"   {len(d)} elementi")
            tutto.extend(d)
        except Exception as e:  # noqa: BLE001
            print(f"   [errore] {feed['editore']}: {e}", file=sys.stderr)
    print("-> Notizie ...")
    try:
        n = fetch_news()
        print(f"   {len(n)} elementi")
        tutto.extend(n)
    except Exception as e:  # noqa: BLE001
        print(f"   [errore] News: {e}", file=sys.stderr)
    return tutto
