"""
send_telegram.py — Notifiche Istituzionali AtmBetSignal.
- Selezioni Ufficiali (Top 5 con soglia >= 65%).
- Se nessuna partita supera il 65%, notifica la protezione del capitale.
- Watchlist Radar (Top 10): studio statistico separato (NO BET ufficiale).
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
    official_picks = data.get("all_selected_picks", [])
    radar_watchlist = data.get("radar_watchlist", [])

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    righe = []

    # 1. INTESTAZIONE & SELEZIONI UFFICIALI (>= 65%)
    righe.append(f"🏧 <b>AtmBetSignal — Report Quantitativo ({date_str})</b>\n")

    if not official_picks:
        righe.append(
            "🛡️ <b>Capitale Protetto: Nessun segnale operativo oggi.</b>\n"
            "Nessun evento in palinsesto ha superato la soglia minima di sicurezza (<b>Probabilità ≥ 65%</b> e Quota ≥ 1.40).\n"
            "<i>La regola primaria è preservare il capitale quando il mercato non offre valore reale.</i>\n"
        )
    else:
        righe.append(
            f"🎯 <b>SELEZIONI UFFICIALI OPERATIVE (Top {len(official_picks)})</b>\n"
            f"<i>Parametri: Probabilità ≥ 65.0% | Quota ≥ 1.40 | Quarter-Kelly</i>\n"
        )
        badges = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for idx, p in enumerate(official_picks):
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
                f"💰 Stake Consigliato: <b>{stake}%</b> (Edge: {sign}{edge_pct:.1f}%)\n"
            )

    # 2. LINEA DI SEPARAZIONE E WATCHLIST RADAR (TOP 10 PER ANALISI)
    if radar_watchlist:
        righe.append("───────────────────────")
        righe.append(
            "📡 <b>RADAR QUANTITATIVO (Top 10 Watchlist)</b>\n"
            "⚠️ <i>Eventi appena sotto soglia o con quote compresse. Esclusivamente per studio e monitoraggio statistico (<b>NO BET Ufficiale</b>).</i>\n"
        )

        for idx, r in enumerate(radar_watchlist):
            prob_pct = r['estimated_probability'] * 100
            righe.append(
                f"▫️ <b>{r['match']}</b>\n"
                f"   Esito: <code>{r['outcome_label']}</code> @ <b>{r['odd']:.2f}</b> (Prob: <b>{prob_pct:.1f}%</b> | <i>{r.get('league','')}</i>)"
            )

    righe.append("\n🌐 <i>Performance ed Equity Line certificate su GitHub Pages.</i>")

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
