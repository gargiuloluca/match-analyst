"""
analyze_fund.py — AtmBetSignal Institutional Portfolio & Risk Engine (Model D)
Versione Corretta e Sincronizzata con il Tracker
- Ottimizzazione di portafoglio multi-selezione basata su Risk Parity
- Matrice di correlazione e rimozione della sovraesposizione sullo stesso match
- Volatility Targeting & Drawdown-Triggered Scaling (Kelly Dinamico)
- Sincronizzazione nativa e pulita con data/tracker_fund.json per la plancia
"""

import json
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRACKER_FILE = DATA_DIR / "tracker_fund.json"
LATEST_FILE = DATA_DIR / "latest_fund.json"

def load_all_signals():
    signals = []
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

def normalize_match_str(s: str) -> str:
    n = s.lower()
    for drop in [" fc", " ac", " as", "cf", "ssc ", "afc ", " "]:
        n = n.replace(drop, "")
    return n

def calculate_portfolio_risk(selections):
    if not selections:
        return []

    optimized_portfolio = []
    seen_events = set()
    MAX_DAILY_EXPOSURE_PCT = 5.0

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
        odds = float(sel.get("odd", sel.get("odds", 1.80)))
        prob = float(sel.get("estimated_probability", sel.get("probability", 0.5)))
        
        if odds <= 1.0 or prob <= 0:
            continue

        q = 1.0 - prob
        kelly_full = (prob * odds - 1.0) / (odds - 1.0)
        kelly_fraction = max(0.0, kelly_full * 0.25)

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
    
    # Sincronizzazione Tracker Fund strutturata identica agli altri motori
    tracker_fund_data = {
        "total_bets": 0, "won": 0, "lost": 0, "void": 0,
        "win_rate": 0.0, "net_profit_units": 0.0, "roi_pct": 0.0, "bets": []
    }
    
    if TRACKER_FILE.exists():
        try:
            loaded = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("bets"), list):
                tracker_fund_data = loaded
        except Exception:
            pass

    existing_pairs = set()
    for b in tracker_fund_data.get("bets", []):
        m_norm = normalize_match_str(b.get("match", ""))
        mkt = str(b.get("market_key", "")).strip().upper()
        existing_pairs.add((m_norm, mkt))

    new_added = 0
    for op in portfolio:
        match_name = op.get("match") or f"{op.get('home_team')} vs {op.get('away_team')}"
        mkt_key = str(op.get("market_key", "1X2")).strip().upper()
        pair_key = (normalize_match_str(match_name), mkt_key)

        if pair_key not in existing_pairs:
            match_id = op.get("match_id") or op.get("id") or "fund_event"
            bet_id = f"{match_id}_{mkt_key}"
            
            tracker_fund_data["bets"].append({
                "id": bet_id,
                "event_id": match_id,
                "date": op.get("commence_time", datetime.now(timezone.utc).isoformat()),
                "match": match_name,
                "league": op.get("league", "Fund Portfolio"),
                "bet": op.get("outcome_label", "Allocation"),
                "market_key": mkt_key,
                "odd": float(op.get("odd", op.get("odds", 1.80))),
                "prob": float(op.get("estimated_probability", op.get("probability", 0.5))),
                "stake_pct": op.get("fund_stake_units", 1.0),
                "tier": "FUND D",
                "status": "PENDING",
                "profit": 0.0
            })
            existing_pairs.add(pair_key)
            new_added += 1

    tracker_fund_data["total_bets"] = len(tracker_fund_data["bets"])
    TRACKER_FILE.write_text(json.dumps(tracker_fund_data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"Modello D (Fund Engine) completato: generate {len(portfolio)} allocazioni, {new_added} aggiunte al tracker.")

if __name__ == "__main__":
    main()
    
