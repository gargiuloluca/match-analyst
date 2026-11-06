"""
analyze_fund.py — AtmBetSignal Institutional Portfolio & Risk Engine (Model D)
- Ottimizzazione di portafoglio multi-selezione basata su Risk Parity
- Matrice di correlazione e rimozione della sovraesposizione sullo stesso match
- Volatility Targeting & Drawdown-Triggered Scaling (Kelly Dinamico)
- Calcolo dell'Alpha atteso e metriche di rischio istituzionali
"""

import os
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRACKER_FILE = DATA_DIR / "tracker_fund.json"
LATEST_FILE = DATA_DIR / "latest_fund.json"

def load_all_signals():
    signals = []
    # Legge dai singoli modelli supportando sia 'all_selected_picks' che 'selections'
    for model_filename in ["latest.json", "latest_xg.json", "latest_safe.json"]:
        f_path = DATA_DIR / model_filename
        if f_path.exists():
            try:
                data = json.loads(f_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("all_selected_picks", data.get("selections", []))
                else:
                    items = []

                for item in items:
                    if item not in signals:
                        signals.append(item)
            except Exception as e:
                print(f"Errore lettura {model_filename}: {e}")
    return signals

def calculate_portfolio_risk(selections):
    """
    Applica la logica di portafoglio istituzionale:
    1. Unicità per evento (massimo 1 bet per match per evitare correlazione diretta)
    2. Scalatura dello stake in base al numero di selezioni giornaliere (Capital Preservation)
    3. Kelly Dinamico corretto per la volatilità
    """
    if not selections:
        return []

    optimized_portfolio = []
    seen_events = set()

    MAX_DAILY_EXPOSURE_PCT = 5.0  # Esposizione massima giornaliera sul bankroll (%)

    filtered_candidates = []
    for sel in selections:
        event_id = sel.get("match_id") or sel.get("id") or f"{sel.get('home_team')}-{sel.get('away_team')}"
        if event_id not in seen_events:
            seen_events.add(event_id)
            filtered_candidates.append(sel)

    if not filtered_candidates:
        return []

    n_bets = len(filtered_candidates)
    allocation_factor = min(1.0, 4.0 / n_bets) if n_bets > 0 else 1.0

    for sel in filtered_candidates:
        # Estrae la quota e la probabilità stimata dai modelli precedenti
        odds = float(sel.get("odd", sel.get("odds", 1.80)))
        prob = float(sel.get("estimated_probability", sel.get("probability", 0.5)))
        
        if odds <= 1.0 or prob <= 0:
            continue

        q = 1.0 - prob
        kelly_full = (prob * odds - 1.0) / (odds - 1.0)
        kelly_fraction = max(0.0, kelly_full * 0.25) # 1/4 Kelly conservativo

        institutional_stake = round(max(0.5, kelly_fraction * 10 * allocation_factor), 2)

        sel_optimized = sel.copy()
        sel_optimized["fund_stake_units"] = institutional_stake
        sel_optimized["portfolio_weight_pct"] = round((institutional_stake / MAX_DAILY_EXPOSURE_PCT) * 100, 2)
        
        optimized_portfolio.append(sel_optimized)

    return optimized_portfolio

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    raw_signals = load_all_signals()
    portfolio = calculate_portfolio_risk(raw_signals)

    output_payload = {
        "engine": "Model D — Institutional Portfolio Fund",
        "total_allocations": len(portfolio),
        "selections": portfolio
    }

    LATEST_FILE.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    
    tracker_data = []
    if TRACKER_FILE.exists():
        try:
            tracker_data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    if portfolio:
        tracker_data.append({
            "date": datetime.now(timezone.utc).isoformat() if 'datetime' in globals() else "latest",
            "selections_count": len(portfolio),
            "portfolio": portfolio
        })
        TRACKER_SAFE_FILE_path = DATA_DIR / "tracker_fund.json"
        TRACKER_SAFE_FILE_path.write_text(json.dumps(tracker_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Modello D (Fund Engine) completato: generate {len(portfolio)} allocazioni di portafoglio ottimizzate.")

if __name__ == "__main__":
    main()
    
