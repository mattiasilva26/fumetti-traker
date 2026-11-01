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
COLLECTION = []

# ------------------------------------------------------------------ USCITE
PUBLISHERS = [
    {
        "editore": "Bonelli",
        "api": "https://www.sergiobonelli.it/wp-json/wp/v2/product",
        "media": "https://www.sergiobonelli.it/wp-json/wp/v2/media",
        "date_from": "attribute",     # usa pa_data-di-uscita (date reali, anche future)
        "require_collana": True,       # limita la sezione edicola agli albi
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
UPCOMING_DYLAN = [{
    "id": "dylan-dog-color-fest-59",
    "tipo": "uscita",
    "editore": "Bonelli",
    "serie": "Dylan Dog",
    "collana": "Color Fest",
    "numero": 59,
    "titolo": "Dylan Dog Color Fest 59 – Dedicato a Ambrosini",
    "data": "2026-11-07",
    "cover": "https://mycomics.it/wp-content/uploads/sites/16/2026/09/Dylan-Dog-Color-Fest-59-Dedicato-a-Ambrosini.jpg",
    "link": "https://www.sergiobonelli.it/collana/dylan-dog-color-fest/",
    "fonte": "MyComics preordini",
}]

# L'API prodotti Bonelli non restituisce sempre tutti gli arretrati della
# collana Color Fest. Archivio ufficiale: numeri 21-58.
COLOR_FEST_ARCHIVE = [
    (21, "Lo scuotibare", "2017-05-05"),
    (22, "Remake 2", "2017-08-09"),
    (23, "Il convento del vuoto", "2017-11-08"),
    (24, "Strani giorni", "2018-02-08"),
    (25, "I conigli rosa muoiono", "2018-05-05"),
    (26, "Creepy Past", "2018-08-09"),
    (27, "Il male infinito", "2018-11-08"),
    (28, "Gotico inglese", "2019-02-08"),
    (29, "Se una notte d'inverno un assassino", "2019-05-08"),
    (30, "Groucho Primo", "2019-08-09"),
    (31, "Selezione innaturale", "2019-11-08"),
    (32, "Altre visioni", "2020-02-08"),
    (33, "Delitti e castighi", "2020-05-08"),
    (34, "Groucho Secondo", "2020-08-08"),
    (35, "Nuove visioni", "2020-11-06"),
    (36, "Mister Punch", "2021-02-09"),
    (37, "Doppio orrore", "2021-05-08"),
    (38, "Groucho Terzo", "2021-08-06"),
    (39, "Stati di paura", "2021-11-17"),
    (40, "Estreme visioni", "2022-02-09"),
    (41, "L'orrore delle armi", "2022-05-10"),
    (42, "Groucho Quarto", "2022-08-06"),
    (43, "Utopia modulare", "2022-11-05"),
    (44, "Il verme bianco", "2023-02-08"),
    (45, "Luci e ombre", "2023-05-10"),
    (46, "Groucho Quinto", "2023-08-09"),
    (47, "I vivi e gli altri", "2023-11-08"),
    (48, "Il risveglio", "2024-02-08"),
    (49, "Lettere dall'incubo", "2024-05-08"),
    (50, "Groucho (fuori di) sesto", "2024-08-08"),
    (51, "Strade perdute", "2024-11-08"),
    (52, "Non vale se non hai paura", "2025-02-08"),
    (53, "A prova di morte", "2025-05-08"),
    (54, "Estranei", "2025-08-09"),
    (55, "Cosa conosce la notte", "2025-11-08"),
    (56, "Dissolvenza al nero", "2026-02-10"),
    (57, "Destinazione: terrore!", "2026-05-08"),
    (58, "Lo spazio bianco", "2026-08-08"),
]
COLOR_FEST_NUMBERS_BY_DATE = {release_date: number for number, _, release_date in COLOR_FEST_ARCHIVE}


def _color_fest_number(title, release_date):
    match = re.search(r"color\s*fest\s*(?:n\.?\s*)?(\d+)", title, re.IGNORECASE)
    return int(match.group(1)) if match else COLOR_FEST_NUMBERS_BY_DATE.get(release_date)


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
    prods = []
    for page in range(1, 101):
        batch = _get_json(pub["api"], {
            "orderby": "date", "order": "desc", "per_page": 100, "page": page,
            "_fields": "id,title,link,class_list,featured_media,date",
        })
        if not isinstance(batch, list):
            break
        prods.extend(batch)
        if len(batch) < 100:
            break
    if not prods:
        return out

    today = _dt.date.today()
    rows, media_ids = [], []

    for p in prods:
        classes = _classes(p)
        if pub.get("require_cat_fumetti") and "product_cat-fumetti" not in classes:
            continue

        if pub["date_from"] == "attribute":
            data = _uscita_date(classes)
            if not data:
                data = (p.get("date") or "")[:10]
        else:
            data = (p.get("date") or "")[:10]

        titolo = html.unescape(((p.get("title") or {}).get("rendered") or "")).strip()
        if not titolo:
            continue

        joined = " ".join(classes)
        merchandising = "product_cat-merchandising" in classes or bool(re.search(
            r"t[ -]?shirt|magliett|cappellin|tazza|portachiav|plaid|puzzle|medaglia",
            titolo,
            re.IGNORECASE,
        ))
        serie = ""
        if not merchandising and ("dylan-dog" in joined or re.search(r"dylan\s*dog", titolo, re.IGNORECASE)):
            serie = "Dylan Dog"
        elif not merchandising and "toni-bellasalma" in joined:
            serie = "Toni Bellasalma"

        in_window = True
        if pub.get("window_days"):
            try:
                in_window = _dt.date.fromisoformat(data) >= today - _dt.timedelta(days=pub["window_days"])
            except ValueError:
                pass
        is_release = in_window and (serie == "Dylan Dog" or not pub.get("require_collana") or any(
            c.startswith("pa_collana-") for c in classes
        ))
        if not serie and not is_release:
            continue

        if serie == "Dylan Dog":
            titolo_low = titolo.casefold()
            if "cofanetto" in titolo_low or "box" in titolo_low:
                collana = "Cofanetti"
            elif "color fest" in titolo_low or "colorfest" in titolo_low:
                collana = "Color Fest"
            elif "oldboy" in titolo_low or "old boy" in titolo_low:
                collana = "Oldboy"
            elif "speciale" in titolo_low:
                collana = "Speciale"
            elif "maxi" in titolo_low:
                collana = "Maxi"
            elif "almanacco" in titolo_low or "enciclopedia della paura" in titolo_low:
                collana = "Almanacco / Enciclopedia"
            elif "gigante" in titolo_low:
                collana = "Gigante"
            elif any(term in titolo_low for term in ("collezione", "book", "ristampa", "raccolta")):
                collana = "Raccolte e ristampe"
            elif re.search(r"dylan\s*dog\s*n\.?\s*\d+", titolo_low):
                collana = "Serie regolare"
            else:
                collana = "Altre edizioni"
        else:
            collana = "Toni Bellasalma"

        rows.append({"id": p.get("id"), "data": data, "serie": serie, "collana": collana,
                     "uscita": is_release, "titolo": titolo,
                     "link": p.get("link", ""), "fm": p.get("featured_media")})
        media_ids.append(p.get("featured_media"))

    mmap = _media_map(pub["media"], media_ids)

    for r in rows:
        if r["serie"]:
            COLLECTION.append({
                "id": str(r["id"] or r["link"] or r["titolo"]),
                "tipo": "collezione",
                "editore": pub["editore"],
                "serie": r["serie"],
                "collana": r["collana"],
                "numero": _color_fest_number(r["titolo"], r["data"]) if r["collana"] == "Color Fest" else None,
                "titolo": r["titolo"],
                "data": r["data"],
                "cover": mmap.get(r["fm"], ""),
                "link": r["link"],
            })

    recent_rows = [row for row in rows if row["uscita"]]

    selected_rows = recent_rows[:pub.get("max", 50)]
    selected_ids = {row["id"] for row in selected_rows}
    selected_rows.extend(
        row for row in recent_rows
        if row["serie"] == "Dylan Dog" and row["id"] not in selected_ids
    )

    for r in selected_rows:
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
    COLLECTION.clear()
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
    for item in UPCOMING_DYLAN:
        if not any(x.get("titolo", "").casefold() == item["titolo"].casefold() for x in tutto):
            tutto.append(item)
        COLLECTION.append({**item, "tipo": "collezione"})
    for number, title, release_date in COLOR_FEST_ARCHIVE:
        if any(x.get("collana") == "Color Fest" and x.get("data") == release_date
               for x in COLLECTION):
            continue
        COLLECTION.append({
            "id": f"dylan-dog-color-fest-{number}",
            "tipo": "collezione",
            "editore": "Bonelli",
            "serie": "Dylan Dog",
            "collana": "Color Fest",
            "numero": number,
            "titolo": f"Dylan Dog Color Fest {number} – {title}",
            "data": release_date,
            "cover": "",
            "link": "https://www.sergiobonelli.it/collana/dylan-dog-color-fest/",
        })
    return tutto
