"""
settle_results.py — AtmBetSignal
Verifica automatica dei punteggi finali tramite The Odds API.
Risolve le scommesse PENDING in WON / LOST e aggiorna ROI e Win Rate nel tracker.json.
"""

import os
import json
from pathlib import Path
import requests

ODDS_API_KEY = os.environ.get("ODDSAPI_KEY", "").strip()
ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRACKER_PATH = DATA_DIR / "tracker.json"

SPORT_KEYS = [
    "soccer_italy_serie_a", "soccer_epl", "soccer_spain_la_liga",
    "soccer_germany_bundesliga", "soccer_france_ligue_one",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league",
    "soccer_italy_serie_b", "soccer_efl_champ", "soccer_spain_segunda_division",
    "soccer_germany_bundesliga2", "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga", "soccer_belgium_first_div",
    "soccer_turkey_super_league", "soccer_spl"
]

def evaluate_bet(market_type: str, h_score: int, a_score: int) -> bool:
    tot = h_score + a_score
    if market_type == "1":
        return h_score > a_score
    elif market_type == "2":
        return a_score > h_score
    elif market_type == "1X":
        return h_score >= a_score
    elif market_type == "X2":
        return a_score >= h_score
    elif market_type == "Over2.5":
        return tot >= 3
    elif market_type == "Under2.5":
        return tot <= 2
    elif market_type == "GG":
        return h_score > 0 and a_score > 0
    elif market_type == "NG":
        return h_score == 0 or a_score == 0
    return False

def main():
    if not TRACKER_PATH.exists():
        print("Nessun file tracker.json trovato.")
        return

    tracker = json.loads(TRACKER_PATH.read_text(encoding="utf-8"))
    bets = tracker.get("bets", [])
    pending = [b for b in bets if b.get("status") == "PENDING"]

    if not pending:
        print("Nessuna scommessa in attesa da verificare.")
        return

    if not ODDS_API_KEY:
        print("ODDSAPI_KEY mancante nei secrets.")
        return

    completed_scores = {}
    for sport in SPORT_KEYS:
        url = f"{ODDS_BASE_URL}/sports/{sport}/scores/"
        params = {"apiKey": ODDS_API_KEY, "daysFrom": 3}
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                for match in r.json():
                    if match.get("completed") and match.get("scores"):
                        scores_list = match.get("scores", [])
                        h_val = next((int(s["score"]) for s in scores_list if s["name"] == match["home_team"]), None)
                        a_val = next((int(s["score"]) for s in scores_list if s["name"] == match["away_team"]), None)
                        if h_val is not None and a_val is not None:
                            completed_scores[match["id"]] = (h_val, a_val)
        except Exception as e:
            print(f"Errore recupero punteggi per {sport}: {e}")

    updated = 0
    for b in pending:
        fid = b.get("fixture_id")
        if fid in completed_scores:
            h, a = completed_scores[fid]
            b["score"] = f"{h}-{a}"
            won = evaluate_bet(b["market_type"], h, a)
            if won:
                b["status"] = "WON"
                b["profit"] = round(b["odd"] - 1.0, 2)
            else:
                b["status"] = "LOST"
                b["profit"] = -1.0
            updated += 1

    settled = [b for b in bets if b.get("status") in ("WON", "LOST")]
    tot_settled = len(settled)
    won_cnt = len([b for b in settled if b.get("status") == "WON"])
    lost_cnt = len([b for b in settled if b.get("status") == "LOST"])
    tot_profit = sum(b.get("profit", 0.0) for b in settled)

    tracker["total_bets"] = tot_settled
    tracker["won"] = won_cnt
    tracker["lost"] = lost_cnt
    tracker["win_rate"] = round((won_cnt / tot_settled * 100), 1) if tot_settled > 0 else 0.0
    tracker["net_profit_units"] = round(tot_profit, 2)
    tracker["roi_pct"] = round((tot_profit / tot_settled * 100), 1) if tot_settled > 0 else 0.0

    TRACKER_PATH.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Verifica completata: {updated} pronostici risolti oggi. Win Rate: {tracker['win_rate']}% | ROI: {tracker['roi_pct']}%")

if __name__ == "__main__":
    main()
