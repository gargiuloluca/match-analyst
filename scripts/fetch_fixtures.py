"""
fetch_fixtures.py

Scarica le partite di oggi per le leghe principali (Serie A, Premier League,
Liga, Bundesliga, Ligue 1, Champions League), la forma recente di ogni
squadra (dalla classifica) e le quote 1X2.

Fonti dati (entrambe senza carta di credito, solo email per registrarsi):
- football-data.org  → partite, classifica, forma      (piano free: 12 competizioni, 10 richieste/min)
- the-odds-api.com   → quote 1X2                        (piano free: 500 richieste/mese)

Output: data/raw/fixtures_YYYY-MM-DD.json

Nota: il piano free di football-data.org copre 12 competizioni in totale.
Quelle scelte qui sotto sono le 5 leghe domestiche principali + Champions
League. Se vuoi aggiungerne altre supportate dal piano free (es. Eredivisie
"DED", Primeira Liga "PPL", Championship inglese "ELC"), aggiungile alla
lista LEAGUES.
"""

import json
import os
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

# Leghe monitorate: codice football-data.org + sport key the-odds-api.com.
# Tutte incluse nel piano free di entrambi i servizi.
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

# Piccola pausa tra le chiamate a football-data.org per restare sotto il
# limite di 10 richieste/minuto del piano free, ora che monitoriamo più leghe.
FD_CALL_DELAY_SECONDS = 6.5


def fd_get(endpoint: str, params: dict = None) -> dict:
    resp = requests.get(f"{FD_BASE_URL}/{endpoint}", headers=FD_HEADERS, params=params or {}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_todays_fixtures(fd_code: str) -> list:
    data = fd_get(f"competitions/{fd_code}/matches", {"dateFrom": TODAY, "dateTo": TODAY})
    return data.get("matches", [])


def fetch_standings(fd_code: str) -> dict:
    """Classifica attuale: usata come proxy di forma (posizione, punti,
    differenza reti). Più semplice e affidabile, sul piano free, rispetto a
    ricostruire le ultime 5 partite squadra per squadra."""
    data = fd_get(f"competitions/{fd_code}/standings")
    table = {}
    for group in data.get("standings", []):
        if group.get("type") != "TOTAL":
            continue
        for row in group.get("table", []):
            team_id = row["team"]["id"]
            table[team_id] = {
                "position": row["position"],
                "points": row["points"],
                "played": row["playedGames"],
                "goal_diff": row["goalDifference"],
                "form": row.get("form"),  # es. "W,W,D,L,W"
            }
    return table


def fetch_odds(odds_sport_key: str) -> dict:
    """Quote 1X2 per tutte le partite in programma in una lega, indicizzate
    per coppia (squadra_casa, squadra_trasferta)."""
    if not ODDS_API_KEY:
        return {}
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
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
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


def form_to_points(form_string: str, season_goal_diff: int, season_played: int) -> dict:
    """Converte la stringa 'W,W,D,L,W' della classifica in punti sulle ultime
    5 partite. La differenza reti "last5" non è disponibile sul piano free,
    quindi usiamo una stima proporzionale dalla differenza reti stagionale."""
    if not form_string:
        return {"points_last5": 0, "goal_diff_last5": 0, "matches_analyzed": 0}
    results = form_string.split(",")
    points = sum(3 if r == "W" else 1 if r == "D" else 0 for r in results)
    avg_goal_diff_per_game = (season_goal_diff / season_played) if season_played else 0
    estimated_goal_diff_last5 = round(avg_goal_diff_per_game * len(results), 1)
    return {"points_last5": points, "goal_diff_last5": estimated_goal_diff_last5, "matches_analyzed": len(results)}


def match_odds(odds_by_match: dict, home_name: str, away_name: str) -> dict:
    """Le quote usano i nomi ufficiali della squadra, football-data.org usa i
    propri: proviamo un match esatto, poi un match "contiene"."""
    if (home_name, away_name) in odds_by_match:
        return odds_by_match[(home_name, away_name)]
    for (h, a), val in odds_by_match.items():
        if home_name.split()[0].lower() in h.lower() and away_name.split()[0].lower() in a.lower():
            return val
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
        raise SystemExit("FOOTBALLDATA_KEY non impostata: imposta la variabile d'ambiente o il secret su GitHub.")

    all_fixtures = []
    for league in LEAGUES:
        try:
            league_fixtures = fetch_league(league)
            all_fixtures.extend(league_fixtures)
            print(f"{league['name']}: {len(league_fixtures)} partite oggi")
        except requests.HTTPError as e:
            print(f"Attenzione: errore su {league['name']}: {e}")

    out_path = OUTPUT_DIR / f"fixtures_{TODAY}.json"
    out_path.write_text(json.dumps(all_fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Salvate {len(all_fixtures)} partite totali in {out_path}")
    if not ODDS_API_KEY:
        print("Nota: ODDSAPI_KEY non impostata, le quote saranno vuote per tutte le partite.")


if __name__ == "__main__":
    main()
