"""
"""
analyze_master.py — AtmBetSignal Master Selector & AI Ranking Engine (Model E)
Versione Corretta e Ottimizzata
- Raccoglie tutti i pronostici generati dai motori A, B, C, D (supporta tutte le strutture di chiavi)
- Applica un algoritmo di scoring multi-fattoriale (Consenso, Edge, Quota, Lega)
- Seleziona esclusivamente le Top 5 opportunità assolute della giornata
"""

import os
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FINAL_SIGNALS_FILE = DATA_DIR / "latest_master.json"

def load_all_engine_signals():
    """Raccoglie tutti i pronostici prodotti dai vari motori supportando formati multipli."""
    all_candidates = []
    model_files = ["latest.json", "latest_xg.json", "latest_safe.json", "latest_fund.json"]
    
    for filename in model_files:
        f_path = DATA_DIR / filename
        if f_path.exists():
            try:
                data = json.loads(f_path.read_text(encoding="utf-8"))
                
                # Estrae gli elementi gestendo sia dizionari strutturati che liste pure
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("all_selected_picks", data.get("selections", data.get("portfolio", [])))
                
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    
                    # Normalizzazione delle chiavi essenziali per evitare disallineamenti
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
    
    # 1. Fattore Quota (Supporta sia 'odd' che 'odds' o 'price')
    odds = float(signal.get("odd", signal.get("odds", signal.get("price", 1.80))))
    if 1.45 <= odds <= 2.50:
        score += 15.0
    elif 1.30 <= odds < 1.45 or 2.50 < odds <= 3.00:
        score += 8.0
    else:
        score -= 5.0

    # 2. Fattore Edge / Valore Atteso (Supporta 'edge' o 'ev')
    edge = float(signal.get("edge", signal.get("ev", 0.03)))
    if edge >= 0.05:
        score += 15.0
    elif edge >= 0.025:
        score += 10.0

    # 3. Fattore Probabilità Implicita (Supporta 'estimated_probability' o 'prob')
    prob = float(signal.get("estimated_probability", signal.get("prob", signal.get("probability", 0.6))))
    if prob >= 0.72:
        score += 15.0  # Alta affidabilità (stile Safe80 / Ufficiale top)
    elif prob >= 0.65:
        score += 10.0

    # 4. Fattore Tier (Premia i livelli Diamond e Gold generati a monte)
    tier = str(signal.get("tier", "")).upper()
    if "DIAMOND" in tier:
        score += 15.0
    elif "GOLD" in tier:
        score += 10.0
    elif "OFFICIAL" in tier or "SAFE" in tier:
        score += 5.0

    return round(max(0.0, min(100.0, score)), 2)

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    candidates = load_all_engine_signals()
    
    if not candidates:
        print("Master Selector: Nessun candidato trovato dai motori.")
        FINAL_SIGNALS_FILE.write_text(json.dumps({"engine": "Model E — Master Selector AI Top 5", "total_evaluated": 0, "selections": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # Assegna uno score a ciascun candidato
    scored_candidates = []
    for cand in candidates:
        score = evaluate_and_score_signal(cand)
        cand["master_score"] = score
        scored_candidates.append(cand)

    # Ordina per punteggio decrescente
    scored_candidates.sort(key=lambda x: x["master_score"], reverse=True)

    # SELEZIONA ESCLUSIVAMENTE LE TOP 5 ASSOLUTE
    top_5_selections = scored_candidates[:5]

    output_payload = {
        "engine": "Model E — Master Selector AI Top 5",
        "total_evaluated": len(candidates),
        "selections": top_5_selections
    }

    FINAL_SIGNALS_FILE.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Master Selector completato: filtrate {len(candidates)} opportunità, selezionate le Top {len(top_5_selections)} definitive.")

if __name__ == "__main__":
    main()
