"""
settle_results.py — AtmBetSignal Automated Settlement Engine
Verifica i risultati finali su The Odds API e aggiorna tracker.json.
Supporta: 1X2, DC, DNB (con rimborso in parità), Totali gol e BTTS.
Invia un resoconto sintetico su Telegram a fine giornata.
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

API_KEY = os.environ.get("ODDSAPI_KEY", "").strip()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRACKER_FILE = DATA_DIR / "tracker.json"

LEAGUES = [
    "soccer_italy_serie_a", "soccer_spain_la_liga", "soccer_epl",
    "soccer_germany_bundesliga", "soccer_france_ligue_one",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league",
    "soccer_england_championship", "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga", "soccer_belgium_first_div",
    "soccer_england_league1", "soccer_england_efl_cup"
]

def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Errore Telegram settlement: {e}")

def fetch_scores_for_league(sport_key: str):
    if not API_KEY:
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores"
    params = {"apiKey": API_KEY, "daysFrom": 3}
    try:
        res = requests.get(url, params=params, timeout=20)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Errore fetch scores {sport_key}: {e}")
    return []

def evaluate_bet_status(market_key: str, h_score: int, a_score: int, odd: float, stake: float):
    tot_goals = h_score + a_score
    status = "LOST"
    profit = -round(stake, 2)

    # 1X2
    if market_key == "1":
        if h_score > a_score:
            status = "WON"
            profit = round(stake * (odd - 1.0), 2)
    elif market_key == "X":
        if h_score == a_score:
            status = "WON"
            profit = round(stake * (odd - 1.0), 2)
    elif market_key == "2":
        if a_score > h_score:
            status = "WON"
            profit = round(stake * (odd - 1.0), 2)
    # Doppia Chance
    elif market_key == "1X":
        if h_score >= a_score:
            status = "WON"
            profit = round(stake * (odd - 1.0), 2)
    elif market_key == "X2":
        if a_score >= h_score:
            status = "WON"
            profit = round(stake * (odd - 1.0), 2)
    # Draw No Bet (Rimborso in caso di parità)
    elif market_key == "DNB_1":
        if h_score > a_score:
            status = "WON"
            profit = round(stake * (odd - 1.0), 2)
        elif h_score == a_score:
            status = "REFUND"
            profit = 0.0
    elif market_key == "DNB_2":
        if a_score > h_score:
            status = "WON"
            profit = round(stake * (odd - 1.0), 2)
        elif h_score == a_score:
            status = "REFUND"
            profit = 0.0
    # Totali Gol
    elif market_key == "OVER_15":
        if tot_goals > 1.5: status = "WON"; profit = round(stake * (odd - 1.0), 2)
    elif market_key == "UNDER_15":
        if tot_goals < 1.5: status = "WON"; profit = round(stake * (odd - 1.0), 2)
    elif market_key == "OVER_25":
        if tot_goals > 2.5: status = "WON"; profit = round(stake * (odd - 1.0), 2)
    elif market_key == "UNDER_25":
        if tot_goals < 2.5: status = "WON"; profit = round(stake * (odd - 1.0), 2)
    elif market_key == "OVER_35":
        if tot_goals > 3.5: status = "WON"; profit = round(stake * (odd - 1.0), 2)
    elif market_key == "UNDER_35":
        if tot_goals < 3.5: status = "WON"; profit = round(stake * (odd - 1.0), 2)
    # BTTS
    elif market_key == "BTTS_YES":
        if h_score > 0 and a_score > 0: status = "WON"; profit = round(stake * (odd - 1.0), 2)
    elif market_key == "BTTS_NO":
        if h_score == 0 or a_score == 0: status = "WON"; profit = round(stake * (odd - 1.0), 2)

    return status, profit

def main():
    if not TRACKER_FILE.exists():
        print("tracker.json non trovato.")
        return

    tracker_data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
    bets = tracker_data.get("bets", [])
    pending_bets = [b for b in bets if b.get("status") == "PENDING"]

    if not pending_bets:
        print("Nessuna scommessa PENDING da refertare.")
        return

    # Mappa risultati conclusi
    scores_by_match = {}
    for league in LEAGUES:
        events = fetch_scores_for_league(league)
        for ev in events:
            if ev.get("completed"):
                h_name = ev.get("home_team")
                a_name = ev.get("away_team")
                scores = ev.get("scores")
                if scores and len(scores) >= 2:
                    h_score = next((int(s["score"]) for s in scores if s["name"] == h_name), None)
                    a_score = next((int(s["score"]) for s in scores if s["name"] == a_name), None)
                    if h_score is not None and a_score is not None:
                        key = f"{h_name}_{a_name}".lower()
                        scores_by_match[key] = (h_score, a_score)

    settled_count = 0
    won_count = 0
    refund_count = 0
    daily_pnl = 0.0

    for b in pending_bets:
        match_str = b.get("match", "")
        parts = match_str.split(" vs ")
        if len(parts) != 2:
            continue
        h_team, a_team = parts[0].strip(), parts[1].strip()
        match_key = f"{h_team}_{a_team}".lower()

        if match_key in scores_by_match:
            h_score, a_score = scores_by_match[match_key]
            m_key = b.get("market_key", b.get("id", "").split("_")[-1])
            odd = float(b.get("odd", 1.0))
            stake = float(b.get("stake_pct", 1.0))

            status, profit = evaluate_bet_status(m_key, h_score, a_score, odd, stake)

            b["status"] = status
            b["profit"] = profit
            b["score"] = f"{h_score}-{a_score}"
            settled_count += 1
            daily_pnl += profit
            if status == "WON": won_count += 1
            elif status == "REFUND": refund_count += 1

    if settled_count > 0:
        TRACKER_FILE.write_text(json.dumps(tracker_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # Report Telegram notturno
        msg = [
            "<b>🌙 AtmBetSignal — Chiusura Palinsesto & Settlement</b>",
            f"Operazioni refertate: <b>{settled_count}</b>",
            f"✅ Vinte: <b>{won_count}</b> | 🔄 Rimborsate: <b>{refund_count}</b> | ❌ Perse: <b>{settled_count - won_count - refund_count}</b>",
            f"P&L di Giornata: <b>{daily_pnl:+.2f}% Bankroll</b>\n",
            "📊 Track-record aggiornato e verificabile sul portale web."
        ]
        send_telegram("\n".join(msg))
        print(f"Refertazione completata: {settled_count} scommesse aggiornate.")
    else:
        print("I match PENDING non risultano ancora conclusi sui feed.")

if __name__ == "__main__":
    main()
