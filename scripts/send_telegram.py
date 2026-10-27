"""
send_telegram.py — Report Istituzionale Giornaliero AtmBetSignal
Evidenzia giocate DIAMOND, GOLD, OFFICIAL e flussi Smart Money.
"""

import os
import json
import requests
from pathlib import Path

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LATEST_FILE = DATA_DIR / "latest.json"

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
    if not LATEST_FILE.exists():
        print("latest.json non trovato.")
        return

    data = json.loads(LATEST_FILE.read_text(encoding="utf-8"))
    officials = data.get("all_selected_picks", [])
    radar = data.get("radar_watchlist", [])

    lines = []
    lines.append("<b>🏧 AtmBetSignal — Intelligence Report</b>")
    lines.append("<i>Modello Bivariato Dixon-Coles & Smart Money Flow</i>\n")

    if not officials:
        lines.append("🛡️ <b>Capitale Protetto:</b> Nessun evento del palinsesto supera la soglia istituzionale del 65% o rispetta i vincoli di flusso di quota. Zero scommesse forzate per preservare il bankroll.")
    else:
        lines.append(f"🎯 <b>TOP {len(officials)} SELEZIONI UFFICIALI (Soglia ≥ 65%)</b>\n")
        for i, p in enumerate(officials, 1):
            tier = p.get("tier", "OFFICIAL")
            badge = "🎯 SEGNALE PRO"
            if tier == "DIAMOND":
                badge = "💎 <b>DIAMOND PICK (Massimo Edge & Smart Money)</b>"
            elif tier == "GOLD":
                badge = "🥇 <b>GOLD PICK (Super Affidabilità)</b>"

            prob_pct = f"{p['estimated_probability'] * 100:.1f}%"
            edge_pct = f"{p['edge'] * 100:+.1f}%"
            shift = p.get("line_shift_pct", 0.0)
            shift_tag = f" | Quota: {shift:+.1f}%" if shift != 0.0 else ""

            lines.append(f"{badge}")
            lines.append(f"⚽ <b>{p['match']}</b>")
            lines.append(f"🏆 {p['league']}")
            lines.append(f"📍 Esito: <b>{p['outcome_label']}</b> @ <b>{p['odd']:.2f}</b>")
            lines.append(f"📊 Stima: <b>{prob_pct}</b> | Edge: <code>{edge_pct}</code>{shift_tag}")
            lines.append(f"💰 Stake Kelly: <b>{p['suggested_stake_pct']}% del Bankroll</b>\n")

    if radar:
        lines.append("─────────────────────")
        lines.append(f"📡 <b>WATCHLIST RADAR ({len(radar)} Match per Studio)</b>")
        lines.append("<i>(Quote / Esiti a scopo puramente statistico)</i>\n")
        for i, r in enumerate(radar, 1):
            r_prob = f"{r['estimated_probability'] * 100:.1f}%"
            lines.append(f"{i}. <b>{r['match']}</b>")
            lines.append(f"   ↳ {r['outcome_label']} @ {r['odd']:.2f} (Prob: {r_prob})")

    lines.append("\n🔗 <i>Verifica il track-record e la dashboard sul portale web.</i>")

    send_message("\n".join(lines))

if __name__ == "__main__":
    main()
