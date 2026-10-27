"""
fetch_fixtures.py — AtmBetSignal Odds Fetcher
Scarica quote e palinsesto per i principali campionati europei e leghe secondarie ad alta liquidità tramite The Odds API.
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

API_KEY = os.environ.get("ODDSAPI_KEY", "").strip()
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "fixtures.json"

# Paniere Campionati Espanso (Top 5 + Leghe Strategiche ad Alta Efficienza)
LEAGUES = [
    # Top 5 Europee
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    # Coppe Europee
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    # Leghe ad Alta Liquidità & Regolarità Statistica
    "soccer_england_efl_cup",
    "soccer_england_league1",
    "soccer_england_championship",
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_belgium_first_div"
]

def fetch_league_odds(sport_key: str):
    if not API_KEY:
        print("Errore: ODDSAPI_KEY non trovata nelle variabili d'ambiente.")
        return []

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal"
    }

    try:
        res = requests.get(url, params=params, timeout=20)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            print("Errore: Chiave The Odds API non valida o scaduta.")
        else:
            print(f"Info: Nessun dato o status {res.status_code} per {sport_key}")
    except Exception as e:
        print(f"Errore connessione su {sport_key}: {e}")
    return []

def parse_match_data(raw_matches, sport_key: str):
    parsed = []
    for m in raw_matches:
        home_team = m.get("home_team")
        away_team = m.get("away_team")
        commence_time = m.get("commence_time")
        bookmakers = m.get("bookmakers", [])

        if not bookmakers:
            continue

        # Estrazione quote medie di mercato
        h2h_home, h2h_draw, h2h_away = [], [], []
        over25, under25 = [], []

        for b in bookmakers:
            for market in b.get("markets", []):
                if market.get("key") == "h2h":
                    for outcome in market.get("outcomes", []):
                        price = outcome.get("price", 0.0)
                        if outcome.get("name") == home_team and price > 1.0:
                            h2h_home.append(price)
                        elif outcome.get("name") == away_team and price > 1.0:
                            h2h_away.append(price)
                        elif outcome.get("name").lower() in ["draw", "pareggio"] and price > 1.0:
                            h2h_draw.append(price)
                elif market.get("key") == "totals":
                    for outcome in market.get("outcomes", []):
                        price = outcome.get("price", 0.0)
                        point = outcome.get("point", 0.0)
                        if point == 2.5:
                            if outcome.get("name").lower() in ["over", "più"]:
                                over25.append(price)
                            elif outcome.get("name").lower() in ["under", "meno"]:
                                under25.append(price)

        if not (h2h_home and h2h_draw and h2h_away):
            continue

        odd_1 = sum(h2h_home) / len(h2h_home)
        odd_x = sum(h2h_draw) / len(h2h_draw)
        odd_2 = sum(h2h_away) / len(h2h_away)

                # Calcolo quote sintetiche per Doppie Chance con correzione aggio standard
        prob_implied_1x = (1.0 / odd_1) + (1.0 / odd_x)
        odd_1x = round(1.0 / (prob_implied_1x * 0.94), 2) if prob_implied_1x > 0 else 0.0

        prob_implied_x2 = (1.0 / odd_2) + (1.0 / odd_x)
        odd_x2 = round(1.0 / (prob_implied_x2 * 0.94), 2) if prob_implied_x2 > 0 else 0.0

        # Calcolo quote sintetiche Draw No Bet (DNB / Rimborso in caso di parità)
        odd_dnb_1 = round(odd_1 * (1.0 - (1.0 / max(1.05, odd_x))), 2)
        odd_dnb_2 = round(odd_2 * (1.0 - (1.0 / max(1.05, odd_x))), 2)

        odd_over25 = sum(over25) / len(over25) if over25 else 0.0
        odd_under25 = sum(under25) / len(under25) if under25 else 0.0

        # Stima implicita Goal/NoGoal da Under/Over
        odd_btts_yes = round(odd_over25 * 0.95, 2) if odd_over25 > 1.30 else 1.80

        odds_dict = {
            "1": round(odd_1, 2),
            "X": round(odd_x, 2),
            "2": round(odd_2, 2),
            "1X": max(1.20, odd_1x),
            "X2": max(1.20, odd_x2),
            "OVER_25": round(odd_over25, 2) if odd_over25 > 1.0 else 0.0,
            "UNDER_25": round(odd_under25, 2) if odd_under25 > 1.0 else 0.0,
            "BTTS_YES": odd_btts_yes
        }

        parsed.append({
            "id": m.get("id"),
            "sport_key": sport_key,
            "league_name": m.get("sport_title", sport_key),
            "commence_time": commence_time,
            "home_team": home_team,
            "away_team": away_team,
            "odds": odds_dict
        })

    return parsed

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_fixtures = []

    print(f"Scansione in corso su {len(LEAGUES)} campionati...")
    for league in LEAGUES:
        raw = fetch_league_odds(league)
        matches = parse_match_data(raw, league)
        all_fixtures.extend(matches)

    output_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": len(all_fixtures),
        "fixtures": all_fixtures
    }

    OUTPUT_FILE.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completato: {len(all_fixtures)} match totali scaricati e pronti in data/fixtures.json.")

if __name__ == "__main__":
    main()
