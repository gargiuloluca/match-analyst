"""
send_telegram.py — Notifiche Sniper AtmBetSignal.
Adatta il messaggio in base al giorno:
- Infrasettimanale: Max 2-3 colpi chirurgici.
- Weekend: Max 5 selezioni ad altissima probabilità.
- Se nessuna partita supera il 65%: notifica di protezione del capitale.
"""

import os
import json
import requests
from pathlib import Path

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "latest.json"

def main():
    if not BOT_TOKEN or not CHAT_ID or not DATA_PATH.exists():
        return

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    date_str = data.get("date", "")
    picks = data.get("all_selected_picks", [])
    weekday = data.get("weekday", 0)

    periodo = "Edizione Weekend" if weekday in (5, 6) else "Edizione Infrasettimanale"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # Se nessuna partita ha superato il 65% di probabilità
    if not picks:
        msg = (
            f"🏧 <b>AtmBetSignal — {periodo} ({date_str})</b>\n\n"
            f"🛡️ <b>Capitale Protetto: Nessun segnale oggi.</b>\n"
            f"Tutte le partite scansionate avevano probabilità &lt; 65% o quote non vantaggiose.\n"
            f"<i>La regola fondamentale dell'investimento sportivo è preservare il bankroll quando non c'è reale valore.</i>"
        )
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=15)
        return

    medaglie = ["🥇", "🥈", "🥉", "🎯", "🎯"]
    righe = [
        f"🏧 <b>AtmBetSignal — {periodo} ({date_str})</b>",
        f"<i>{len(picks)} Operazioni ad Alta Probabilità (Soglia ≥ 65% | Quota ≥ 1.40)</i>\n"
    ]

    for idx, p in enumerate(picks):
        badge = medaglie[idx] if idx < len(medaglie) else "🎯"
        prob_pct = p['estimated_probability'] * 100
        stake = p.get('suggested_stake_pct', 1.0)

        righe.append(
            f"{badge} <b>SELEZIONE #{idx + 1}</b>\n"
            f"⚽ <b>{p['match']}</b>\n"
            f"🏆 <i>{p.get('league', 'Campionato')}</i>\n"
            f"🎯 Giocata: <b>{p['outcome_label']}</b>\n"
            f"📈 Quota: <code>{p['odd']:.2f}</code> | Probabilità: <b>{prob_pct:.1f}%</b>\n"
            f"💰 Stake Suggerito: <b>{stake}% del Bankroll</b>\n"
        )

    righe.append("🛡️ <i>Gestione del rischio: Massima disciplina, segui rigorosamente lo stake indicato.</i>")
    righe.append("🌐 <i>Tracker & Storico certificato su GitHub Pages.</i>")

    payload = {
        "chat_id": CHAT_ID,
        "text": "\n".join(righe),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Errore Telegram: {e}")

if __name__ == "__main__":
    main()
