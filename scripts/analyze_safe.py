"""
analyze_safe.py — AtmBetSignal High-Probability Sniper Engine (Model C: Safe >= 80%, Quota >= 1.40)
Filtra con precisione matematica e alimenta in automatico data/tracker_safe.json:
- Probabilità stimata: >= 80.0%
- Quota minima: >= 1.40
Salva i risultati separatamente in data/latest_safe.json e data/tracker_safe.json.
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"
OUTPUT_SAFE_FILE = DATA_DIR / "latest_safe.json"
TRACKER_SAFE_FILE = DATA_DIR / "tracker_safe.json"

LEAGUE_GOAL_PROFILES = {
    "soccer_italy_serie_a": {"mu_home": 1.45, "mu_away": 1.15, "tau": -0.05},
    "soccer_epl": {"mu_home": 1.55, "mu_away": 1.25, "tau": -0.04},
    "soccer_spain_la_liga": {"mu_home": 1.40, "mu_away": 1.05, "tau": -0.06},
    "soccer_germany_bundesliga": {"mu_home": 1.70, "mu_away": 1.35, "tau": -0.03},
    "soccer_france_ligue_one": {"mu_home": 1.40, "mu_away": 1.10, "tau": -0.05},
    "soccer_uefa_champs_league": {"mu_home": 1.60, "mu_away": 1.30, "tau": -0.04},
    "soccer_uefa_europa_league": {"mu_home": 1.55, "mu_away": 1.25, "tau": -0.04},
    "soccer_netherlands_eredivisie": {"mu_home": 1.75, "mu_away": 1.30, "tau": -0.02},
    "soccer_england_championship": {"mu_home": 1.42, "mu_away": 1.12, "tau": -0.05},
    "soccer_portugal_primeira_liga": {"mu_home": 1.48, "mu_away": 1.02, "tau": -0.06},
    "soccer_belgium_first_div": {"mu_home": 1.58, "mu_away": 1.28, "tau": -0.04},
    "soccer_england_league1": {"mu_home": 1.40, "mu_away": 1.15, "tau": -0.05},
    "soccer_england_efl_cup": {"mu_home": 1.50, "mu_away": 1.20, "tau": -0.04},
    "default": {"mu_home": 1.48, "mu_away": 1.18, "tau": -0.05}
}

def poisson_pmf(k: int, lambd: float) -> float:
    return (lambd ** k) * math.exp(-lambd) / math.factorial(k)

def tau_factor(x: int, y: int, lambda_h: float, mu_a: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1.0 - lambda_h * mu_a * rho
    elif x == 0 and y == 1:
        return 1.0 + lambda_h * rho
    elif x == 1 and y == 0:
        return 1.0 + mu_a * rho
    elif x == 1 and y == 1:
        return 1.0 - rho
    return 1.0

def build_score_matrix(lambda_h: float, mu_a: float, rho: float, max_goals: int = 8):
    matrix = {}
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            p_indep = poisson_pmf(x, lambda_h) * poisson_pmf(y, mu_a)
            t_adj = tau_factor(x, y, lambda_h, mu_a, rho)
            matrix[(x, y)] = max(0.0, p_indep * t_adj)
    total = sum(matrix.values())
    if total > 0:
        matrix = {k: v / total for k, v in matrix.items()}
    return matrix

def normalize_match_str(s: str) -> str:
    n = s.lower()
    for drop in [" fc", " ac", " as", "cf", "ssc ", "afc ", " "]:
        n = n.replace(drop, "")
    return n

def evaluate_sniper_markets(matrix, odds_dict):
    p_home = sum(prob for (x, y), prob in matrix.items() if x > y)
    p_draw = sum(prob for (x, y), prob in matrix.items() if x == y)
    p_away = sum(prob for (x, y), prob in matrix.items() if x < y)

    p_1x = p_home + p_draw
    p_x2 = p_away + p_draw

    p_over15 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 1.5)
    p_under35 = sum(prob for (x, y), prob in matrix.items() if (x + y) < 3.5)

    markets = [
        {"key": "1", "label": "Vittoria Casa (1)", "prob": p_home, "odd": odds_dict.get("1", 0.0)},
        {"key": "2", "label": "Vittoria Trasferta (2)", "prob": p_away, "odd": odds_dict.get("2", 0.0)},
        {"key": "1X", "label": "Doppia Chance 1X", "prob": p_1x, "odd": odds_dict.get("1X", 0.0)},
        {"key": "X2", "label": "Doppia Chance X2", "prob": p_x2, "odd": odds_dict.get("X2", 0.0)},
        {"key": "OVER_15", "label": "Over 1.5 Gol", "prob": p_over15, "odd": odds_dict.get("OVER_15", 0.0)},
        {"key": "UNDER_35", "label": "Under 3.5 Gol", "prob": p_under35, "odd": odds_dict.get("UNDER_35", 0.0)}
    ]

    valid = []
    for m in markets:
        if m["odd"] >= 1.40 and m["prob"] >= 0.80:
            edge = (m["prob"] * m["odd"]) - 1.0
            if edge > 0.01:
                m["edge"] = round(edge, 4)
                valid.append(m)
    return valid

def main():
    if not FIXTURES_FILE.exists():
        print("Palinsesto data/fixtures.json non trovato.")
        return

    data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])
    if not fixtures:
        print("Nessun match presente.")
        return

    safe_picks = []

    for item in fixtures:
        m_id = item.get("id")
        league_key = item.get("sport_key", "default")
        profile = LEAGUE_GOAL_PROFILES.get(league_key, LEAGUE_GOAL_PROFILES["default"])

        odds = item.get("odds", {})
        o1 = odds.get("1", 2.0)
        o2 = odds.get("2", 3.0)
        o_over25 = odds.get("OVER_25", 1.95)

        expected_total = profile["mu_home"] + profile["mu_away"]
        if o_over25 > 1.20:
            pace_factor = (1.95 / o_over25) ** 0.45
            expected_total *= pace_factor

        p_home_fair = 1.0 / max(1.05, o1)
        p_away_fair = 1.0 / max(1.05, o2)
        strength_sum = p_home_fair + p_away_fair

        share_h = p_home_fair / strength_sum if strength_sum > 0 else 0.55
        share_a = p_away_fair / strength_sum if strength_sum > 0 else 0.45

        lambda_h = expected_total * share_h
        mu_a = expected_total * share_a

        matrix = build_score_matrix(lambda_h, mu_a, profile["tau"])
        valid_markets = evaluate_sniper_markets(matrix, odds)

        for mkt in valid_markets:
            b = mkt["odd"] - 1.0
            p = mkt["prob"]
            raw_kelly = ((b * p) - (1.0 - p)) / b if b > 0 else 0.0
            stake = round(min(2.5, max(1.25, (raw_kelly * 0.25) * 100)), 2)

            safe_picks.append({
                "match_id": m_id,
                "match": f"{item.get('home_team')} vs {item.get('away_team')}",
                "commence_time": item.get("commence_time"),
                "league": item.get("league_name", league_key),
                "market_key": mkt["key"],
                "outcome_label": mkt["label"],
                "odd": round(mkt["odd"], 2),
                "estimated_probability": round(mkt["prob"], 4),
                "edge": mkt["edge"],
                "suggested_stake_pct": stake,
                "tier": "SNIPER 80+"
            })

    safe_picks.sort(key=lambda x: (x["estimated_probability"], x["edge"]), reverse=True)

    payload = {
        "engine": "Model C (Sniper Safe >= 80% @ >= 1.40)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_probability": "80%",
        "min_odd": 1.40,
        "total_officials": len(safe_picks),
        "all_selected_picks": safe_picks,
        "radar_watchlist": []
    }

    OUTPUT_SAFE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Model C Sniper] Analisi completata: trovate {len(safe_picks)} selezioni con Quota >= 1.40 e Prob >= 80%.")

    # Sincronizzazione Tracker Safe
    tracker_safe_data = {
        "total_bets": 0, "won": 0, "lost": 0, "void": 0,
        "win_rate": 0.0, "net_profit_units": 0.0, "roi_pct": 0.0, "bets": []
    }

    if TRACKER_SAFE_FILE.exists():
        try:
            loaded = json.loads(TRACKER_SAFE_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("bets"), list):
                tracker_safe_data = loaded
        except Exception:
            pass

    existing_pairs = set()
    for b in tracker_safe_data.get("bets", []):
        m_norm = normalize_match_str(b.get("match", ""))
        mkt = str(b.get("market_key", "")).strip().upper()
        existing_pairs.add((m_norm, mkt))

    new_added = 0
    for op in safe_picks:
        op_match_norm = normalize_match_str(op["match"])
        op_mkt = str(op["market_key"]).strip().upper()
        pair_key = (op_match_norm, op_mkt)

        if pair_key not in existing_pairs:
            bet_id = f"{op['match_id']}_{op['market_key']}"
            tracker_safe_data["bets"].append({
                "id": bet_id,
                "date": op["commence_time"],
                "match": op["match"],
                "league": op["league"],
                "bet": op["outcome_label"],
                "market_key": op["market_key"],
                "odd": op["odd"],
                "prob": op["estimated_probability"],
                "stake_pct": op["suggested_stake_pct"],
                "tier": op["tier"],
                "status": "PENDING",
                "profit": 0.0
            })
            existing_pairs.add(pair_key)
            new_added += 1

    tracker_safe_data["total_bets"] = len(tracker_safe_data["bets"])
    TRACKER_SAFE_FILE.write_text(json.dumps(tracker_safe_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Model C Sniper] Tracker sincronizzato: {new_added} nuove selezioni aggiunte.")

if __name__ == "__main__":
    main()
    
