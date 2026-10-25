"""
fetch_fixtures.py — AtmBetSignal Consensus Fetcher.
Scarica le partite odierne (UTC) verificando la presenza di consenso tra bookmaker
su campionati principali e secondari.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ODDS_API_KEY = os.environ.get("ODDSAPI_KEY", "").strip()
ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

LEAGUES = [
    # Top 5 Campionati e Coppe Europee
    {"name": "Serie A", "odds_key": "soccer_italy_serie_a"},
    {"name": "Premier League", "odds_key": "soccer_epl"},
    {"name": "La Liga", "odds_key": "soccer_spain_la_liga"},
    {"name": "Bundesliga", "odds_key": "soccer_germany_bundesliga"},
    {"name": "Ligue 1", "odds_key": "soccer_france_ligue_one"},
    {"name": "Champions League", "odds_key": "soccer_uefa_champs_league"},
    {"name": "Europa League", "odds_key": "soccer_uefa_europa_league"},
    {"name": "Conference League", "odds_key": "soccer_uefa_europa_conference_league"},

    # Seconde Divisioni
    {"name": "Serie B (Italia)", "odds_key": "soccer_italy_serie_b"},
    {"name": "Championship (Inghilterra)", "odds_key": "soccer_efl_champ"},
    {"name": "Segunda División (Spagna)", "odds_key": "soccer_spain_segunda_division"},
    {"name": "2. Bundesliga (Germania)", "odds_key": "soccer_germany_bundesliga2"},

    # Campionati Europei Secondari ad alto valore
    {"name": "Eredivisie (Olanda)", "odds_key": "soccer_netherlands_eredivisie"},
    {"name": "Primeira Liga (Portogallo)", "odds_key": "soccer_portugal_primeira_liga"},
    {"name": "Jupiler Pro League (Belgio)", "odds_key": "soccer_belgium_first_div"},
    {"name": "Süper Lig (Turchia)", "odds_key": "soccer_turkey_super_league"},
    {"name": "Premiership (Scozia)", "odds_key": "soccer_spl"},
    {"name": "Super League (Svizzera)", "odds_key": "soccer_switzerland_superleague"},
    {"name": "Bundesliga (Austria)", "odds_key": "soccer_austria_bundesliga"},

    # Campionati Extra-Europei
    {"name": "Brasileirão (Brasile)", "odds_key": "soccer_brazil_campeonato"},
    {"name": "MLS (USA)", "odds_key": "soccer_usa_mls"},
]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_matches():
    if not ODDS_API_KEY:
        print("ERRORE: Secret ODDSAPI_KEY mancante!")
        return []

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    from_iso = f"{today_str}T00:00:00Z"
    to_iso = f"{today_str}T23:59:59Z"

    fixtures_today = []

    for league in LEAGUES:
        url = f"{ODDS_BASE_URL}/sports/{league['odds_key']}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "commenceTimeFrom": from_iso,
            "commenceTimeTo": to_iso,
        }

        try:
            resp = requests.get(url, params=params, timeout=20)
            if resp.status_code != 200:
                continue

            events = resp.json()
            for ev in events:
                commence_time = ev.get("commence_time", "")
                if not commence_time.startswith(today_str):
                    continue

                home = ev.get("home_team")
                away = ev.get("away_team")
                bookmakers = ev.get("bookmakers", [])

                # Filtro Liquidità: Richiede almeno 2 bookmaker per validare il consenso
                if len(bookmakers) < 2:
                    continue

                h_odds, d_odds, a_odds = [], [], []

                for bm in bookmakers:
                    markets = bm.get("markets", [])
                    if not markets:
                        continue
                    outcomes = {o["name"]: float(o["price"]) for o in markets[0].get("outcomes", [])}
                    if outcomes.get(home) and outcomes.get("Draw") and outcomes.get(away):
                        h_odds.append(outcomes[home])
                        d_odds.append(outcomes["Draw"])
                        a_odds.append(outcomes[away])

                if len(h_odds) < 2:
                    continue

                # Calcolo quota mediana/consenso di mercato
                h_odds.sort()
                d_odds.sort()
                a_odds.sort()
                mid = len(h_odds) // 2
                median_h = h_odds[mid]
                median_d = d_odds[mid]
                median_a = a_odds[mid]

                fixtures_today.append({
                    "fixture_id": ev.get("id"),
                    "league": league["name"],
                    "commence_time": commence_time,
                    "home_team": {"name": home},
                    "away_team": {"name": away},
                    "bookmaker_count": len(h_odds),
                    "odds": {
                        "home": round(median_h, 2),
                        "draw": round(median_d, 2),
                        "away": round(median_a, 2),
                        "max_home": max(h_odds),
                        "max_draw": max(d_odds),
                        "max_away": max(a_odds)
                    }
                })
        except Exception as e:
            print(f"Errore scansione {league['name']}: {e}")

    return fixtures_today


def main():
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    fixtures = fetch_matches()
    out_path = OUTPUT_DIR / f"fixtures_{today_str}.json"
    out_path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Scaricamento completato: {len(fixtures)} partite con consenso confermato per oggi ({today_str}).")


if __name__ == "__main__":
    main()
