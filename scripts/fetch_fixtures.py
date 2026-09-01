"""
fetch_fixtures.py

Scarica le partite di calcio in programma oggi (Serie A), la forma recente
di ogni squadra (ultime 5 partite dalla classifica) e le quote 1X2.

Fonti dati (entrambe senza carta di credito, solo email per registrarsi):
- football-data.org  → partite, classifica, forma      (piano free: 10 richieste/min)
- the-odds-api.com   → quote 1X2                        (piano free: 500 richieste/mese)

Output: data/raw/fixtures_YYYY-MM-DD.json

Nota: il piano free di football-data.org copre 12 competizioni tra cui la
Serie A (codice "SA") ma i dati di partite/classifica possono avere un
piccolo ritardo rispetto al tempo reale: per uno screening del giorno prima
o del mattino stesso non è un problema.
"""

import json
import os
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

# Codice competizione football-data.org. SA = Serie A. Estendi se ti serve
# anche la Serie B (nota: la Serie B non è sempre presente nel piano free).
COMPETITION_CODE = "SA"

# Sport key richiesto da the-odds-api.com per il calcio italiano
ODDS_SPORT_KEY = "soccer_italy_serie_a"

TODAY = date.today().isoformat()

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fd_get(endpoint: str, params: dict = None) -> dict:
    resp = requests.get(f"{FD_BASE_URL}/{endpoint}", headers=FD_HEADERS, params=params or {}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_todays_fixtures() -> list:
    data = fd_get(f"competitions/{COMPETITION_CODE}/matches", {"dateFrom": TODAY, "dateTo": TODAY})
    return data.get("matches", [])


def fetch_standings() -> dict:
    """Classifica attuale: usata come proxy di forma (posizione, punti,
    differenza reti). Più semplice e affidabile, sul piano free, rispetto a
    ricostruire le ultime 5 partite squadra per squadra."""
    data = fd_get(f"competitions/{COMPETITION_CODE}/standings")
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


def fetch_odds() -> dict:
    """Quote 1X2 per tutte le partite di Serie A in programma, indicizzate
    per coppia (squadra_casa, squadra_trasferta) in minuscolo per il match."""
    if not ODDS_API_KEY:
        return {}
    resp = requests.get(
        f"{ODDS_BASE_URL}/sports/{ODDS_SPORT_KEY}/odds",
        params={
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
        },
        timeout=20,
    )
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


def main():
    if not FD_API_KEY:
        raise SystemExit("FOOTBALLDATA_KEY non impostata: imposta la variabile d'ambiente o il secret su GitHub.")

    fixtures = fetch_todays_fixtures()
    standings = fetch_standings()
    odds_by_match = fetch_odds()

    all_fixtures = []
    for fx in fixtures:
        home = fx["homeTeam"]
        away = fx["awayTeam"]
        home_row = standings.get(home["id"], {})
        away_row = standings.get(away["id"], {})
        home_form = form_to_points(home_row.get("form"), home_row.get("goal_diff", 0), home_row.get("played", 0))
        away_form = form_to_points(away_row.get("form"), away_row.get("goal_diff", 0), away_row.get("played", 0))
        odds = match_odds(odds_by_match, home["name"], away["name"])

        all_fixtures.append(
            {
                "fixture_id": fx["id"],
                "date": fx["utcDate"],
                "home_team": {"id": home["id"], "name": home["name"], "form": home_form},
                "away_team": {"id": away["id"], "name": away["name"], "form": away_form},
                "odds": odds,
            }
        )

    out_path = OUTPUT_DIR / f"fixtures_{TODAY}.json"
    out_path.write_text(json.dumps(all_fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Salvate {len(all_fixtures)} partite in {out_path}")
    if not ODDS_API_KEY:
        print("Nota: ODDSAPI_KEY non impostata, le quote saranno vuote per tutte le partite.")


if __name__ == "__main__":
    main()
