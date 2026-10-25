"""
send_telegram.py
Invia i 3 migliori pronostici a massima probabilità su Telegram.
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
    picks = data.get("picks", {})

    if not picks:
        return

    righe = [
        f"🎯 <b>Match Analyst — Top 3 del {date_str}</b>",
        "<i>Selezionate per massima probabilità di vincita (quota ≥ 1.40)</i>\n"
    ]

    p1 = picks.get("conservativo")
    if p1:
        righe.append(
            f"🥇 <b>TOP PICK 1 (Massima Probabilità)</b>\n"
            f"• <b>Match:</b> {p1['match']} ({p1.get('league', '')})\n"
            f"• <b>Esito:</b> <b>{p1['outcome_label']}</b>\n"
            f"• <b>Quota:</b> <code>{p1['odd']:.2f}</code> | Prob: <b>{int(p1['estimated_probability']*100)}%</b>\n"
        )

    p2 = picks.get("consigliato")
    if p2:
        righe.append(
            f"🥈 <b>TOP PICK 2 (Alta Affidabilità)</b>\n"
            f"• <b>Match:</b> {p2['match']} ({p2.get('league', '')})\n"
            f"• <b>Esito:</b> <b>{p2['outcome_label']}</b>\n"
            f"• <b>Quota:</b> <code>{p2['odd']:.2f}</code> | Prob: <b>{int(p2['estimated_probability']*100)}%</b>\n"
        )

    p3 = picks.get("hard")
    if p3:
        righe.append(
            f"🥉 <b>TOP PICK 3 (Alta Affidabilità)</b>\n"
            f"• <b>Match:</b> {p3['match']} ({p3.get('league', '')})\n"
            f"• <b>Esito:</b> <b>{p3['outcome_label']}</b>\n"
            f"• <b>Quota:</b> <code>{p3['odd']:.2f}</code> | Prob: <b>{int(p3['estimated_probability']*100)}%</b>\n"
        )

    righe.append("📊 <i>Dettagli completi e quote disponibili su GitHub Pages.</i>")
    msg = "\n".join(righe)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

if __name__ == "__main__":
    main()
