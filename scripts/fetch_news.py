"""
send_telegram.py
Invia il report dei pronostici odierni su Telegram con log di debug completi.
"""

import os
import json
import requests
from pathlib import Path

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "latest.json"

def main():
    print("--- INIZIO INVIO TELEGRAM ---")
    
    # 1. Verifica Secret
    if not BOT_TOKEN:
        print("ERRORE: Secret TELEGRAM_BOT_TOKEN mancante o vuoto!")
        return
    if not CHAT_ID:
        print("ERRORE: Secret TELEGRAM_CHAT_ID mancante o vuoto!")
        return
    print(f"Token presente (lunghezza: {len(BOT_TOKEN)}), Chat ID: {CHAT_ID}")

    # 2. Verifica File Dati
    print(f"Cerco file dati in: {DATA_PATH}")
    if not DATA_PATH.exists():
        print(f"ERRORE: Il file {DATA_PATH} non esiste!")
        return

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    date_str = data.get("date", "")
    picks = data.get("picks", {})
    print(f"Data trovata: {date_str}, Pronostici trovati: {len(picks)}")

    if not picks:
        msg = f"⚽ <b>Match Analyst — {date_str}</b>\n\nNessuna giocata con edge sufficiente individuata oggi."
    else:
        righe = [f"⚽ <b>Match Analyst — Pronostici {date_str}</b>\n"]
        
        p_cons = picks.get("conservativo")
        if p_cons:
            righe.append(
                f"🟢 <b>CONSERVATIVO</b>\n"
                f"• {p_cons['match']}\n"
                f"• Esito: <b>{p_cons['outcome_label']}</b>\n"
                f"• Quota: <code>{p_cons['odd']:.2f}</code> (Prob: {int(p_cons['estimated_probability']*100)}%)\n"
            )

        p_rec = picks.get("consigliato")
        if p_rec:
            righe.append(
                f"🔵 <b>CONSIGLIATO</b>\n"
                f"• {p_rec['match']}\n"
                f"• Esito: <b>{p_rec['outcome_label']}</b>\n"
                f"• Quota: <code>{p_rec['odd']:.2f}</code> (Prob: {int(p_rec['estimated_probability']*100)}%)\n"
            )

        p_hard = picks.get("hard")
        if p_hard:
            righe.append(
                f"🟠 <b>HARD</b>\n"
                f"• {p_hard['match']}\n"
                f"• Esito: <b>{p_hard['outcome_label']}</b>\n"
                f"• Quota: <code>{p_hard['odd']:.2f}</code> (Prob: {int(p_hard['estimated_probability']*100)}%)\n"
            )

        righe.append("📊 <i>Dettagli completi disponibili su GitHub Pages.</i>")
        msg = "\n".join(righe)

    # 3. Invio effettivo a Telegram
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"Risposta HTTP Telegram: {r.status_code}")
        if r.status_code == 200:
            print("SUCCESSO: Notifica Telegram inviata correttamente!")
        else:
            print(f"ERRORE TELEGRAM: {r.text}")
    except Exception as e:
        print(f"ECCEZIONE DI RETE: {e}")

if __name__ == "__main__":
    main()
