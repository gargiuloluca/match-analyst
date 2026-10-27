"""
manage_subscribers.py — Gestore autonomo degli abbonamenti AtmBetSignal.
- Controlla le scadenze in data/subscribers.json.
- Espelle automaticamente dal Canale VIP Telegram gli utenti con abbonamento/prova terminati.
"""

import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
VIP_CHANNEL_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SUBS_FILE = DATA_DIR / "subscribers.json"

def kick_telegram_user(bot_token: str, channel_id: str, user_id: int) -> bool:
    """Rimuove un utente dal canale VIP revocando il suo accesso."""
    try:
        url_ban = f"https://api.telegram.org/bot{bot_token}/banChatMember"
        r1 = requests.post(url_ban, json={"chat_id": channel_id, "user_id": user_id}, timeout=10)
        
        # Unban immediato per consentire un eventuale rientro futuro se rinnova
        url_unban = f"https://api.telegram.org/bot{bot_token}/unbanChatMember"
        requests.post(url_unban, json={"chat_id": channel_id, "user_id": user_id, "only_if_banned": True}, timeout=10)
        
        return r1.status_code == 200 and r1.json().get("ok", False)
    except Exception as e:
        print(f"Errore rimozione utente {user_id}: {e}")
        return False

def main():
    if not SUBS_FILE.exists():
        print("Nessun database abbonati trovato.")
        return

    data = json.loads(SUBS_FILE.read_text(encoding="utf-8"))
    subscribers = data.get("subscribers", [])
    now = datetime.now(timezone.utc)
    updated = False

    for sub in subscribers:
        valid_until_str = sub.get("valid_until")
        if not valid_until_str:
            continue

        try:
            valid_until = datetime.fromisoformat(valid_until_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # Se la data è superata e lo stato è ancora ACTIVE
        if now > valid_until and sub.get("status") == "ACTIVE":
            print(f"Abbonamento scaduto per: {sub.get('email')}")
            sub["status"] = "EXPIRED"
            updated = True

            tg_id = sub.get("telegram_id")
            if tg_id and BOT_TOKEN and VIP_CHANNEL_ID:
                success = kick_telegram_user(BOT_TOKEN, VIP_CHANNEL_ID, tg_id)
                if success:
                    print(f"Utente Telegram {tg_id} espulso con successo dal canale VIP.")
                else:
                    print(f"Impossibile espellere l'utente Telegram {tg_id}.")

    if updated:
        SUBS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Database abbonati aggiornato con le nuove scadenze.")
    else:
        print("Tutti gli abbonati risultano in regola.")

if __name__ == "__main__":
    main()
