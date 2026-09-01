# Match Analyst

Strumento personale di screening per il calcio: ogni giorno filtra gli eventi in
programma incrociando statistiche di forma, quote e notizie extra-campo
(infortuni, crisi societarie, tensioni nello spogliatoio), e propone **3
pronostici** per gli eventi più solidi — conservativo, consigliato, hard —
con la probabilità stimata e il margine (edge) rispetto alla quota di mercato.

Pensato per supportare uno studio metodico delle giocate in singola, non per
sostituire il giudizio di chi gioca. Include anche uno storico per tracciare
esiti, ROI e hit rate nel tempo.

> ⚠️ Nessuno strumento statistico garantisce risultati. Le probabilità qui
> calcolate sono stime basate su dati storici e pubblici: usale come supporto
> alla decisione, non come certezza. Gioca solo ciò che puoi permetterti di
> perdere.

## Come funziona

```
GitHub Actions (cron giornaliero)
        │
        ├── fetch_fixtures.py   → partite, forma, quote (football-data.org + the-odds-api.com)
        ├── fetch_news.py       → notizie extra-campo da feed RSS pubblici
        └── analyze.py          → filtro, scoring, 3 pronostici per evento
                                       │
                                       ▼
                              data/latest.json
                                       │
                                       ▼
                        index.html (dashboard, GitHub Pages)
```

Tutto gira su infrastruttura gratuita di GitHub: Actions esegue lo script,
Pages serve la dashboard statica che legge il JSON prodotto. Nessun server da
pagare o mantenere.

## Setup — prima testa in locale, poi sposta su GitHub

### 1. Chiavi API necessarie (entrambe gratis, nessuna carta richiesta)

| Servizio | Uso | Dove registrarsi | Cosa serve |
|---|---|---|---|
| football-data.org | Partite, classifica, forma | football-data.org/client/register | solo email |
| the-odds-api.com | Quote 1X2 | the-odds-api.com → "Get API key" | solo email |

Le notizie extra-campo usano feed RSS pubblici (Gazzetta, ANSA, TMW): **nessuna
registrazione necessaria** per quelle.

### 2. Testa tutto in locale, prima di toccare GitHub

Serve Python 3.10+ installato sul tuo computer. Poi, da dentro la cartella
del progetto:

```bash
export FOOTBALLDATA_KEY="la-tua-chiave-footballdata"
export ODDSAPI_KEY="la-tua-chiave-oddsapi"
./test_locale.sh
```

Lo script installa le dipendenze, scarica i dati veri e genera
`data/latest.json`. Se qualcosa va storto, l'errore appare direttamente nel
terminale — più facile da diagnosticare che dentro un'Action su GitHub.

Per vedere la dashboard con i dati appena generati:

```bash
python -m http.server 8000
```

e apri `http://localhost:8000` nel browser. (Serve un mini-server locale
perché il browser blocca il caricamento diretto di file JSON da `file://`.)

Solo quando questo funziona bene, passa al punto 3.

### 3. Sposta tutto su GitHub

Carica il repository su GitHub, poi:

**Settings → Secrets and variables → Actions → New repository secret**
- `FOOTBALLDATA_KEY`
- `ODDSAPI_KEY`

**Settings → Pages → Source: Deploy from branch → Branch: main, folder: / (root)**

Dopo qualche minuto la dashboard sarà raggiungibile a:
`https://<tuo-utente>.github.io/<nome-repo>/`

### 4. Attiva l'Action

Il workflow in `.github/workflows/daily-analysis.yml` gira automaticamente
ogni giorno alle 08:00 UTC (9-10 del mattino ora italiana). Puoi anche
lanciarlo a mano da **Actions → Daily Analysis → Run workflow**.

## Struttura dati

- `data/latest.json` — output del giorno corrente, letto dalla dashboard
- `data/history/` — archivio di ogni run giornaliera (uno per data)
- `data/tracker.json` — le tue giocate registrate, con esito ed esito atteso

## Come si calcolano i 3 pronostici

Per ogni evento che supera il filtro iniziale (scarto di forma minimo,
assenza di notizie ad alto impatto non ancora prezzate dal mercato):

1. **Conservativo** — l'esito con probabilità stimata più alta, a prescindere
   dall'edge. Quota bassa, rischio minimo.
2. **Consigliato** — l'esito con il miglior rapporto tra probabilità stimata
   e probabilità implicita dalla quota (il classico criterio di *value
   betting*: gioco quando penso che l'evento sia più probabile di quanto dica
   il mercato).
3. **Hard** — un esito plausibile ma a quota più alta, proposto solo se
   l'edge stimato è comunque positivo: più rischio, ma non un azzardo cieco.

Il dettaglio del calcolo è in `scripts/analyze.py`, commentato passo per
passo — modificalo liberamente per adattarlo ai tuoi criteri.

## Prossimi passi consigliati

- Sostituisci il modello di probabilità placeholder (basato su forma
  recente) con un modello Poisson o un gradient boosting allenato sullo
  storico dei campionati che segui
- Aggiungi le leghe/campionati che ti interessano in `scripts/fetch_fixtures.py`
- Collega il tracker a un form per registrare le giocate dal telefono (es.
  Google Form → Google Sheet → sync periodico nel repo)
