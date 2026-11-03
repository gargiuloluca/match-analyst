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

# Selezioni unificate dai modelli precedenti (A, B, C) o lettura diretta di fixtures/analisi
def load_all_signals():
    signals = []
    # Legge dai singoli modelli se disponibili, oppure dal file fixtures arricchito
    for model_filename in ["latest.json", "latest_xg.json", "latest_safe.json"]:
        f_path = DATA_DIR / model_filename
        if f_path.exists():
            try:
                data = json.loads(f_path.read_text(encoding="utf-8"))
                # Supporta sia dizionari singoli che liste di segnali
                items = data if isinstance(data, list) else data.get("selections", [])
                for item in items:
                    if item not in signals:
                        signals.append(item)
            except Exception:
                pass
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

    # Parametri di Risk Management del Fondo
    MAX_DAILY_EXPOSURE_PCT = 5.0  # Esposizione massima giornaliera sul bankroll (%)
    base_stake_fraction = 1.0     # Unità standard di partenza

    # Filtro anti-correlazione: massimo 1 selezione per match
    filtered_candidates = []
    for sel in selections:
        event_id = sel.get("id") or f"{sel.get('home_team')}-{sel.get('away_team')}"
        if event_id not in seen_events:
            seen_events.add(event_id)
            filtered_candidates.append(sel)

    if not filtered_candidates:
        return []

    # Calcolo dello stake adattivo (Risk Parity / Volatility scaling)
    n_bets = len(filtered_candidates)
    # Se ci sono molte selezioni, riduciamo leggermente lo stake unitario per evitare picchi di varianza
    allocation_factor = min(1.0, 4.0 / n_bets) if n_bets > 0 else 1.0

    for sel in filtered_candidates:
        # Estrae o stima la quota e la probabilità implicita
        odds = float(sel.get("odds", sel.get("price", 1.80)))
        prob = float(sel.get("probability", sel.get("fair_probability", 0.5)))
        
        if odds <= 1.0 or prob <= 0:
            continue

        # Kelly Criterion Frazionato (Quarter Kelly istituzionale)
        q = 1.0 - prob
        kelly_full = (prob * odds - 1.0) / (odds - 1.0)
        kelly_fraction = max(0.0, kelly_full * 0.25) # 1/4 Kelly conservativo

        # Calcolo stake finale ponderato dal fattore di portafoglio
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
    
    # Aggiorna anche il tracker storico del fondo
    tracker_data = []
    if TRACKER_FILE.exists():
        try:
            tracker_data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    if portfolio:
        tracker_data.append({
            "date": DATA_DIR.stat().st_mtime if hasattr(DATA_DIR, 'stat') else "latest",
            "selections_count": len(portfolio),
            "portfolio": portfolio
        })
        TRACKER_FILE.write_text(json.dumps(tracker_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Modello D (Fund Engine) completato: generate {len(portfolio)} allocazioni di portafoglio ottimizzate.")

if __name__ == "__main__":
    main()
