"""
settle_results.py — Verifica automatica degli esiti e calcolo metriche ROI.
Valuta 1, 2, 1X, X2, Over 2.5, Under 2.5, GG e NG.
"""

import json
import os
from pathlib import Path
import requests

ODDS_API_KEY = os.environ.get("ODDSAPI_KEY", "")
ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRACKER_PATH = DATA_DIR / "tracker.json"


def evaluate_outcome(market_type: str, home_goals: int, away_goals: int) -> bool:
    """Valuta la condizione di vincita in base al mercato."""
    total_goals = home_goals + away_goals

    if market_type == "1":
        return home_goals > away_goals
    elif market_type == "2":
        return away_goals > home_goals
    elif market_type == "1X":
        return home_goals >= away_goals
    elif market_type == "X2":
        return away_goals >= home_goals
    elif market_type == "Over2.5":
        return total_goals >= 3
    elif market_type == "Under2.5":
        return total_goals <= 2
    elif market_type == "GG":
        return home_goals > 0 and away_goals > 0
    elif market_type == "NG":
        return home_goals == 0 or away_goals == 0
    return False


def settle_bets():
    if not TRACKER_PATH.exists():
        print("Nessun tracker trovato.")
        return

    tracker = json.loads(TRACKER_PATH.read_text(encoding="utf-8"))
    bets = tracker.get("bets", [])
    pending_bets = [b for b in bets if b.get("status") == "PENDING"]

    if not pending_bets:
        print("Nessuna scommessa in attesa di verifica.")
        return

    # Recupera i risultati completati tramite The Odds API (scores endpoint)
    # The Odds API supporta i punteggi passati: /sports/{sport}/scores/?daysFrom=3
    resolved_count = 0

    for b in pending_bets:
        # Nota: In assenza di chiamata API immediata sui punteggi storici,
        # lo script può verificare la presenza del risultato se valorizzato manualmente o via API
        fixture_id = b.get("fixture_id")
        # Se disponibile il punteggio da endpoint score:
        # home_score, away_score = fetch_score_for_fixture(fixture_id)
        # Esempio di risoluzione automatica se lo score è presente:
        if b.get("score") and "-" in str(b.get("score")):
            parts = str(b["score"]).split("-")
            h, a = int(parts[0].strip()), int(parts[1].strip())
            won = evaluate_outcome(b["market_type"], h, a)
            b["status"] = "WON" if won else "LOST"
            b["profit"] = round((b["odd"] - 1.0), 2) if won else -1.0
            resolved_count += 1

    # Ricalcolo metriche globali su scommesse chiuse
    settled = [b for b in bets if b.get("status") in ("WON", "LOST")]
    total_settled = len(settled)
    won_bets = len([b for b in settled if b.get("status") == "WON"])
    lost_bets = len([b for b in settled if b.get("status") == "LOST"])
    net_profit = sum(b.get("profit", 0.0) for b in settled)

    tracker["total_bets"] = total_settled
    tracker["won"] = won_bets
    tracker["lost"] = lost_bets
    tracker["win_rate"] = round((won_bets / total_settled * 100), 1) if total_settled > 0 else 0.0
    tracker["net_profit_units"] = round(net_profit, 2)
    tracker["roi_pct"] = round((net_profit / total_settled * 100), 1) if total_settled > 0 else 0.0

    TRACKER_PATH.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Risolte {resolved_count} scommesse. Win-rate attuale: {tracker['win_rate']}% | ROI: {tracker['roi_pct']}%")


if __name__ == "__main__":
    settle_bets()
