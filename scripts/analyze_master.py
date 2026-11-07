"""
analyze_master.py — AtmBetSignal Master Selector & AI Ranking Engine (Model E)
Versione Sincronizzata con il Tracker per la Plancia
- Raccoglie tutti i pronostici generati dai motori A, B, C, D (supporta tutte le strutture di chiavi)
- Applica un algoritmo di scoring multi-fattoriale (Consenso, Edge, Quota, Lega)
- Seleziona esclusivamente le Top 5 opportunità assolute della giornata
- Sincronizzazione nativa con data/tracker_master.json
"""

import os
import json
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FINAL_SIGNALS_FILE = DATA_DIR / "latest_master.json"
TRACKER_MASTER_FILE = DATA_DIR / "tracker_master.json"

def load_all_engine_signals():
    """Raccoglie tutti i pronostici prodotti dai vari motori supportando formati multipli."""
    all_candidates = []
    model_files = ["latest.json", "latest_xg.json", "latest_safe.json", "latest_fund.json"]
    
    for filename in model_files:
        f_path = DATA_DIR / filename
        if f_path.exists():
            try:
                data = json.loads(f_path.read_text(encoding="utf-8"))
                
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("all_selected_picks", data.get("selections", data.get("portfolio", [])))
                
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    
                    match_id = item.get("match_id") or item.get("id") or item.get("event_id")
                    market_key = item.get("market_key") or item.get("market") or "1X2"
                    
                    unique_key = (str(match_id), str(market_key))
                    if not any(c.get("_unique_key") == unique_key for c in all_candidates):
                        item["_unique_key"] = unique_key
                        all_candidates.append(item)
            except Exception as e:
                print(f"Errore caricamento {filename} nel Master: {e}")
                
    return all_candidates

def evaluate_and_score_signal(signal):
    """
    Algoritmo di Scoring Multi-Fattoriale (0 - 100):
    Valuta la qualità della scommessa basandosi sui parametri quantitativi dei modelli.
    """
    score = 50.0  # Base di partenza
    
    odds = float(signal.get("odd", signal.get("odds", signal.get("price", 1.80))))
    if 1.45 <= odds <= 2.50:
        score += 15.0
    elif 1.30 <= odds < 1.45 or 2.50 < odds <= 3.00:
        score += 8.0
    else:
        score -= 5.0

    edge = float(signal.get("edge", signal.get("ev", 0.03)))
    if edge >= 0.05:
        score += 15.0
    elif edge >= 0.025:
        score += 10.0

    prob = float(signal.get("estimated_probability", signal.get("prob", signal.get("probability", 0.6))))
    if prob >= 0.72:
        score += 15.0
    elif prob >= 0.65:
        score += 10.0

    tier = str(signal.get("tier", "")).upper()
    if "DIAMOND" in tier:
        score += 15.0
    elif "GOLD" in tier:
        score += 10.0
    elif "OFFICIAL" in tier or "SAFE" in tier:
        score += 5.0

    return round(max(0.0, min(100.0, score)), 2)

def normalize_match_str(s: str) -> str:
    n = s.lower()
    for drop in [" fc", " ac", " as", "cf", "ssc ", "afc ", " "]:
        n = n.replace(drop, "")
    return n

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    candidates = load_all_engine_signals()
    
    if not candidates:
        print("Master Selector: Nessun candidato trovato dai motori.")
        FINAL_SIGNALS_FILE.write_text(json.dumps({"engine": "Model E — Master Selector AI Top 5", "total_evaluated": 0, "selections": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    scored_candidates = []
    for cand in candidates:
        score = evaluate_and_score_signal(cand)
        cand["master_score"] = score
        scored_candidates.append(cand)

    scored_candidates.sort(key=lambda x: x["master_score"], reverse=True)
    top_5_selections = scored_candidates[:5]

    output_payload = {
        "engine": "Model E — Master Selector AI Top 5",
        "total_evaluated": len(candidates),
        "selections": top_5_selections
    }

    FINAL_SIGNALS_FILE.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Sincronizzazione Tracker Master per la tabella dello storico in basso
    tracker_master_data = {
        "total_bets": 0, "won": 0, "lost": 0, "void": 0,
        "win_rate": 0.0, "net_profit_units": 0.0, "roi_pct": 0.0, "bets": []
    }
    
    if TRACKER_MASTER_FILE.exists():
        try:
            loaded = json.loads(TRACKER_MASTER_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("bets"), list):
                tracker_master_data = loaded
        except Exception:
            pass

    existing_pairs = set()
    for b in tracker_master_data.get("bets", []):
        m_norm = normalize_match_str(b.get("match", ""))
        mkt = str(b.get("market_key", "")).strip().upper()
        existing_pairs.add((m_norm, mkt))

    new_added = 0
    for op in top_5_selections:
        match_name = op.get("match") or f"{op.get('home_team')} vs {op.get('away_team')}"
        mkt_key = str(op.get("market_key", op.get("market", "1X2"))).strip().upper()
        pair_key = (normalize_match_str(match_name), mkt_key)

        if pair_key not in existing_pairs:
            match_id = op.get("match_id") or op.get("id") or "master_event"
            bet_id = f"{match_id}_{mkt_key}"
            
            tracker_master_data["bets"].append({
                "id": bet_id,
                "event_id": match_id,
                "date": op.get("commence_time", datetime.now(timezone.utc).isoformat()),
                "match": match_name,
                "league": op.get("league", "Master Top 5"),
                "bet": op.get("outcome_label", op.get("bet", "Master Pick")),
                "market_key": mkt_key,
                "odd": float(op.get("odd", op.get("odds", op.get("price", 1.80)))),
                "prob": float(op.get("estimated_probability", op.get("probability", 0.6))),
                "stake_pct": float(op.get("suggested_stake_pct", op.get("fund_stake_units", 1.0))),
                "tier": f"MASTER AI ({op.get('master_score', 0)})",
                "status": "PENDING",
                "profit": 0.0
            })
            existing_pairs.add(pair_key)
            new_added += 1

    tracker_master_data["total_bets"] = len(tracker_master_data["bets"])
    TRACKER_MASTER_FILE.write_text(json.dumps(tracker_master_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Master Selector completato: filtrate {len(candidates)} opportunità, selezionate le Top {len(top_5_selections)} definitive, {new_added} aggiunte al tracker.")

if __name__ == "__main__":
    main()
    
