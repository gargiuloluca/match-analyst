"""
send_telegram.py — Report Istituzionale Master Top 5 AtmBetSignal
Invia su Telegram esclusivamente le Top 5 opportunità assolute filtrate dall'AI Master Selector.
"""

import os
import json
import requests
from pathlib import Path

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LATEST_MASTER_FILE = DATA_DIR / "latest_master.json"

def send_message(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("Credenziali Telegram non configurate. Invio saltato.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload, timeout=15)
    if r.status_code == 200:
        print("Messaggio Telegram inviato con successo.")
    else:
        print(f"Errore invio Telegram: {r.status_code} — {r.text}")

def main():
    if not LATEST_MASTER_FILE.exists():
        print("latest_master.json non trovato.")
        return

    data = json.loads(LATEST_MASTER_FILE.read_text(encoding="utf-8"))
    selections = data.get("selections", [])

    lines = []
    lines.append("<b>🏧 AtmBetSignal — Master AI Intelligence Report</b>")
    lines.append("<i>Selezione Istituzionale di Élite (Top 5 Giornaliere)</i>\n")

    if not selections:
        lines.append("🛡️ <b>Capitale Protetto:</b> Nessuna opportunità odierna ha superato i rigorosi filtri di qualità del Master Selector. Zero scommesse forzate per preservare il bankroll.")
    else:
        lines.append(f"🎯 <b>LE TOP {len(selections)} OCCASIONI ASSOLUTE DELLA GIORNATA</b>\n")
        
        for i, p in enumerate(selections, 1):
            # Gestione flessibile dei campi tra i vari motori
            home = p.get("home_team", "")
            away = p.get("away_team", "")
            match_name = p.get("match", f"{home} - {away}" if home and away else "Match")
            league = p.get("league_name", p.get("league", "Campionato Internazionale"))
            
            outcome = p.get("outcome_label", p.get("market", "Esito Consigliato"))
            
            # Estrazione quota (supporta 'odds' come dizionario o float, 'odd', 'price')
            raw_odds = p.get("odds", p.get("odd", p.get("price", 1.80)))
            if isinstance(raw_odds, dict):
                # Se è un dizionario, prendiamo la quota principale dell'esito o default
                odd_val = float(raw_odds.get("1", raw_odds.get("OVER_25", 1.80)))
            else:
                odd_val = float(raw_odds)

            score = p.get("master_score", 0.0)
            stake = p.get("fund_stake_units", p.get("suggested_stake_pct", 1.0))

            badge = f"🔥 <b>RANK #{i} (AI Score: {score}/100)</b>"

            lines.append(f"{badge}")
            lines.append(f"⚽ <b>{match_name}</b>")
            lines.append(f"🏆 {league}")
            lines.append(f"📍 Esito: <b>{outcome}</b> @ <b>{odd_val:.2f}</b>")
            lines.append(f"💰 Stake Consigliato: <b>{stake}% del Bankroll</b>\n")

    lines.append("─────────────────────")
    lines.append("🔗 <i>Verifica il track-record e la dashboard sul portale web.</i>")

    send_message("\n".join(lines))

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
