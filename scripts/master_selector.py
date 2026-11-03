
"""
master_selector.py — AtmBetSignal Master Selector & AI Ranking Engine (Model E)
- Raccoglie tutti i pronostici generati dai motori A, B, C, D
- Applica un algoritmo di scoring multi-fattoriale (Consenso, Edge, Quota, Lega)
- Seleziona esclusivamente le Top 5 opportunità assolute della giornata
"""

import os
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FINAL_SIGNALS_FILE = DATA_DIR / "latest_master.json"

def load_all_engine_signals():
    """Raccoglie tutti i segnali prodotti dai vari motori."""
    all_candidates = []
    
    # File generati dai vari modelli precedenti
    model_files = ["latest.json", "latest_xg.json", "latest_safe.json", "latest_fund.json"]
    
    for filename in model_files:
        f_path = DATA_DIR / filename
        if f_path.exists():
            try:
                data = json.loads(f_path.read_text(encoding="utf-8"))
                items = data if isinstance(data, list) else data.get("selections", [])
                for item in items:
                    unique_key = (item.get("id"), item.get("market", "1X2"))
                    if not any(c.get("_unique_key") == unique_key for c in all_candidates):
                        item["_unique_key"] = unique_key
                        all_candidates.append(item)
            except Exception:
                pass
                
    return all_candidates

def evaluate_and_score_signal(signal):
    """
    Algoritmo di Scoring Multi-Fattoriale (0 - 100):
    Valuta la qualità della scommessa basandosi su parametri quantitativi puri.
    """
    score = 50.0  # Base di partenza
    
    # 1. Fattore Quota (Premia lo "Sweet Spot" tra 1.50 e 2.30)
    odds = float(signal.get("odds", signal.get("price", 1.80)))
    if 1.50 <= odds <= 2.30:
        score += 15.0
    elif 1.30 <= odds < 1.50 or 2.30 < odds <= 3.00:
        score += 8.0
    else:
        score -= 5.0

    # 2. Fattore Edge / Valore (Margine di overround pulito)
    overround = float(signal.get("overround_pct", 5.0))
    if overround < 5.0:
        score += 10.0

    # 3. Fattore Probabilità Implicita / Affidabilità
    prob = float(signal.get("probability", signal.get("fair_probability", 0.6)))
    if prob >= 0.75:
        score += 15.0
    elif prob >= 0.60:
        score += 10.0

    # 4. Fattore Lega di Elite
    sport_key = signal.get("sport_key", "")
    elite_leagues = ["soccer_italy_serie_a", "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga", "soccer_efl_champ", "soccer_italy_serie_b"]
    if sport_key in elite_leagues:
        score += 10.0
    else:
        score += 5.0

    return round(max(0.0, min(100.0, score)), 2)

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    candidates = load_all_engine_signals()
    
    if not candidates:
        print("Master Selector: Nessun candidato trovato dai motori.")
        FINAL_SIGNALS_FILE.write_text(json.dumps({"selections": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

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
  
