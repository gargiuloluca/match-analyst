"""
fetch_fixtures.py
Scarica le partite e le relative quote 1X2 per le principali leghe europee.
"""

import json
import os
import re
import time
from datetime import date
from pathlib import Path
import requests

FD_API_KEY = os.environ.get("FOOTBALLDATA_KEY", "")
FD_BASE_URL = "https://api.football-data.org/v4"
FD_HEADERS = {"X-Auth-Token": FD_API_KEY}

ODDS_API_KEY = os.environ.get("ODDSAPI_KEY", "")
ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

LEAGUES = [
    {"name": "Serie A", "fd_code": "SA", "odds_key": "soccer_italy_serie_a"},
    {"name": "Premier League", "fd_code": "PL", "odds_key": "soccer_epl"},
    {"name": "La Liga", "fd_code": "PD", "odds_key": "soccer_spain_la_liga"},
    {"name": "Bundesliga", "fd_code": "BL1", "odds_key": "soccer_germany_bundesliga"},
    {"name": "Ligue 1", "fd_code": "FL1", "odds_key": "soccer_france_ligue_one"},
    {"name": "Champions League", "fd_code": "CL", "odds_key": "soccer_uefa_champs_league"},
]

TODAY = date.today().isoformat()
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FD_CALL_DELAY_SECONDS = 6.5


def fetch_odds(odds_sport_key: str) -> dict:
    if not ODDS_API_KEY:
        print(f"[{odds_sport_key}] ODDSAPI_KEY assente.")
        return {}
    try:
        resp = requests.get(
            f"{ODDS_BASE_URL}/sports/{odds_sport_key}/odds",
            params={
                "apiKey": ODDS_API_KEY,
                "regions": "eu",
                "markets": "h2h",
                "oddsFormat": "decimal",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"[{odds_sport_key}] Errore The Odds API: {resp.status_code}")
            return {}
        events = resp.json()
        odds_by_match = {}
        for ev in events:
            home, away = ev.get("home_team"), ev.get("away_team")
            if not ev.get("bookmakers"):
                continue
            market = ev["bookmakers"][0].get("markets", [{}])[0]
            outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            h_price = outcomes.get(home)
            d_price = outcomes.get("Draw")
            a_price = outcomes.get(away)
            if h_price and d_price and a_price:
                odds_by_match[(home, away)] = {
                    "home": float(h_price),
                    "draw": float(d_price),
                    "away": float(a_price),
                    "bookmaker": ev["bookmakers"][0].get("title"),
                    "raw_home": home,
                    "raw_away": away,
                }
        return odds_by_match
    except Exception as e:
        print(f"Errore chiamata quote: {e}")
        return {}


def clean_name(name: str) -> str:
    name = re.sub(r"\b(FC|AC|AS|CF|AFC|BSC|SSC|US|SS|1\.|Hellas|Calcio|Real|Club)\b", "", name, flags=re.IGNORECASE)
    return "".join(c for c in name.lower() if c.isalnum())


def match_odds(odds_by_match: dict, home_name: str, away_name: str) -> dict:
    if (home_name, away_name) in odds_by_match:
        return odds_by_match[(home_name, away_name)]

    nh = clean_name(home_name)
    na = clean_name(away_name)

    for (h, a), odds in odds_by_match.items():
        ch = clean_name(h)
        ca = clean_name(a)
        if (nh in ch or ch in nh) and (na in ca or ca in na):
            return odds

    # Confronto parziale sulle radici delle parole
    words_h = [clean_name(w) for w in home_name.split() if len(w) > 3]
    words_a = [clean_name(w) for w in away_name.split() if len(w) > 3]
    if words_h and words_a:
        for (h, a), odds in odds_by_match.items():
            if any(w in clean_name(h) for w in words_h) and any(w in clean_name(a) for w in words_a):
                return odds

    return {}


def fetch_todays_fixtures(fd_code: str) -> list:
    try:
        resp = requests.get(f"{FD_BASE_URL}/competitions/{fd_code}/matches", headers=FD_HEADERS, params={"dateFrom": TODAY, "dateTo": TODAY}, timeout=20)
        if resp.status_code == 200:
            return resp.json().get("matches", [])
    except Exception:
        pass
    return []


def fetch_standings(fd_code: str) -> dict:
    try:
        resp = requests.get(f"{FD_BASE_URL}/competitions/{fd_code}/standings", headers=FD_HEADERS, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            table = {}
            for group in data.get("standings", []):
                if group.get("type") != "TOTAL":
                    continue
                for row in group.get("table", []):
                    table[row["team"]["id"]] = {
                        "points": row.get("points", 0),
                        "goal_diff": row.get("goalDifference", 0),
                        "played": row.get("playedGames", 1),
                        "form": row.get("form"),
                    }
            return table
    except Exception:
        pass
    return {}


def form_to_points(form_string: str, season_goal_diff: int, season_played: int) -> dict:
    if not form_string:
        return {"points_last5": 5, "goal_diff_last5": 0, "matches_analyzed": 5}
    results = form_string.split(",")
    points = sum(3 if r == "W" else 1 if r == "D" else 0 for r in results)
    avg_gd = (season_goal_diff / season_played) if season_played else 0
    return {"points_last5": points, "goal_diff_last5": round(avg_gd * len(results), 1), "matches_analyzed": len(results)}


def fetch_league(league: dict) -> list:
    odds_by_match = fetch_odds(league["odds_key"])
    fixtures = fetch_todays_fixtures(league["fd_code"])
    time.sleep(FD_CALL_DELAY_SECONDS)
    standings = fetch_standings(league["fd_code"])
    time.sleep(FD_CALL_DELAY_SECONDS)

    results = []
    matched_odds_keys = set()

    # 1. Popola da Football-Data e unisci le quote
    for fx in fixtures:
        home = fx["homeTeam"]
        away = fx["awayTeam"]
        odds = match_odds(odds_by_match, home["name"], away["name"])

        if odds:
            matched_odds_keys.add((odds.get("raw_home"), odds.get("raw_away")))

        home_row = standings.get(home["id"], {})
        away_row = standings.get(away["id"], {})

        results.append({
            "fixture_id": fx["id"],
            "league": league["name"],
            "date": fx["utcDate"],
            "home_team": {"id": home["id"], "name": home["name"], "form": form_to_points(home_row.get("form"), home_row.get("goal_diff", 0), home_row.get("played", 0))},
            "away_team": {"id": away["id"], "name": away["name"], "form": form_to_points(away_row.get("form"), away_row.get("goal_diff", 0), away_row.get("played", 0))},
            "odds": odds,
        })

    # 2. Fallback: se una partita ha quote ma non è stata associata, aggiungila direttamente dalle quote
    for (raw_h, raw_a), odds_data in odds_by_match.items():
        if (raw_h, raw_a) not in matched_odds_keys:
            results.append({
                "fixture_id": f"{clean_name(raw_h)}_{clean_name(raw_a)}",
                "league": league["name"],
                "date": TODAY,
                "home_team": {"id": 0, "name": raw_h, "form": {"points_last5": 5, "goal_diff_last5": 0, "matches_analyzed": 5}},
                "away_team": {"id": 0, "name": raw_a, "form": {"points_last5": 5, "goal_diff_last5": 0, "matches_analyzed": 5}},
                "odds": odds_data,
            })

    return results


def main():
    all_fixtures = []
    for league in LEAGUES:
        try:
            lf = fetch_league(league)
            all_fixtures.extend(lf)
            print(f"{league['name']}: {len(lf)} partite caricate")
        except Exception as e:
            print(f"Errore su {league['name']}: {e}")

    out_path = OUTPUT_DIR / f"fixtures_{TODAY}.json"
    out_path.write_text(json.dumps(all_fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    
    odds_count = sum(1 for f in all_fixtures if f.get("odds"))
    print(f"Salvate {len(all_fixtures)} partite totali in {out_path}")
    print(f"Quote valide agganciate: {odds_count}/{len(all_fixtures)}")


if __name__ == "__main__":
    main()
