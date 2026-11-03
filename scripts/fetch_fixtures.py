"""
fetch_fixtures.py — AtmBetSignal Odds Ingestion & Normalization Engine (V3 Robust)
- Fallback multi-chiave API con gestione header di quota residua
- Parsing robusto di quote 1X2 (h2h) e Totali indipendentemente dal formato bookmaker
- Finestra temporale dinamica a 72 ore (copre turni infrasettimanali e coppe)
- Filtro liquidità: overround <= 7.5% per evitare lavagne opache
- Generazione automatica di Fair Odds de-marginalizzate
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

# Chiavi ufficiali verificate The Odds API
LEAGUES = [
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_efl_champ",            # Corretto: era soccer_england_championship (404)
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_belgium_first_div",
    "soccer_england_league1",
    "soccer_england_efl_cup"
]

def get_fixtures_for_league(sport_key: str):
    if not API_KEYS:
        print("[Errore] Nessuna chiave API configurata in ODDSAPI_KEY.")
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
                print(f"[{sport_key}] Dati scaricati con successo. Chiamate residue: {remaining}")
                return res.json()
            elif res.status_code in [401, 429]:
                print(f"[Avviso] Chiave {key[:6]}... esaurita o errata. Tento chiave successiva...")
                continue
            else:
                print(f"[{sport_key}] Errore API HTTP {res.status_code}")
        except Exception as e:
            print(f"[{sport_key}] Errore connessione: {e}")
    return []

def extract_market_odds(bookmakers: list, home_team: str, away_team: str):
    if not bookmakers:
        return {}, {}, 0.0

    odds = {}
    h_clean = home_team.strip().lower()
    a_clean = away_team.strip().lower()

    # 1. Estrazione quote 1X2 cercando il primo bookmaker con mercato completo
    for bm in bookmakers:
        for m in bm.get("markets", []):
            if m.get("key") == "h2h":
                outcomes = m.get("outcomes", [])
                for out in outcomes:
                    name = out.get("name", "").strip().lower()
                    price = float(out.get("price", 0.0))
                    if name == h_clean or name == "home":
                        odds["1"] = price
                    elif name == a_clean or name == "away":
                        odds["2"] = price
                    elif name in ["draw", "pareggio"]:
                        odds["X"] = price
        if "1" in odds and "2" in odds and "X" in odds:
            break

    # 2. Estrazione Totali (Over/Under 1.5, 2.5, 3.5)
    for bm in bookmakers:
        for m in bm.get("markets", []):
            if m.get("key") == "totals":
                for out in m.get("outcomes", []):
                    pt = out.get("point")
                    side = out.get("name", "").strip().lower()
                    price = float(out.get("price", 0.0))
                    if pt == 2.5:
                        if side == "over": odds["OVER_25"] = price
                        elif side == "under": odds["UNDER_25"] = price
                    elif pt == 1.5:
                        if side == "over": odds["OVER_15"] = price
                        elif side == "under": odds["UNDER_15"] = price
                    elif pt == 3.5:
                        if side == "over": odds["OVER_35"] = price
                        elif side == "under": odds["UNDER_35"] = price

    # 3. Derivazione Fair Odds, Doppia Chance e Draw No Bet (DNB)
    o1 = odds.get("1", 0.0)
    ox = odds.get("X", 0.0)
    o2 = odds.get("2", 0.0)

    overround = 0.0
    fair_odds = {}

    if o1 > 1.0 and ox > 1.0 and o2 > 1.0:
        inv_sum = (1.0 / o1) + (1.0 / ox) + (1.0 / o2)
        overround = round((inv_sum - 1.0) * 100, 2)

        # Riconduzione a probabilità pura e calcolo quota equa (Fair Odd)
        fair_odds["1"] = round(1.0 / ((1.0 / o1) / inv_sum), 3)
        fair_odds["X"] = round(1.0 / ((1.0 / ox) / inv_sum), 3)
        fair_odds["2"] = round(1.0 / ((1.0 / o2) / inv_sum), 3)

        # Doppia Chance derivata (regola delle probabilità congiunte)
        odds["1X"] = round(1.0 / ((1.0 / o1) + (1.0 / ox)), 2)
        odds["X2"] = round(1.0 / ((1.0 / o2) + (1.0 / ox)), 2)

        # Draw No Bet (Rimborso Pareggio)
        odds["DNB_1"] = round(o1 * (1.0 - (1.0 / ox)), 2)
        odds["DNB_2"] = round(o2 * (1.0 - (1.0 / ox)), 2)

    return odds, fair_odds, overround

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Conserva opening_odds per calcolo dello scostamento Smart Money
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
    # Tolleranza di 15 minuti indietro per match appena iniziati e orizzonte a 72 ore
    min_horizon = now_utc - timedelta(minutes=15)
    max_horizon = now_utc + timedelta(hours=72)

    processed_fixtures = []
    print(f"Avvio scaricamento palinsesto (Finestra: 72 ore da {now_utc.strftime('%Y-%m-%d %H:%M UTC')})...")

    for league in LEAGUES:
        raw_events = get_fixtures_for_league(league)
        if not raw_events:
            continue

        for ev in raw_events:
            ev_id = ev.get("id")
            commence_str = ev.get("commence_time")
            if not commence_str:
                continue

            try:
                commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
            except Exception:
                continue

            # Filtro temporale a 72h
            if commence_dt < min_horizon or commence_dt > max_horizon:
                continue

            home = ev.get("home_team", "").strip()
            away = ev.get("away_team", "").strip()
            bookmakers = ev.get("bookmakers", [])

            odds, fair_odds, overround = extract_market_odds(bookmakers, home, away)

            # Per entrare nel modello quantitativo devono esistere almeno 1 e 2
            if not odds.get("1") or not odds.get("2"):
                continue

            # Filtro liquidità (scarta mercati con aggio > 7.5%)
            if overround > 7.5:
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
    print(f"Operazione completata: salvate {len(processed_fixtures)} partite in data/fixtures.json.")

if __name__ == "__main__":
    main()
