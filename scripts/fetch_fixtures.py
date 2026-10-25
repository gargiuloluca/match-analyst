"""
fetch_fixtures.py
Scarica SOLO le partite con fischio d'inizio nella data odierna (00:00 - 23:59 UTC)
per le leghe europee principali da The Odds API.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests

ODDS_API_KEY = os.environ.get("ODDSAPI_KEY", "")
ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

LEAGUES = [
    {"name": "Serie A", "odds_key": "soccer_italy_serie_a"},
    {"name": "Premier League", "odds_key": "soccer_epl"},
    {"name": "La Liga", "odds_key": "soccer_spain_la_liga"},
    {"name": "Bundesliga", "odds_key": "soccer_germany_bundesliga"},
    {"name": "Ligue 1", "odds_key": "soccer_france_ligue_one"},
    {"name": "Champions League", "odds_key": "soccer_uefa_champs_league"},
]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_today_matches():
    if not ODDS_API_KEY:
        print("ERRORE: ODDSAPI_KEY mancante!")
        return []

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    # Finestra: da mezzanotte di oggi alle 23:59:59 di stasera
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
                print(f"[{league['name']}] Errore HTTP {resp.status_code}: {resp.text}")
                continue

            events = resp.json()
            for ev in events:
                commence_time = ev.get("commence_time", "")
                if not commence_time.startswith(today_str):
                    continue

                home = ev.get("home_team")
                away = ev.get("away_team")

                if not ev.get("bookmakers"):
                    continue

                market = ev["bookmakers"][0].get("markets", [{}])[0]
                outcomes = {o["name"]: float(o["price"]) for o in market.get("outcomes", [])}

                h_odd = outcomes.get(home)
                d_odd = outcomes.get("Draw")
                a_odd = outcomes.get(away)

                if h_odd and d_odd and a_odd:
                    fixtures_today.append({
                        "fixture_id": ev.get("id"),
                        "league": league["name"],
                        "commence_time": commence_time,
                        "home_team": {"name": home},
                        "away_team": {"name": away},
                        "odds": {
                            "home": h_odd,
                            "draw": d_odd,
                            "away": a_odd,
                            "bookmaker": ev["bookmakers"][0].get("title", "Bookmaker"),
                        }
                    })
        except Exception as e:
            print(f"Errore su {league['name']}: {e}")

    return fixtures_today


def main():
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    fixtures = fetch_today_matches()

    out_path = OUTPUT_DIR / f"fixtures_{today_str}.json"
    out_path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Partite effettive in programma OGGI ({today_str}): {len(fixtures)}")


if __name__ == "__main__":
    main()
