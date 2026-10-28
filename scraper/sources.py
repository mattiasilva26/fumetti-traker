"""
Fonti dati per il tracker fumetti.

DUE cose separate e affidabili:

1) ULTIME USCITE -> dall'API prodotti dei siti (WordPress/WooCommerce):
   - Bonelli: ogni albo espone la data di uscita reale (anche FUTURA) come
     attributo "pa_data-di-uscita-GG-MM-AAAA". Prendiamo solo gli albi/volumi
     (hanno "pa_collana-..."), non il merchandising.
   - Bugs Comics: prendiamo i prodotti in categoria "fumetti" (tag Bellasalma
     evidenziato). Bugs non espone la data di uscita, quindi usiamo la data del
     prodotto come riferimento.

2) NOTIZIE -> dai feed RSS dei siti di informazione fumetto, filtrate per parola
   chiave. Restano separate dalle uscite.
"""

import datetime as _dt
import html
import re
import sys
import time

import requests

try:
    import feedparser
except Exception:  # noqa: BLE001
    feedparser = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
}
TIMEOUT = 25

# ------------------------------------------------------------------ USCITE
PUBLISHERS = [
    {
        "editore": "Bonelli",
        "api": "https://www.sergiobonelli.it/wp-json/wp/v2/product",
        "media": "https://www.sergiobonelli.it/wp-json/wp/v2/media",
        "date_from": "attribute",     # usa pa_data-di-uscita (date reali, anche future)
        "require_collana": True,       # solo albi/volumi, niente merchandising
        "window_days": 60,             # scarta roba piu' vecchia di 60 giorni (tiene tutto il futuro)
        "max": 50,
    },
    {
        "editore": "Bugs Comics",
        "api": "https://www.bugscomics.com/wp-json/wp/v2/product",
        "media": "https://www.bugscomics.com/wp-json/wp/v2/media",
        "date_from": "post",           # Bugs non espone la data uscita: usiamo quella del prodotto
        "require_cat_fumetti": True,    # solo fumetti
        "window_days": None,            # il catalogo Bugs e' piccolo: niente finestra temporale
        "max": 15,
    },
]

# ------------------------------------------------------------------ NOTIZIE
NEWS_FEEDS = [
    "https://www.lospaziobianco.it/feed/",
    "https://www.fumettologica.it/feed/",
    "https://www.sergiobonelli.it/feed/",
]
PAROLE = ["dylan dog", "bellasalma", "bonelli", "bugs comics", "sclavi", "samuel stern"]


def _get_json(url, params=None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] {url} -> {e}", file=sys.stderr)
        return None


def _classes(prod):
    cl = prod.get("class_list")
    if isinstance(cl, dict):
        return list(cl.values())
    if isinstance(cl, list):
        return cl
    return []


def _uscita_date(classes):
    for c in classes:
        m = re.match(r"pa_data-di-uscita-(\d{1,2})-(\d{1,2})-(\d{4})", c)
        if m:
            g, mo, y = (int(x) for x in m.groups())
            try:
                return _dt.date(y, mo, g).isoformat()
            except ValueError:
                return ""
    return ""


def _media_map(media_url, ids):
    out = {}
    ids = [i for i in ids if i]
    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]
        data = _get_json(media_url, {
            "include": ",".join(str(x) for x in chunk),
            "per_page": len(chunk),
            "_fields": "id,source_url",
        })
        if isinstance(data, list):
            for m in data:
                out[m.get("id")] = m.get("source_url", "")
    return out


def fetch_publisher(pub):
    out = []
    prods = _get_json(pub["api"], {
        "orderby": "date", "order": "desc", "per_page": 100,
        "_fields": "id,title,link,class_list,featured_media,date",
    })
    if not isinstance(prods, list):
        return out

    today = _dt.date.today()
    rows, media_ids = [], []

    for p in prods:
        classes = _classes(p)
        if pub.get("require_collana") and not any(c.startswith("pa_collana-") for c in classes):
            continue
        if pub.get("require_cat_fumetti") and "product_cat-fumetti" not in classes:
            continue

        if pub["date_from"] == "attribute":
            data = _uscita_date(classes)
            if not data:
                continue
        else:
            data = (p.get("date") or "")[:10]

        if pub.get("window_days") and data:
            try:
                if _dt.date.fromisoformat(data) < today - _dt.timedelta(days=pub["window_days"]):
                    continue
            except ValueError:
                pass

        joined = " ".join(classes)
        serie = ""
        if "dylan-dog" in joined:
            serie = "Dylan Dog"
        elif "toni-bellasalma" in joined:
            serie = "Toni Bellasalma"

        titolo = html.unescape(((p.get("title") or {}).get("rendered") or "")).strip()
        if not titolo:
            continue

        rows.append({"data": data, "serie": serie, "titolo": titolo,
                     "link": p.get("link", ""), "fm": p.get("featured_media")})
        media_ids.append(p.get("featured_media"))

    mmap = _media_map(pub["media"], media_ids)

    for r in rows[:pub.get("max", 50)]:
        out.append({
            "tipo": "uscita",
            "editore": pub["editore"],
            "serie": r["serie"],
            "titolo": r["titolo"],
            "data": r["data"],
            "cover": mmap.get(r["fm"], ""),
            "link": r["link"],
            "fonte": pub["editore"],
        })
    return out


def _feed_cover(entry):
    for key in ("media_content", "media_thumbnail"):
        v = entry.get(key)
        if v and isinstance(v, list) and v and v[0].get("url"):
            return v[0]["url"]
    htmlc = ""
    if entry.get("content"):
        htmlc = entry["content"][0].get("value", "")
    htmlc = htmlc or entry.get("summary", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', htmlc)
    return m.group(1) if m else ""


def fetch_news():
    out = []
    if feedparser is None:
        print("  [warn] feedparser non disponibile", file=sys.stderr)
        return out
    for url in NEWS_FEEDS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] feed {url} -> {e}", file=sys.stderr)
            continue
        fonte = parsed.feed.get("title", url)
        for e in parsed.entries[:40]:
            titolo = html.unescape(e.get("title", ""))
            testo = (titolo + " " + e.get("summary", "")).lower()
            if not any(k in testo for k in PAROLE):
                continue
            data = ""
            if e.get("published_parsed"):
                data = time.strftime("%Y-%m-%d", e.published_parsed)
            serie = ""
            low = titolo.lower()
            if "dylan dog" in low:
                serie = "Dylan Dog"
            elif "bellasalma" in low:
                serie = "Toni Bellasalma"
            out.append({
                "tipo": "news", "editore": fonte, "serie": serie,
                "titolo": titolo, "data": data, "cover": _feed_cover(e),
                "link": e.get("link", ""), "fonte": fonte,
            })
    return out


def fetch_all():
    tutto = []
    for pub in PUBLISHERS:
        print(f"-> uscite {pub['editore']} ...")
        try:
            d = fetch_publisher(pub)
            print(f"   {len(d)} uscite")
            tutto.extend(d)
        except Exception as e:  # noqa: BLE001
            print(f"   [errore] {pub['editore']}: {e}", file=sys.stderr)
    print("-> notizie ...")
    try:
        n = fetch_news()
        print(f"   {len(n)} notizie")
        tutto.extend(n)
    except Exception as e:  # noqa: BLE001
        print(f"   [errore] notizie: {e}", file=sys.stderr)
    return tutto
