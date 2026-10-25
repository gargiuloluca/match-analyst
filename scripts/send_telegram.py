"""
send_telegram.py — Notifiche Istituzionali AtmBetSignal.
Invia le 3 Top Pick mattutine complete di probabilità reale, quota e Stake suggerito (Quarter-Kelly).
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
        f"🏧 <b>AtmBetSignal — Top 3 Istituzionali ({date_str})</b>",
        "<i>Motore Quantitativo Dixon-Coles | Quota ≥ 1.40 | Staking Quarter-Kelly</i>\n"
    ]

    badge_map = [
        ("conservativo", "🥇 TOP PICK 1 (Massima Probabilità)"),
        ("consigliato",  "🥈 TOP PICK 2 (Alta Affidabilità)"),
        ("hard",         "🥉 TOP PICK 3 (Alta Affidabilità)")
    ]

    for key, title in badge_map:
        p = picks.get(key)
        if not p:
            continue

        prob_pct = p['estimated_probability'] * 100
        edge_pct = (p.get('edge', 0)) * 100
        sign = "+" if edge_pct >= 0 else ""
        stake = p.get('suggested_stake_pct', 1.0)

        righe.append(
            f"{title}\n"
            f"⚽ <b>{p['match']}</b>\n"
            f"🏆 <i>{p.get('league', 'Campionato')}</i>\n"
            f"🎯 Esito: <b>{p['outcome_label']}</b>\n"
            f"📈 Quota: <code>{p['odd']:.2f}</code> | Prob: <b>{prob_pct:.1f}%</b>\n"
            f"💰 Stake Consigliato: <b>{stake}% del Bankroll</b> (Edge: {sign}{edge_pct:.1f}%)\n"
        )

    righe.append("🛡️ <i>Risk Management: Non superare mai lo stake raccomandato.</i>")
    righe.append("🌐 <i>Tracker & ROI in tempo reale su GitHub Pages.</i>")
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
        print(f"Errore Telegram: {e}")

if __name__ == "__main__":
    main()
