"""
fetch_fixtures.py

Scarica le partite di oggi per le leghe principali (Serie A, Premier League,
Liga, Bundesliga, Ligue 1, Champions League), la forma recente di ogni
squadra (dalla classifica) e le quote 1X2.

Fonti dati:
- football-data.org  → partite, classifica, forma
- the-odds-api.com   → quote 1X2
"""

import json
import os
import re
import time
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

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


def fd_get(endpoint: str, params: dict = None) -> dict:
    resp = requests.get(f"{FD_BASE_URL}/{endpoint}", headers=FD_HEADERS, params=params or {}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_todays_fixtures(fd_code: str) -> list:
    data = fd_get(f"competitions/{fd_code}/matches", {"dateFrom": TODAY, "dateTo": TODAY})
    return data.get("matches", [])


def fetch_standings(fd_code: str) -> dict:
    data = fd_get(f"competitions/{fd_code}/standings")
    table = {}
    for group in data.get("standings", []):
        if group.get("type") != "TOTAL":
            continue
        for row in group.get("table", []):
            team_id = row["team"]["id"]
            table[team_id] = {
                "position": row.get("position"),
                "points": row.get("points"),
                "played": row.get("playedGames"),
                "goal_diff": row.get("goalDifference"),
                "form": row.get("form"),
            }
    return table


def fetch_odds(odds_sport_key: str) -> dict:
    if not ODDS_API_KEY:
        print(f"[{odds_sport_key}] AVVISO: ODDSAPI_KEY non trovata nei secrets!")
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
            print(f"[{odds_sport_key}] Errore quote HTTP {resp.status_code}: {resp.text}")
            return {}
        events = resp.json()
        odds_by_match = {}
        for ev in events:
            home, away = ev.get("home_team"), ev.get("away_team")
            if not ev.get("bookmakers"):
                continue
            market = ev["bookmakers"][0].get("markets", [{}])[0]
            outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            odds_by_match[(home, away)] = {
                "home": outcomes.get(home),
                "draw": outcomes.get("Draw"),
                "away": outcomes.get(away),
                "bookmaker": ev["bookmakers"][0].get("title"),
            }
        return odds_by_match
    except Exception as e:
        print(f"Errore chiamata The Odds API per {odds_sport_key}: {e}")
        return {}


def form_to_points(form_string: str, season_goal_diff: int, season_played: int) -> dict:
    if not form_string:
        return {"points_last5": 5, "goal_diff_last5": 0, "matches_analyzed": 5}
    results = form_string.split(",")
    points = sum(3 if r == "W" else 1 if r == "D" else 0 for r in results)
    avg_goal_diff_per_game = (season_goal_diff / season_played) if season_played else 0
    estimated_goal_diff_last5 = round(avg_goal_diff_per_game * len(results), 1)
    return {"points_last5": points, "goal_diff_last5": estimated_goal_diff_last5, "matches_analyzed": len(results)}


def clean_team_name(name: str) -> str:
    """Rimuove prefissi e suffissi societari per facilitare l'abbinamento."""
    name = re.sub(r'\b(FC|AC|AS|CF|AFC|BSC|SSC|US|SS|1\.|Hellas|Calcio)\b', '', name, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', name).strip().lower()


def match_odds(odds_by_match: dict, home_name: str, away_name: str) -> dict:
    # 1. Tentativo di match esatto
    if (home_name, away_name) in odds_by_match:
        return odds_by_match[(home_name, away_name)]

    norm_h = clean_team_name(home_name)
    norm_a = clean_team_name(away_name)

    # 2. Match flessibile sui nomi puliti
    for (h, a), odds in odds_by_match.items():
        clean_h = clean_team_name(h)
        clean_a = clean_team_name(a)
        if (norm_h in clean_h or clean_h in norm_h) and (norm_a in clean_a or clean_a in norm_a):
            return odds

    # 3. Match sulla prima parola identificativa lunga (>3 caratteri)
    words_h = [w for w in norm_h.split() if len(w) > 3]
    words_a = [w for w in norm_a.split() if len(w) > 3]
    if words_h and words_a:
        for (h, a), odds in odds_by_match.items():
            if words_h[0] in h.lower() and words_a[0] in a.lower():
                return odds

    return {}


def fetch_league(league: dict) -> list:
    fixtures = fetch_todays_fixtures(league["fd_code"])
    time.sleep(FD_CALL_DELAY_SECONDS)
    if not fixtures:
        return []

    standings = fetch_standings(league["fd_code"])
    time.sleep(FD_CALL_DELAY_SECONDS)

    odds_by_match = fetch_odds(league["odds_key"])

    results = []
    for fx in fixtures:
        home = fx["homeTeam"]
        away = fx["awayTeam"]
        home_row = standings.get(home["id"], {})
        away_row = standings.get(away["id"], {})
        home_form = form_to_points(home_row.get("form"), home_row.get("goal_diff", 0), home_row.get("played", 0))
        away_form = form_to_points(away_row.get("form"), away_row.get("goal_diff", 0), away_row.get("played", 0))
        odds = match_odds(odds_by_match, home["name"], away["name"])

        results.append(
            {
                "fixture_id": fx["id"],
                "league": league["name"],
                "date": fx["utcDate"],
                "home_team": {"id": home["id"], "name": home["name"], "form": home_form},
                "away_team": {"id": away["id"], "name": away["name"], "form": away_form},
                "odds": odds,
            }
        )
    return results


def main():
    if not FD_API_KEY:
        raise SystemExit("FOOTBALLDATA_KEY non impostata: configurala nei secret su GitHub.")

    all_fixtures = []
    for league in LEAGUES:
        try:
            league_fixtures = fetch_league(league)
            all_fixtures.extend(league_fixtures)
            print(f"{league['name']}: {len(league_fixtures)} partite oggi")
        except requests.HTTPError as e:
            print(f"Errore su {league['name']}: {e}")

    out_path = OUTPUT_DIR / f"fixtures_{TODAY}.json"
    out_path.write_text(json.dumps(all_fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Salvate {len(all_fixtures)} partite totali in {out_path}")

    odds_found = sum(1 for f in all_fixtures if f.get("odds"))
    print(f"Quote collegate con successo: {odds_found}/{len(all_fixtures)}")


if __name__ == "__main__":
    main()
