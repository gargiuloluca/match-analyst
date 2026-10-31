"""
settle_results.py — AtmBetSignal Triple-Engine Auto Settler
Verifica i risultati ufficiali e referta in un colpo solo:
- data/tracker.json (Motore Ufficiale A)
- data/tracker_xg.json (Motore B xG)
- data/tracker_safe.json (Motore C Sniper Safe)
"""

import os
import json
import requests
from pathlib import Path

ODDSAPI_KEY_RAW = os.environ.get("ODDSAPI_KEY", "").strip()
API_KEYS = [k.strip() for k in ODDSAPI_KEY_RAW.split(",") if k.strip()]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TRACKER_FILES = [
    DATA_DIR / "tracker.json",
    DATA_DIR / "tracker_xg.json",
    DATA_DIR / "tracker_safe.json"
]

LEAGUES = [
    "soccer_italy_serie_a", "soccer_spain_la_liga", "soccer_epl",
    "soccer_germany_bundesliga", "soccer_france_ligue_one",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league",
    "soccer_england_championship", "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga", "soccer_belgium_first_div",
    "soccer_england_league1", "soccer_england_efl_cup"
]

def fetch_completed_scores(sport_key: str):
    if not API_KEYS:
        return []
    for key in API_KEYS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores"
        params = {"apiKey": key, "daysFrom": 3}
        try:
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
    return []

def evaluate_bet_outcome(market_key: str, home_score: int, away_score: int) -> bool:
    total_goals = home_score + away_score
    m = market_key.upper()
    if m == "1": return home_score > away_score
    if m == "X": return home_score == away_score
    if m == "2": return away_score > home_score
    if m == "1X": return home_score >= away_score
    if m == "X2": return away_score >= home_score
    if m == "OVER_15": return total_goals > 1.5
    if m == "UNDER_15": return total_goals < 1.5
    if m == "OVER_25": return total_goals > 2.5
    if m == "UNDER_25": return total_goals < 2.5
    if m == "OVER_35": return total_goals > 3.5
    if m == "UNDER_35": return total_goals < 3.5
    if m == "BTTS_YES": return home_score > 0 and away_score > 0
    if m == "BTTS_NO": return home_score == 0 or away_score == 0
    return False

def settle_single_tracker(tracker_file: Path, completed_matches: dict):
    if not tracker_file.exists():
        return
    try:
        data = json.loads(tracker_file.read_text(encoding="utf-8"))
    except Exception:
        return

    bets = data.get("bets", [])
    updated = False

    for b in bets:
        if b.get("status") != "PENDING":
            continue

        match_name = b.get("match", "")
        # Match ricerca per nomi squadre
        match_info = None
        for (h, a), info in completed_matches.items():
            if h.lower() in match_name.lower() and a.lower() in match_name.lower():
                match_info = info
                break

        if match_info and match_info.get("completed"):
            h_score = match_info["home_score"]
            a_score = match_info["away_score"]
            m_key = b.get("market_key", "")
            is_won = evaluate_bet_outcome(m_key, h_score, a_score)

            b["score"] = f"{h_score}-{a_score}"
            odd = float(b.get("odd", 1.0))
            stake = float(b.get("stake_pct", 1.0))

            if is_won:
                b["status"] = "WON"
                b["profit"] = round(stake * (odd - 1.0), 2)
            else:
                b["status"] = "LOST"
                b["profit"] = round(-stake, 2)
            updated = True

    if updated or True:
        concluded = [b for b in bets if b.get("status") in ["WON", "LOST"]]
        won = sum(1 for b in concluded if b["status"] == "WON")
        lost = sum(1 for b in concluded if b["status"] == "LOST")
        net_profit = sum(float(b.get("profit", 0.0)) for b in concluded)
        total_staked = sum(float(b.get("stake_pct", 1.0)) for b in concluded)

        win_rate = round((won / len(concluded)) * 100, 1) if concluded else 0.0
        roi_pct = round((net_profit / total_staked) * 100, 1) if total_staked > 0 else 0.0

        data["total_bets"] = len(concluded)
        data["won"] = won
        data["lost"] = lost
        data["win_rate"] = win_rate
        data["net_profit_units"] = round(net_profit, 2)
        data["roi_pct"] = roi_pct
        data["bets"] = bets

        tracker_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{tracker_file.name}] Refertato: Concluse {len(concluded)} | WR {win_rate}% | ROI {roi_pct}%")

def main():
    print("Scaricamento risultati finali campionati...")
    completed_matches = {}

    for league in LEAGUES:
        scores = fetch_completed_scores(league)
        for s in scores:
            if s.get("completed"):
                scores_list = s.get("scores")
                if scores_list and len(scores_list) >= 2:
                    h_team = s.get("home_team", "")
                    a_team = s.get("away_team", "")
                    h_sc = int(scores_list[0].get("score", 0)) if scores_list[0].get("name") == h_team else int(scores_list[1].get("score", 0))
                    a_sc = int(scores_list[1].get("score", 0)) if scores_list[1].get("name") == a_team else int(scores_list[0].get("score", 0))
                    completed_matches[(h_team, a_team)] = {
                        "completed": True,
                        "home_score": h_sc,
                        "away_score": a_sc
                    }

    print(f"Match conclusi recuperati: {len(completed_matches)}. Refertazione tracker in corso...")
    for tf in TRACKER_FILES:
        settle_single_tracker(tf, completed_matches)

if __name__ == "__main__":
    main()
    
