"""
send_telegram.py — Notifiche Top 5 AtmBetSignal.
Invia su Telegram le migliori 5 operazioni del giorno con probabilità >= 65% e quota >= 1.40.
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

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # Se nessuna partita ha superato la soglia del 65%
    if not picks:
        msg = (
            f"🏧 <b>AtmBetSignal — Selezione Top 5 ({date_str})</b>\n\n"
            f"🛡️ <b>Capitale Protetto: Nessun segnale conforme oggi.</b>\n"
            f"Nessuna partita ha raggiunto i parametri minimi di sicurezza (Probabilità ≥ 65% e Quota ≥ 1.40).\n"
            f"<i>La regola primaria è preservare il capitale quando il mercato non offre valore reale.</i>"
        )
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=15)
        return

    badges = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    righe = [
        f"🏧 <b>AtmBetSignal — I Migliori {len(picks)} Pronostici ({date_str})</b>",
        f"<i>Selezione Quantitativa ad Altissima Probabilità (≥ 65% | Quota ≥ 1.40)</i>\n"
    ]

    for idx, p in enumerate(picks):
        icon = badges[idx] if idx < len(badges) else "🎯"
        prob_pct = p['estimated_probability'] * 100
        edge_pct = (p.get('edge', 0)) * 100
        sign = "+" if edge_pct >= 0 else ""
        stake = p.get('suggested_stake_pct', 1.0)

        righe.append(
            f"{icon} <b>TOP PICK #{idx + 1}</b>\n"
            f"⚽ <b>{p['match']}</b>\n"
            f"🏆 <i>{p.get('league', 'Campionato')}</i>\n"
            f"🎯 Esito: <b>{p['outcome_label']}</b>\n"
            f"📈 Quota: <code>{p['odd']:.2f}</code> | Probabilità: <b>{prob_pct:.1f}%</b>\n"
            f"💰 Stake Consigliato: <b>{stake}% del Bankroll</b> (Edge: {sign}{edge_pct:.1f}%)\n"
        )

    righe.append("🛡️ <i>Risk Management: Giocare solo in singola. Non superare gli stake consigliati.</i>")
    righe.append("🌐 <i>Equity Line e Storico certificato su GitHub Pages.</i>")

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
