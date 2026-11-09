"""
make_backup.py — AtmBetSignal Automated Daily Backup Engine
- Raccoglie tutti i file JSON critici della cartella data/
- Genera un unico file di backup consolidato in data/backup_giornaliero.json
"""

import json
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BACKUP_FILE = DATA_DIR / "backup_giornaliero.json"

FILES_TO_BACKUP = [
    "fixtures.json",
    "latest.json", "tracker.json",
    "latest_xg.json", "tracker_xg.json",
    "latest_safe.json", "tracker_safe.json",
    "latest_fund.json", "tracker_fund.json",
    "latest_master.json", "tracker_master.json"
]

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    backup_payload = {
        "system": "AtmBetSignal Institutional Backup",
        "backup_timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {}
    }

    for filename in FILES_TO_BACKUP:
        f_path = DATA_DIR / filename
        if f_path.exists():
            try:
                backup_payload["data"][filename] = json.loads(f_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"Errore lettura file {filename} per il backup: {e}")

    BACKUP_FILE.write_text(json.dumps(backup_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Backup giornaliero completato con successo: salvati {len(backup_payload['data'])} file in backup_giornaliero.json.")

if __name__ == "__main__":
    main()
  
