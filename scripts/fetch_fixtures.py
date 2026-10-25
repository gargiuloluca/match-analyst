"""
fetch_fixtures.py — AtmBetSignal Safe API Fetcher.
Ottimizza le chiamate API in base al giorno della settimana per rientrare
ampiamente nelle 500 richieste mensili gratuite di The Odds API.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ODDS_API_KEY = os.environ.get("ODDSAPI_KEY", "").strip()
ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

NOW_UTC = datetime.now(timezone.utc)
TODAY_STR = NOW_UTC.strftime("%Y-%m-%d")
WEEKDAY = NOW_UTC.weekday()  # 0 = Lunedì, ..., 4 = Venerdì, 5 = Sabato, 6 = Domenica

ALL_LEAGUES = [
    # Top 5 Campionati e Coppe
    {"name": "Serie A", "odds_key": "soccer_italy_serie_a", "weekend_only": True},
    {"name": "Premier League", "odds_key": "soccer_epl", "weekend_only": True},
    {"name": "La Liga", "odds_key": "soccer_spain_la_liga", "weekend_only": True},
    {"name": "Bundesliga", "odds_key": "soccer_germany_bundesliga", "weekend_only": True},
    {"name": "Ligue 1", "odds_key": "soccer_france_ligue_one", "weekend_only": True},
    {"name": "Champions League", "odds_key": "soccer_uefa_champs_league", "weekend_only": False},
    {"name": "Europa League", "odds_key": "soccer_uefa_europa_league", "weekend_only": False},
    {"name": "Conference League", "odds_key": "soccer_uefa_europa_conference_league", "weekend_only": False},

    # Seconde Divisioni
    {"name": "Serie B (Italia)", "odds_key": "soccer_italy_serie_b", "weekend_only": True},
    {"name": "Championship (Inghilterra)", "odds_key": "soccer_efl_champ", "weekend_only": False},
    {"name": "Segunda División (Spagna)", "odds_key": "soccer_spain_segunda_division", "weekend_only": True},
    {"name": "2. Bundesliga (Germania)", "odds_key": "soccer_germany_bundesliga2", "weekend_only": True},

    # Campionati Secondari Europei
    {"name": "Eredivisie (Olanda)", "odds_key": "soccer_netherlands_eredivisie", "weekend_only": True},
    {"name": "Primeira Liga (Portogallo)", "odds_key": "soccer_portugal_primeira_liga", "weekend_only": True},
    {"name": "Jupiler Pro League (Belgio)", "odds_key": "soccer_belgium_first_div", "weekend_only": True},
    {"name": "Süper Lig (Turchia)", "odds_key": "soccer_turkey_super_league", "weekend_only": False},
    {"name": "Premiership (Scozia)", "odds_key": "soccer_spl", "weekend_only": True},
    {"name": "Super League (Svizzera)", "odds_key": "soccer_switzerland_superleague", "weekend_only": True},
    {"name": "Bundesliga (Austria)", "odds_key": "soccer_austria_bundesliga", "weekend_only": True},

    # Extra Europei
    {"name": "Brasileirão (Brasile)", "odds_key": "soccer_brazil_campeonato", "weekend_only": False},
    {"name": "MLS (USA)", "odds_key": "soccer_usa_mls", "weekend_only": False},
]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_leagues_to_scan():
    # Dal venerdì alla domenica scansiona tutto il palinsesto
    if WEEKDAY in (4, 5, 6):
        return ALL_LEAGUES
    # Dal lunedì al giovedì scansiona coppe, campionati infrasettimanali e top leghe
    return [l for l in ALL_LEAGUES if not l.get("weekend_only") or l["name"] in ("Serie A", "Premier League", "La Liga")]


def fetch_matches():
    if not ODDS_API_KEY:
        print("ERRORE: ODDSAPI_KEY mancante!")
        return []

    from_iso = f"{TODAY_STR}T00:00:00Z"
    to_iso = f"{TODAY_STR}T23:59:59Z"

    fixtures_today = []
    target_leagues = get_leagues_to_scan()
    print(f"Safe API Mode: scansione mirata su {len(target_leagues)} campionati.")

    for league in target_leagues:
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
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                continue

            remaining = resp.headers.get("x-requests-remaining")
            if remaining:
                print(f"Crediti API residui per questo mese: {remaining}")

            events = resp.json()
            for ev in events:
                commence_time = ev.get("commence_time", "")
                if not commence_time.startswith(TODAY_STR):
                    continue

                home = ev.get("home_team")
                away = ev.get("away_team")
                bookmakers = ev.get("bookmakers", [])

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

                h_odds.sort()
                d_odds.sort()
                a_odds.sort()
                mid = len(h_odds) // 2

                fixtures_today.append({
                    "fixture_id": ev.get("id"),
                    "league": league["name"],
                    "odds_key": league["odds_key"],
                    "commence_time": commence_time,
                    "home_team": {"name": home},
                    "away_team": {"name": away},
                    "bookmaker_count": len(h_odds),
                    "odds": {
                        "home": round(h_odds[mid], 2),
                        "draw": round(d_odds[mid], 2),
                        "away": round(a_odds[mid], 2),
                    }
                })
        except Exception as e:
            print(f"Errore su {league['name']}: {e}")

    return fixtures_today


def main():
    fixtures = fetch_matches()
    out_path = OUTPUT_DIR / f"fixtures_{TODAY_STR}.json"
    out_path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Partite scaricate oggi ({TODAY_STR}): {len(fixtures)}")


if __name__ == "__main__":
    main()
