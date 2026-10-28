"""
settle_results.py — AtmBetSignal Automated Settlement & Telegram Notifier (Multi-Key & Fuzzy Matching)
Controlla i risultati delle partite in PENDING tramite The Odds API con rotazione chiavi.
Assegna WON, LOST, REFUND (DNB), calcola l'Equity Line e invia il report Telegram.
Include matching flessibile (ignora FC, AC, AS per evitare mancate refertazioni).
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

API_KEYS_RAW = os.environ.get("ODDSAPI_KEY", "").strip()
API_KEYS = [k.strip() for k in API_KEYS_RAW.split(",") if k.strip()]

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRACKER_FILE = DATA_DIR / "tracker.json"

LEAGUES = [
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_england_championship",
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_belgium_first_div",
    "soccer_england_league1",
    "soccer_england_efl_cup"
]

def send_telegram_msg(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("Credenziali Telegram non trovate. Messaggio saltato.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Errore invio report Telegram: {e}")

def fetch_completed_scores_with_fallback(sport_key: str):
    if not API_KEYS:
        return []
    
    for idx, key in enumerate(API_KEYS):
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores"
        params = {"apiKey": key, "daysFrom": 3}
        try:
            res = requests.get(url, params=params, timeout=20)
            if res.status_code == 200:
                return res.json()
            elif res.status_code in [401, 429]:
                print(f"Avviso scores: Chiave #{idx+1} esaurita/non valida. Provo successiva...")
            elif res.status_code == 404:
                return []
        except Exception:
            continue

    return []

def evaluate_bet_outcome(market_key: str, home_score: int, away_score: int, odd: float, stake_pct: float):
    tot_goals = home_score + away_score
    status = "LOST"
    profit = -stake_pct

    # Mercati 1X2
    if market_key == "1":
        if home_score > away_score:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "X":
        if home_score == away_score:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "2":
        if away_score > home_score:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)

    # Doppie Chance
    elif market_key == "1X":
        if home_score >= away_score:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "X2":
        if away_score >= home_score:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)

    # Draw No Bet (Rimborso Parità)
    elif market_key == "DNB_1":
        if home_score > away_score:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
        elif home_score == away_score:
            status = "REFUND"
            profit = 0.0
    elif market_key == "DNB_2":
        if away_score > home_score:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
        elif home_score == away_score:
            status = "REFUND"
            profit = 0.0

    # Linee Gol Totali
    elif market_key == "OVER_15":
        if tot_goals > 1.5:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "UNDER_15":
        if tot_goals < 1.5:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "OVER_25":
        if tot_goals > 2.5:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "UNDER_25":
        if tot_goals < 2.5:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "OVER_35":
        if tot_goals > 3.5:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "UNDER_35":
        if tot_goals < 3.5:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)

    # Goal / NoGoal
    elif market_key == "BTTS_YES":
        if home_score > 0 and away_score > 0:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)
    elif market_key == "BTTS_NO":
        if home_score == 0 or away_score == 0:
            status = "WON"
            profit = round(stake_pct * (odd - 1.0), 2)

    return status, profit

def clean_team_name(name: str) -> str:
    n = name.lower()
    for drop in [" fc", " ac", " as", "cf", "ssc ", "afc "]:
        n = n.replace(drop, "")
    return n.strip()

def main():
    if not TRACKER_FILE.exists():
        print("tracker.json non trovato.")
        return

    try:
        tracker_data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Errore lettura tracker.json: {e}")
        return

    bets = tracker_data.get("bets", [])
    pending_bets = [b for b in bets if b.get("status") == "PENDING"]

    if not pending_bets:
        print("Nessuna giocata in attesa di refertazione.")
        return

    # Mappa i punteggi completati
    completed_matches = {}
    print(f"Controllo esiti su {len(LEAGUES)} campionati...")
    for league in LEAGUES:
        scores_data = fetch_completed_scores_with_fallback(league)
        for match in scores_data:
            if match.get("completed") and match.get("scores"):
                h_name = match.get("home_team", "").lower()
                a_name = match.get("away_team", "").lower()
                
                h_score, a_score = None, None
                for s in match["scores"]:
                    if s.get("name", "").lower() == h_name:
                        h_score = int(s.get("score", 0))
                    elif s.get("name", "").lower() == a_name:
                        a_score = int(s.get("score", 0))

                if h_score is not None and a_score is not None:
                    completed_matches[f"{h_name} vs {a_name}"] = (h_score, a_score)

    settled_now = []

    for b in bets:
        if b.get("status") == "PENDING":
            m_str = b.get("match", "").lower()
            clean_m = clean_team_name(m_str)
            
            matched_score = None
            for key, score in completed_matches.items():
                clean_k = clean_team_name(key)
                k_teams = [t.strip() for t in clean_k.split(" vs ") if t.strip()]
                
                if len(k_teams) == 2:
                    if k_teams[0] in clean_m and k_teams[1] in clean_m:
                        matched_score = score
                        break
                    
                    m_teams = [t.strip() for t in clean_m.split(" vs ") if t.strip()]
                    if len(m_teams) == 2 and m_teams[0] in k_teams[0] and m_teams[1] in k_teams[1]:
                        matched_score = score
                        break

            if matched_score:
                h_s, a_s = matched_score
                odd = float(b.get("odd", 1.50))
                stake_pct = float(b.get("stake_pct", 2.5))
                m_key = b.get("market_key", "")

                status, profit = evaluate_bet_outcome(m_key, h_s, a_s, odd, stake_pct)
                b["status"] = status
                b["score"] = f"{h_s}-{a_s}"
                b["profit"] = profit
                settled_now.append(b)

    if settled_now:
        settled_all = [b for b in bets if b.get("status") in ["WON", "LOST", "REFUND"]]
        total_closed = len(settled_all)
        won_cnt = sum(1 for b in settled_all if b.get("status") == "WON")
        lost_cnt = sum(1 for b in settled_all if b.get("status") == "LOST")
        refund_cnt = sum(1 for b in settled_all if b.get("status") == "REFUND")
        
        tot_profit = sum(float(b.get("profit", 0.0)) for b in settled_all)
        tot_staked = sum(float(b.get("stake_pct", 2.5)) for b in settled_all)

        win_rate = round((won_cnt / (won_cnt + lost_cnt) * 100), 1) if (won_cnt + lost_cnt) > 0 else 0.0
        roi_pct = round((tot_profit / tot_staked * 100), 1) if tot_staked > 0 else 0.0

        tracker_data["total_bets"] = total_closed
        tracker_data["won"] = won_cnt
        tracker_data["lost"] = lost_cnt
        tracker_data["void"] = refund_cnt
        tracker_data["win_rate"] = win_rate
        tracker_data["net_profit_units"] = round(tot_profit, 2)
        tracker_data["roi_pct"] = roi_pct

        TRACKER_FILE.write_text(json.dumps(tracker_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Refertate {len(settled_now)} scommesse con successo.")

        lines = []
        lines.append("📋 <b>AtmBetSignal — Resoconto Esiti Ufficiali</b>")
        lines.append(f"<i>Verifica risultati e aggiornamento Equity Line</i>\n")

        for s in settled_now:
            badge = "✅ VINTO" if s["status"] == "WON" else ("❌ PERSO" if s["status"] == "LOST" else "🔄 RIMBORSATO")
            p_val = f"+{s['profit']:.2f}%" if s['profit'] > 0 else f"{s['profit']:.2f}%"
            lines.append(f"⚽ <b>{s['match']}</b> (Fin: {s.get('score', '-')})")
            lines.append(f"   ↳ {s['bet']} @ {s['odd']:.2f} — {badge} (<b>{p_val}</b>)\n")

        lines.append("─────────────────────")
        lines.append(f"📊 <b>Bilancio Complessivo Certificato:</b>")
        lines.append(f"• Win Rate: <b>{win_rate}%</b> ({won_cnt}V - {lost_cnt}P - {refund_cnt}R)")
        lines.append(f"• Rendimento Netto Bankroll: <b>{'+' if tot_profit >= 0 else ''}{tot_profit:.2f}%</b>")
        lines.append(f"• ROI Globale: <b>{'+' if roi_pct >= 0 else ''}{roi_pct}%</b>")

        send_telegram_msg("\n".join(lines))
    else:
        print("Nessun match PENDING terminato al momento del controllo.")

if __name__ == "__main__":
    main()
