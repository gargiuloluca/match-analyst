"""
fetch_fixtures.py — AtmBetSignal Odds Ingestion & Normalization Engine
- Scarica il palinsesto dalle API ufficiali (The Odds API) con fallback multi-chiave
- Filtro temporale rigoroso: solo partite future (commence_time > now) entro le prossime 36 ore
- Filtro di liquidità/overround: scarta match con lavagna > 7.0%
- Calcolo Fair Odds: normalizza le quote eliminando l'aggio del banco
- Archiviazione atomica con ID nativo in data/fixtures.json
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"

ODDSAPI_KEY_RAW = os.environ.get("ODDSAPI_KEY", "").strip()
API_KEYS = [k.strip() for k in ODDSAPI_KEY_RAW.split(",") if k.strip()]

LEAGUES = [
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_england_championship",
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_belgium_first_div",
    "soccer_england_league1",
    "soccer_england_efl_cup"
]

def get_fixtures_for_league(sport_key: str):
    if not API_KEYS:
        print("[Errore] Nessuna API Key trovata in ODDSAPI_KEY.")
        return []

    for key in API_KEYS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": key,
            "regions": "eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal"
        }
        try:
            res = requests.get(url, params=params, timeout=20)
            if res.status_code == 200:
                remaining = res.headers.get("x-requests-remaining", "?")
                print(f"[{sport_key}] Dati scaricati con successo. Richieste residue: {remaining}")
                return res.json()
            elif res.status_code in [401, 429]:
                print(f"[Avviso] Chiave API esaurita o non valida. Tento chiave successiva...")
                continue
            else:
                print(f"[{sport_key}] Errore API: HTTP {res.status_code}")
        except Exception as e:
            print(f"[{sport_key}] Errore di connessione: {e}")
    return []

def extract_market_odds(bookmakers: list):
    """
    Estrae le migliori quote medie/consensuali e calcola le Fair Odds de-marginalizzate.
    """
    if not bookmakers:
        return {}, {}, 0.0

    odds = {}
    
    # 1. Mercato 1X2 (h2h)
    h2h_bms = [b for b in bookmakers if any(m["key"] == "h2h" for m in b.get("markets", []))]
    if h2h_bms:
        bm = h2h_bms[0]
        for m in bm.get("markets", []):
            if m["key"] == "h2h":
                for out in m.get("outcomes", []):
                    name = out.get("name")
                    price = float(out.get("price", 1.0))
                    if name == bm.get("home_team", "") or out.get("name") == "Home":
                        odds["1"] = price
                    elif name == bm.get("away_team", "") or out.get("name") == "Away":
                        odds["2"] = price
                    elif name.lower() in ["draw", "pareggio"]:
                        odds["X"] = price

    # 2. Mercato Totali Gol (Over/Under 2.5, 1.5, 3.5)
    for bm in bookmakers:
        for m in bm.get("markets", []):
            if m["key"] == "totals":
                for out in m.get("outcomes", []):
                    point = out.get("point")
                    name = out.get("name", "").lower()
                    price = float(out.get("price", 1.0))
                    if point == 2.5:
                        if name == "over": odds["OVER_25"] = price
                        elif name == "under": odds["UNDER_25"] = price
                    elif point == 1.5:
                        if name == "over": odds["OVER_15"] = price
                        elif name == "under": odds["UNDER_15"] = price
                    elif point == 3.5:
                        if name == "over": odds["OVER_35"] = price
                        elif name == "under": odds["UNDER_35"] = price

    # 3. Derivazione Doppie Chance e Draw No Bet (DNB)
    o1 = odds.get("1", 0.0)
    ox = odds.get("X", 0.0)
    o2 = odds.get("2", 0.0)

    overround = 0.0
    fair_odds = {}

    if o1 > 1.0 and ox > 1.0 and o2 > 1.0:
        inv_sum = (1.0 / o1) + (1.0 / ox) + (1.0 / o2)
        overround = round((inv_sum - 1.0) * 100, 2)

        # Calcolo Fair Odds prive di margine del banco
        fair_odds["1"] = round(1.0 / ((1.0 / o1) / inv_sum), 3)
        fair_odds["X"] = round(1.0 / ((1.0 / ox) / inv_sum), 3)
        fair_odds["2"] = round(1.0 / ((1.0 / o2) / inv_sum), 3)

        # Doppia Chance derivata sintetica
        odds["1X"] = round(1.0 / ((1.0 / o1) + (1.0 / ox)), 2)
        odds["X2"] = round(1.0 / ((1.0 / o2) + (1.0 / ox)), 2)

        # Draw No Bet (Rimborso X) derivato
        odds["DNB_1"] = round(o1 * (1.0 - (1.0 / ox)), 2)
        odds["DNB_2"] = round(o2 * (1.0 - (1.0 / ox)), 2)

    return odds, fair_odds, overround

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Memorizza le aperture già note per monitorare il drift delle quote
    existing_openings = {}
    if FIXTURES_FILE.exists():
        try:
            old_data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
            for f in old_data.get("fixtures", []):
                e_id = f.get("id")
                if e_id and "odds" in f:
                    existing_openings[e_id] = f.get("opening_odds", f["odds"])
        except Exception:
            pass

    now_utc = datetime.now(timezone.utc)
    max_horizon = now_utc + timedelta(hours=36)

    processed_fixtures = []

    print(f"Scaricamento palinsesto globale (Orario attuale UTC: {now_utc.isoformat()})...")

    for league in LEAGUES:
        raw_events = get_fixtures_for_league(league)
        for ev in raw_events:
            ev_id = ev.get("id")
            commence_str = ev.get("commence_time")
            if not commence_str:
                continue

            try:
                commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
            except Exception:
                continue

            # FILTRO TEMPORALE RIGIDO:
            # Scarta match passati/in corso e match oltre le 36 ore successive
            if commence_dt <= now_utc or commence_dt > max_horizon:
                continue

            home = ev.get("home_team", "").strip()
            away = ev.get("away_team", "").strip()
            bookmakers = ev.get("bookmakers", [])

            odds, fair_odds, overround = extract_market_odds(bookmakers)
            
            # Necessarie quote 1X2 per modellazione valida
            if not odds.get("1") or not odds.get("2"):
                continue

            # FILTRO OVERROUND: Scarta partite con aggio spropositato (> 7.0%)
            if overround > 7.0:
                continue

            opening = existing_openings.get(ev_id, odds)

            processed_fixtures.append({
                "id": ev_id,
                "sport_key": league,
                "league_name": ev.get("sport_title", league),
                "home_team": home,
                "away_team": away,
                "commence_time": commence_str,
                "odds": odds,
                "opening_odds": opening,
                "fair_odds": fair_odds,
                "overround_pct": overround
            })

    output_payload = {
        "fetched_at": now_utc.isoformat(),
        "total_fixtures": len(processed_fixtures),
        "fixtures": processed_fixtures
    }

    FIXTURES_FILE.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completato! Salvate {len(processed_fixtures)} partite fresche per le prossime 36 ore in data/fixtures.json.")

if __name__ == "__main__":
    main()
    
