"""
fetch_fixtures.py — AtmBetSignal Odds Ingestion & Normalization Engine (V3 Robust - Day & Night Focus)
- Fallback multi-chiave API con gestione header di quota residua
- Parsing robusto di quote 1X2 (h2h) e Totali indipendentemente dal formato bookmaker
- Finestra temporale estesa: include tutto il giorno in corso fino alle 05:00 del mattino seguente (UTC)
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

LEAGUES = [
    # --- TOP CAMPIONATI EUROPEI ---
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    
    # --- COMPETIZIONI EUROPEE ---
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    
    # --- CAMPIONATI CADETTI AD ALTA PREVEDIBILITÀ ---
    "soccer_efl_champ",
    "soccer_italy_serie_b",
    "soccer_spain_segunda_division",
    
    # --- NORD EUROPA & GOAL LEAGUES (Alto valore statistico) ---
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_belgium_first_div",
    "soccer_denmark_superliga",
    "soccer_sweden_allsvenskan",
    "soccer_norway_eliteserien",
    "soccer_austria_bundesliga",
    "soccer_switzerland_super_league",
    
    # --- INGHILTERRA LOWER LEAGUES ---
    "soccer_england_league1",
    "soccer_england_league2",
    "soccer_england_efl_cup",

    # --- EXTRA EUROPE & VALORE INTERNAZIONALE VERIFICATO ---
    "soccer_poland_ekstraklasa",
    "soccer_argentina_primera_division",
    "soccer_usa_mls"
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

    o1 = odds.get("1", 0.0)
    ox = odds.get("X", 0.0)
    o2 = odds.get("2", 0.0)

    overround = 0.0
    fair_odds = {}

    if o1 > 1.0 and ox > 1.0 and o2 > 1.0:
        inv_sum = (1.0 / o1) + (1.0 / ox) + (1.0 / o2)
        overround = round((inv_sum - 1.0) * 100, 2)

        fair_odds["1"] = round(1.0 / ((1.0 / o1) / inv_sum), 3)
        fair_odds["X"] = round(1.0 / ((1.0 / ox) / inv_sum), 3)
        fair_odds["2"] = round(1.0 / ((1.0 / o2) / inv_sum), 3)

        odds["1X"] = round(1.0 / ((1.0 / o1) + (1.0 / ox)), 2)
        odds["X2"] = round(1.0 / ((1.0 / o2) + (1.0 / ox)), 2)

        odds["DNB_1"] = round(o1 * (1.0 - (1.0 / ox)), 2)
        odds["DNB_2"] = round(o2 * (1.0 - (1.0 / ox)), 2)

    return odds, fair_odds, overround

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

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
    min_horizon = now_utc - timedelta(minutes=15)
    
    # Finestra intelligente: copre tutto oggi e si estende fino alle 05:00 del mattino successivo (UTC)
    next_day = now_utc + timedelta(days=1)
    max_horizon = datetime(next_day.year, next_day.month, next_day.day, 5, 0, 0, tzinfo=timezone.utc)

    processed_fixtures = []
    print(f"Avvio scaricamento palinsesto (Copertura fino alle 05:00 di domani UTC)...")

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

            # Filtro temporale: da adesso fino alle 05:00 del giorno dopo
            if commence_dt < min_horizon or commence_dt > max_horizon:
                continue

            home = ev.get("home_team", "").strip()
            away = ev.get("away_team", "").strip()
            bookmakers = ev.get("bookmakers", [])

            odds, fair_odds, overround = extract_market_odds(bookmakers, home, away)

            if not odds.get("1") or not odds.get("2"):
                continue

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
    print(f"Operazione completata: salvate {len(processed_fixtures)} partite (inclusi match serali/notturni) in data/fixtures.json.")

if __name__ == "__main__":
    main()
