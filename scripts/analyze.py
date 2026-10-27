"""
analyze.py — AtmBetSignal Institutional Quantitative Analysis Engine
- Matrice bivariata Dixon-Coles con correzione tau
- Valutazione completa mercati: 1X2, DC (1X/X2), DNB, Over/Under (1.5/2.5/3.5), BTTS
- Quarter-Kelly Money Management (Cap 2.5%)
- Segmentazione: DIAMOND (Max Edge), GOLD (Super Affidabilità >= 72%), OFFICIAL (>= 65%), RADAR
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"
LATEST_FILE = DATA_DIR / "latest.json"
TRACKER_FILE = DATA_DIR / "tracker.json"

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
            prob = max(0.0, p_indep * t_adj)
            matrix[(x, y)] = prob
    total = sum(matrix.values())
    if total > 0:
        matrix = {k: v / total for k, v in matrix.items()}
    return matrix

def calculate_quarter_kelly(prob: float, odd: float) -> float:
    b = odd - 1.0
    if b <= 0 or prob <= 0:
        return 0.0
    q = 1.0 - prob
    f_star = (b * prob - q) / b
    if f_star <= 0:
        return 0.0
    quarter = f_star / 4.0
    stake_pct = min(0.025, quarter) * 100
    return round(stake_pct, 2)

def evaluate_markets(matrix, odds_dict):
    p_home = sum(prob for (x, y), prob in matrix.items() if x > y)
    p_draw = sum(prob for (x, y), prob in matrix.items() if x == y)
    p_away = sum(prob for (x, y), prob in matrix.items() if x < y)

    # Doppie Chance
    p_1x = p_home + p_draw
    p_x2 = p_away + p_draw

    # Draw No Bet (Probabilità condizionata)
    decisive = p_home + p_away
    p_dnb_1 = (p_home / decisive) if decisive > 0 else 0.0
    p_dnb_2 = (p_away / decisive) if decisive > 0 else 0.0

    # Linee Totali Gol
    p_over15 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 1.5)
    p_under15 = 1.0 - p_over15
    p_over25 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 2.5)
    p_under25 = 1.0 - p_over25
    p_over35 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 3.5)
    p_under35 = 1.0 - p_over35

    # Goal / NoGoal
    p_btts_yes = sum(prob for (x, y), prob in matrix.items() if x > 0 and y > 0)
    p_btts_no = 1.0 - p_btts_yes

    markets = [
        {"key": "1", "label": "Vittoria Casa (1)", "prob": p_home, "odd": odds_dict.get("1", 0.0)},
        {"key": "X", "label": "Pareggio (X)", "prob": p_draw, "odd": odds_dict.get("X", 0.0)},
        {"key": "2", "label": "Vittoria Trasferta (2)", "prob": p_away, "odd": odds_dict.get("2", 0.0)},
        {"key": "1X", "label": "Doppia Chance 1X", "prob": p_1x, "odd": odds_dict.get("1X", 0.0)},
        {"key": "X2", "label": "Doppia Chance X2", "prob": p_x2, "odd": odds_dict.get("X2", 0.0)},
        {"key": "DNB_1", "label": "Casa Draw No Bet (Rimborso Parità)", "prob": p_dnb_1, "odd": odds_dict.get("DNB_1", 0.0)},
        {"key": "DNB_2", "label": "Trasferta Draw No Bet (Rimborso Parità)", "prob": p_dnb_2, "odd": odds_dict.get("DNB_2", 0.0)},
        {"key": "OVER_15", "label": "Over 1.5 Gol", "prob": p_over15, "odd": odds_dict.get("OVER_15", 0.0)},
        {"key": "UNDER_15", "label": "Under 1.5 Gol", "prob": p_under15, "odd": odds_dict.get("UNDER_15", 0.0)},
        {"key": "OVER_25", "label": "Over 2.5 Gol", "prob": p_over25, "odd": odds_dict.get("OVER_25", 0.0)},
        {"key": "UNDER_25", "label": "Under 2.5 Gol", "prob": p_under25, "odd": odds_dict.get("UNDER_25", 0.0)},
        {"key": "OVER_35", "label": "Over 3.5 Gol", "prob": p_over35, "odd": odds_dict.get("OVER_35", 0.0)},
        {"key": "UNDER_35", "label": "Under 3.5 Gol", "prob": p_under35, "odd": odds_dict.get("UNDER_35", 0.0)},
        {"key": "BTTS_YES", "label": "Entrambe Segnano (Gol)", "prob": p_btts_yes, "odd": odds_dict.get("BTTS_YES", 0.0)},
        {"key": "BTTS_NO", "label": "NoGol", "prob": p_btts_no, "odd": odds_dict.get("BTTS_NO", 0.0)},
    ]
    return [m for m in markets if m["odd"] and m["odd"] >= 1.30]

def main():
    if not FIXTURES_FILE.exists():
        print("Nessun palinsesto trovato in fixtures.json.")
        return

    fixtures_data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    matches = fixtures_data.get("fixtures", [])
    if not matches:
        print("Nessun match disponibile.")
        return

    candidates = []

    for item in matches:
        league_key = item.get("sport_key", item.get("league_key", "default"))
        profile = LEAGUE_GOAL_PROFILES.get(league_key, LEAGUE_GOAL_PROFILES["default"])
        
        home_team = item.get("home_team", "")
        away_team = item.get("away_team", "")
        odds = item.get("odds", {})

        o1 = odds.get("1", 2.0)
        o2 = odds.get("2", 3.0)
        ratio = (o2 / max(1.05, o1)) ** 0.35
        
        lambda_h = profile["mu_home"] * ratio
        mu_a = profile["mu_away"] / ratio
        rho = profile["tau"]

        matrix = build_score_matrix(lambda_h, mu_a, rho)
        evaluated = evaluate_markets(matrix, odds)

        for ev in evaluated:
            prob = ev["prob"]
            odd = ev["odd"]
            edge = (prob * odd) - 1.0
            ev_ratio = prob * odd
            stake = calculate_quarter_kelly(prob, odd)

            tier = "STANDARD"
            is_official = False

            # Criterio Ufficiale Base: Probabilità >= 65% e Quota 1.40 - 3.00
            if prob >= 0.65 and 1.40 <= odd <= 3.00 and edge > 0:
                is_official = True
                tier = "OFFICIAL"

                # Super-Filtro GOLD (Affidabilità >= 72% e quota >= 1.45)
                if prob >= 0.72 and odd >= 1.45 and edge >= 0.08:
                    tier = "GOLD"

                # Super-Filtro DIAMOND (Edge Istituzionale >= +12% e quota >= 1.75)
                if prob >= 0.65 and odd >= 1.75 and edge >= 0.12 and ev_ratio >= 1.15:
                    tier = "DIAMOND"

            candidates.append({
                "match_id": item.get("id"),
                "commence_time": item.get("commence_time"),
                "league": item.get("league_name", league_key),
                "home_team": home_team,
                "away_team": away_team,
                "match": f"{home_team} vs {away_team}",
                "market_key": ev["key"],
                "outcome_label": ev["label"],
                "odd": round(odd, 2),
                "estimated_probability": round(prob, 4),
                "edge": round(edge, 4),
                "ev_ratio": round(ev_ratio, 3),
                "suggested_stake_pct": stake,
                "tier": tier,
                "is_official": is_official
            })

    tier_order = {"DIAMOND": 3, "GOLD": 2, "OFFICIAL": 1, "STANDARD": 0}
    unique_candidates = {}
    for c in sorted(candidates, key=lambda x: (tier_order.get(x["tier"], 0), x["edge"]), reverse=True):
        m_id = c["match_id"]
        if m_id not in unique_candidates:
            unique_candidates[m_id] = c

    all_sorted = list(unique_candidates.values())

    # Top 5 Ufficiali
    official_pool = [c for c in all_sorted if c["is_official"]]
    official_pool.sort(key=lambda x: (tier_order.get(x["tier"], 0), x["estimated_probability"]), reverse=True)
    top_5_officials = official_pool[:5]

    # Watchlist Radar (Top 10 tra 55% e 64.9%)
    official_ids = {c["match_id"] for c in top_5_officials}
    radar_pool = [c for c in all_sorted if c["match_id"] not in official_ids and c["estimated_probability"] >= 0.55]
    radar_pool.sort(key=lambda x: x["estimated_probability"], reverse=True)
    top_10_radar = radar_pool[:10]

    latest_output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_officials": len(top_5_officials),
        "diamond_count": sum(1 for c in top_5_officials if c["tier"] == "DIAMOND"),
        "gold_count": sum(1 for c in top_5_officials if c["tier"] == "GOLD"),
        "all_selected_picks": top_5_officials,
        "radar_watchlist": top_10_radar
    }

    LATEST_FILE.write_text(json.dumps(latest_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Analisi conclusa: {len(top_5_officials)} Ufficiali ({latest_output['diamond_count']} Diamond, {latest_output['gold_count']} Gold) e {len(top_10_radar)} Radar.")

    # Sincronizzazione con tracker.json
    if TRACKER_FILE.exists():
        tracker_data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
    else:
        tracker_data = {"bets": []}

    existing_ids = {b.get("id") for b in tracker_data.get("bets", [])}
    for op in top_5_officials:
        bet_id = f"{op['match_id']}_{op['market_key']}"
        if bet_id not in existing_ids:
            tracker_data["bets"].append({
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

    TRACKER_FILE.write_text(json.dumps(tracker_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Tracker sincronizzato.")

if __name__ == "__main__":
    main()
