# Fumetti Tracker

Web app personale che raccoglie **uscite Bonelli** (con Dylan Dog in evidenza),
**uscite Bugs Comics** (con Toni Bellasalma in evidenza) e **notizie** sul mondo
Dylan Dog / Bellasalma. Si aggiorna da sola e si usa dal telefono come un'app.

## Come funziona (in due pezzi)

1. **Il robot** (`scraper/` + GitHub Actions): gira ogni 6 ore nel cloud, legge
   le fonti, e scrive `docs/data.json`.
2. **La pagina** (`docs/`): sito statico pubblicato con GitHub Pages. Legge
   `data.json` e mostra tutto. È una PWA → dal telefono "Aggiungi a schermata Home".

Nessun server da pagare, nessun PC acceso.

---

## Messa in funzione (una volta sola)

### 1. Carica il progetto su GitHub
Crea un repository nuovo (es. `fumetti-tracker`) e carica questi file.
Da terminale, dentro la cartella del progetto:

```bash
git init
git add .
git commit -m "primo commit"
git branch -M main
git remote add origin https://github.com/TUO-UTENTE/fumetti-tracker.git
git push -u origin main
```

### 2. Attiva GitHub Pages
Nel repo → **Settings → Pages**:
- *Source*: **Deploy from a branch**
- *Branch*: **main**, cartella **/docs**
- Salva.

Dopo un minuto il sito è online a:
`https://TUO-UTENTE.github.io/fumetti-tracker/`

### 3. Attiva il robot
Nel repo → tab **Actions** → se chiede conferma, abilita i workflow.
Poi apri "Aggiorna dati fumetti" → **Run workflow** per lanciarlo subito la
prima volta. Dopo gira da solo ogni 6 ore.

### 4. Installa sul telefono
Apri l'URL del sito nel browser del telefono → menu → **Aggiungi a schermata
Home**. Da lì in poi è un'icona come un'app.

---

## Tarare le fonti (la parte da sistemare)

Lo scraping parte da selettori "larghi" che vanno affinati guardando le pagine
reali. Finché non lo fai, alcune sezioni possono restare vuote: è normale.

- **Bonelli** e **Bugs**: apri la pagina delle uscite nel browser, guarda com'è
  fatto l'HTML (tasto destro → Ispeziona) e aggiorna i selettori `.select(...)`
  nelle funzioni `fetch_bonelli()` / `fetch_bugs()` in `scraper/sources.py`.
- **Notizie**: in `sources.py`, lista `FEED_NEWS` (aggiungi/togli RSS) e
  `PAROLE_CHIAVE` (le parole che fanno "passare" una notizia).

Per provare in locale:
```bash
pip install -r scraper/requirements.txt
python scraper/build.py
# poi apri docs/index.html con un piccolo server:
python -m http.server --directory docs
```

## Note
- Le copertine vengono **linkate**, non scaricate (sono immagini protette).
- Lo scraper si identifica e non martella i siti. Resta un uso personale.
