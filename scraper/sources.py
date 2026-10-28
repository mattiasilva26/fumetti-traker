"""
Fonti dati per il tracker fumetti.

Ogni funzione restituisce una lista di dict normalizzati con questi campi:
  - tipo:     "uscita" oppure "news"
  - editore:  "Bonelli" | "Bugs Comics" | (per le news: la fonte)
  - serie:    es. "Dylan Dog" (vuoto per le news)
  - titolo:   titolo dell'albo o della notizia
  - data:     stringa ISO (YYYY-MM-DD) quando disponibile, altrimenti ""
  - cover:    URL immagine copertina (solo link, non scarichiamo nulla)
  - link:     URL alla pagina originale
  - fonte:    nome leggibile della fonte

NOTA IMPORTANTE SUI SELETTORI HTML:
I siti cambiano layout nel tempo. Le funzioni di scraping qui sotto sono
scritte in modo difensivo: se un selettore non trova nulla, la funzione
ritorna [] invece di crashare, così il resto del sito continua a funzionare.
Quando una fonte "si svuota", vai nella sua funzione e aggiorna i selettori.
"""

import datetime as _dt
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

# User-agent educato: ci identifichiamo invece di spacciarci per un browser.
HEADERS = {
    "User-Agent": "FumettiTracker/1.0 (uso personale; +https://github.com/)",
    "Accept-Language": "it-IT,it;q=0.9",
}

TIMEOUT = 20


def _get(url):
    """GET difensivo: non solleva eccezioni, logga e torna None se fallisce."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r
    except Exception as e:  # noqa: BLE001 - vogliamo degradare, non crashare
        print(f"  [warn] {url} -> {e}", file=sys.stderr)
        return None


def _soup(url):
    r = _get(url)
    if r is None:
        return None
    return BeautifulSoup(r.text, "html.parser")


# Mesi italiani -> numero, per parsare date tipo "28 ottobre 2026".
_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def parse_data_it(testo):
    """Prova a estrarre una data ISO da testo italiano libero. '' se non ci riesce."""
    if not testo:
        return ""
    testo = testo.lower()
    # formato "28 ottobre 2026"
    m = re.search(r"(\d{1,2})\s+([a-zà]+)\s+(\d{4})", testo)
    if m:
        giorno, mese_nome, anno = m.groups()
        mese = _MESI.get(mese_nome)
        if mese:
            try:
                return _dt.date(int(anno), mese, int(giorno)).isoformat()
            except ValueError:
                pass
    # formato "28/10/2026"
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", testo)
    if m:
        g, mm, a = (int(x) for x in m.groups())
        try:
            return _dt.date(a, mm, g).isoformat()
        except ValueError:
            pass
    return ""


# --------------------------------------------------------------------------
# FONTE 1: Uscite Sergio Bonelli Editore
# --------------------------------------------------------------------------
# Pagina di riferimento: le "uscite" mensili sul sito ufficiale.
# Lo scraping qui è un PUNTO DI PARTENZA: i selettori vanno verificati
# sulla pagina reale e corretti (vedi README, sezione "Tarare le fonti").
BONELLI_USCITE_URL = "https://www.sergiobonelli.it/sezioni/1025/in-edicola"


def fetch_bonelli():
    risultati = []
    soup = _soup(BONELLI_USCITE_URL)
    if soup is None:
        return risultati

    # I prodotti in edicola sono di solito in card ripetute.
    # Cerchiamo blocchi che contengono un link + un'immagine + un titolo.
    # Questo selettore è volutamente largo; da restringere dopo ispezione.
    cards = soup.select("article, .card, .prodotto, .box-prodotto, li")
    for card in cards:
        link_tag = card.find("a", href=True)
        img_tag = card.find("img")
        if not link_tag:
            continue
        titolo = (link_tag.get_text(strip=True)
                  or (img_tag.get("alt") if img_tag else "")).strip()
        if not titolo or len(titolo) < 3:
            continue

        href = link_tag["href"]
        if href.startswith("/"):
            href = "https://www.sergiobonelli.it" + href

        cover = ""
        if img_tag:
            cover = img_tag.get("data-src") or img_tag.get("src") or ""
            if cover.startswith("/"):
                cover = "https://www.sergiobonelli.it" + cover

        # È Dylan Dog? lo marchiamo per l'evidenza in homepage.
        serie = "Dylan Dog" if re.search(r"dylan\s*dog", titolo, re.I) else ""

        risultati.append({
            "tipo": "uscita",
            "editore": "Bonelli",
            "serie": serie,
            "titolo": titolo,
            "data": "",
            "cover": cover,
            "link": href,
            "fonte": "Sergio Bonelli Editore",
        })

    # Dedup grezzo per titolo
    visti = set()
    puliti = []
    for r in risultati:
        if r["titolo"] in visti:
            continue
        visti.add(r["titolo"])
        puliti.append(r)
    return puliti


# --------------------------------------------------------------------------
# FONTE 2: Uscite / novità Bugs Comics (focus Toni Bellasalma)
# --------------------------------------------------------------------------
BUGS_URL = "https://www.bugscomics.com/"


def fetch_bugs():
    risultati = []
    soup = _soup(BUGS_URL)
    if soup is None:
        return risultati

    for art in soup.select("article, .post, .product, .elementor-post"):
        link_tag = art.find("a", href=True)
        if not link_tag:
            continue
        titolo = link_tag.get_text(strip=True)
        img_tag = art.find("img")
        if not titolo:
            titolo = img_tag.get("alt", "").strip() if img_tag else ""
        if not titolo or len(titolo) < 3:
            continue

        href = link_tag["href"]
        cover = ""
        if img_tag:
            cover = img_tag.get("data-src") or img_tag.get("src") or ""

        # Marca Bellasalma se compare nel titolo (poi filtreremo in homepage).
        bellasalma = bool(re.search(r"bellasalma", titolo, re.I))

        risultati.append({
            "tipo": "uscita",
            "editore": "Bugs Comics",
            "serie": "Toni Bellasalma" if bellasalma else "",
            "titolo": titolo,
            "data": "",
            "cover": cover,
            "link": href,
            "fonte": "Bugs Comics",
        })

    visti = set()
    puliti = []
    for r in risultati:
        if r["titolo"] in visti:
            continue
        visti.add(r["titolo"])
        puliti.append(r)
    return puliti


# --------------------------------------------------------------------------
# FONTE 3: Notizie (via RSS, filtrate per parole chiave)
# --------------------------------------------------------------------------
# Gli RSS sono la via pulita per le news. Qui mettiamo alcuni portali fumetti
# italiani. Se un feed non risponde, lo saltiamo. Aggiungine/togline liberamente.
FEED_NEWS = [
    "https://www.lospaziobianco.it/feed/",
    "https://www.fumettologica.it/feed/",
]

PAROLE_CHIAVE = ["dylan dog", "bellasalma", "bonelli", "bugs comics", "sclavi"]


def fetch_news():
    import feedparser  # import locale: serve solo qui

    risultati = []
    for feed_url in FEED_NEWS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] feed {feed_url} -> {e}", file=sys.stderr)
            continue

        fonte = feed.feed.get("title", feed_url)
        for entry in feed.entries:
            titolo = entry.get("title", "")
            riassunto = entry.get("summary", "")
            testo = f"{titolo} {riassunto}".lower()
            if not any(k in testo for k in PAROLE_CHIAVE):
                continue

            data = ""
            if entry.get("published_parsed"):
                data = time.strftime("%Y-%m-%d", entry.published_parsed)

            risultati.append({
                "tipo": "news",
                "editore": fonte,
                "serie": "",
                "titolo": titolo,
                "data": data,
                "cover": "",
                "link": entry.get("link", ""),
                "fonte": fonte,
            })
    return risultati


def fetch_all():
    """Raccoglie tutto, in modo che un errore su una fonte non fermi le altre."""
    tutto = []
    for nome, fn in [("Bonelli", fetch_bonelli),
                     ("Bugs Comics", fetch_bugs),
                     ("News", fetch_news)]:
        print(f"-> {nome} ...")
        try:
            dati = fn()
            print(f"   {len(dati)} elementi")
            tutto.extend(dati)
        except Exception as e:  # noqa: BLE001
            print(f"   [errore] {nome}: {e}", file=sys.stderr)
    return tutto
