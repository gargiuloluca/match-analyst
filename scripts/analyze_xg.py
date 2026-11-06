"""
analyze_xg.py — AtmBetSignal Experimental Engine (Model B: Independent Rolling xG & Performance Gap)
Motore parallelo di laboratorio quantitativo avanzato (Versione Specializzata sui Gol ad Alta Precisione).
- Stima dei parametri 100% indipendente dalle quote
- Filtri di élite innalzati (Probabilità minima >= 70%)
- Specializzazione esclusiva sui mercati Under/Over e BTTS (Zero sovrapposizioni con Motore A)
- Performance Gap ottimizzato specificamente sui flussi di reti attese
- Cap di esposizione portafoglio: max 1.25% singola giocata, max 2.5% cumulato di giornata
Salva i risultati in data/latest_xg.json e data/tracker_xg.json.
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"
LATEST_XG_FILE = DATA_DIR / "latest_xg.json"
TRACKER_XG_FILE = DATA_DIR / "tracker_xg.json"

HIGH_VARIANCE_DERBIES = [
    {"roma", "lazio"},
    {"sevilla", "real betis"},
    {"arsenal", "tottenham"},
    {"celtic", "rangers"},
    {"galatasaray", "fenerbahce"},
    {"inter", "milan"},
    {"juventus", "torino"},
    {"sporting", "benfica"},
    {"porto", "benfica"}
]

EUROPEAN_COMPETITORS = {
    "real madrid", "barcelona", "atletico madrid", "manchester city",
    "arsenal", "liverpool", "bayern munchen", "borussia dortmund",
    "inter", "juventus", "milan", "atalanta", "paris saint germain",
    "sporting", "benfica", "porto", "feyenoord", "psv"
}

LEAGUE_GOAL_PROFILES = {
    "soccer_italy_serie_a": {"mu_home": 1.45, "mu_away": 1.15, "tau": -0.06},
    "soccer_epl": {"mu_home": 1.55, "mu_away": 1.25, "tau": -0.04},
    "soccer_spain_la_liga": {"mu_home": 1.38, "mu_away": 1.05, "tau": -0.07},
    "soccer_germany_bundesliga": {"mu_home": 1.70, "mu_away": 1.35, "tau": -0.03},
    "soccer_france_ligue_one": {"mu_home": 1.38, "mu_away": 1.08, "tau": -0.08},
    "soccer_uefa_champs_league": {"mu_home": 1.60, "mu_away": 1.30, "tau": -0.04},
    "soccer_uefa_europa_league": {"mu_home": 1.55, "mu_away": 1.25, "tau": -0.04},
    "soccer_netherlands_eredivisie": {"mu_home": 1.75, "mu_away": 1.30, "tau": -0.02},
    "soccer_england_championship": {"mu_home": 1.40, "mu_away": 1.10, "tau": -0.07},
    "soccer_portugal_primeira_liga": {"mu_home": 1.48, "mu_away": 1.02, "tau": -0.07},
    "soccer_belgium_first_div": {"mu_home": 1.58, "mu_away": 1.28, "tau": -0.04},
    "soccer_england_league1": {"mu_home": 1.40, "mu_away": 1.15, "tau": -0.05},
    "soccer_england_efl_cup": {"mu_home": 1.50, "mu_away": 1.20, "tau": -0.04},
    "default": {"mu_home": 1.48, "mu_away": 1.18, "tau": -0.05}
}

TEAM_XG_DATABASE = {
    "inter": {"xg_for": 1.38, "xg_against": 0.72, "gap": +0.12},
    "juventus": {"xg_for": 1.20, "xg_against": 0.75, "gap": +0.05},
    "milan": {"xg_for": 1.28, "xg_against": 0.92, "gap": -0.08},
    "atalanta": {"xg_for": 1.42, "xg_against": 1.02, "gap": +0.15},
    "napoli": {"xg_for": 1.28, "xg_against": 0.80, "gap": +0.10},
    "roma": {"xg_for": 1.18, "xg_against": 0.90, "gap": -0.04},
    "lazio": {"xg_for": 1.14, "xg_against": 0.98, "gap": -0.02},
    "fiorentina": {"xg_for": 1.18, "xg_against": 0.95, "gap": +0.08},
    "bologna": {"xg_for": 1.12, "xg_against": 0.88, "gap": +0.06},
    "udinese": {"xg_for": 0.95, "xg_against": 1.15, "gap": -0.05},
    "parma": {"xg_for": 1.05, "xg_against": 1.22, "gap": +0.04},
    "genoa": {"xg_for": 0.88, "xg_against": 1.10, "gap": -0.02},
    "venezia": {"xg_for": 0.82, "xg_against": 1.32, "gap": -0.06},
    "cagliari": {"xg_for": 0.92, "xg_against": 1.28, "gap": -0.03},
    "lecce": {"xg_for": 0.86, "xg_against": 1.22, "gap": -0.08},
    "frosinone": {"xg_for": 0.92, "xg_against": 1.28, "gap": -0.04},
    "torino": {"xg_for": 0.94, "xg_against": 0.86, "gap": +0.02},
    "monza": {"xg_for": 0.84, "xg_against": 1.16, "gap": -0.07},
    
    "manchester city": {"xg_for": 1.48, "xg_against": 0.68, "gap": +0.15},
    "liverpool": {"xg_for": 1.44, "xg_against": 0.74, "gap": +0.10},
    "arsenal": {"xg_for": 1.40, "xg_against": 0.70, "gap": +0.12},
    "chelsea": {"xg_for": 1.28, "xg_against": 1.02, "gap": +0.05},
    "aston villa": {"xg_for": 1.25, "xg_against": 1.05, "gap": -0.04},
    "tottenham": {"xg_for": 1.30, "xg_against": 1.12, "gap": -0.02},
    "newcastle": {"xg_for": 1.20, "xg_against": 1.02, "gap": +0.06},
    "everton": {"xg_for": 0.96, "xg_against": 1.08, "gap": +0.08},
    "brentford": {"xg_for": 1.15, "xg_against": 1.18, "gap": +0.05},
    "brighton": {"xg_for": 1.24, "xg_against": 1.15, "gap": +0.14},

    "real madrid": {"xg_for": 1.46, "xg_against": 0.65, "gap": +0.12},
    "barcelona": {"xg_for": 1.50, "xg_against": 0.70, "gap": +0.18},
    "atletico madrid": {"xg_for": 1.26, "xg_against": 0.62, "gap": +0.04},
    "athletic club": {"xg_for": 1.18, "xg_against": 0.78, "gap": +0.09},
    "real sociedad": {"xg_for": 1.10, "xg_against": 0.80, "gap": +0.06},
    "villarreal": {"xg_for": 1.24, "xg_against": 1.12, "gap": +0.05},

    "psv": {"xg_for": 1.58, "xg_against": 0.60, "gap": +0.20},
    "feyenoord": {"xg_for": 1.40, "xg_against": 0.70, "gap": +0.10},
    "ajax": {"xg_for": 1.32, "xg_against": 0.85, "gap": +0.05},
    "sporting": {"xg_for": 1.50, "xg_against": 0.58, "gap": +0.18},
    "porto": {"xg_for": 1.40, "xg_against": 0.62, "gap": +0.12},
    "benfica": {"xg_for": 1.44, "xg_against": 0.62, "gap": +0.14},
    "paris saint germain": {"xg_for": 1.52, "xg_against": 0.65, "gap": +0.16},
    "bayern": {"xg_for": 1.60, "xg_against": 0.68, "gap": +0.22},
    "leverkusen": {"xg_for": 1.42, "xg_against": 0.76, "gap": +0.12},
    "dortmund": {"xg_for": 1.35, "xg_against": 1.02, "gap": +0.04},

    "default": {"xg_for": 1.00, "xg_against": 1.00, "gap": 0.00}
}

def get_team_xg_metrics(team_name: str):
    name_low = team_name.lower()
    for t_key, ratings in TEAM_XG_DATABASE.items():
        if t_key != "default" and t_key in name_low:
            xg_f = 0.85 * ratings["xg_for"] + 0.15 * 1.00
            xg_a = 0.85 * ratings["xg_against"] + 0.15 * 1.00
            return xg_f, xg_a, ratings.get("gap", 0.00)
    return 1.00, 1.00, 0.00

def is_high_variance_derby(home: str, away: str) -> bool:
    h, a = home.lower(), away.lower()
    for derby in HIGH_VARIANCE_DERBIES:
        if any(team in h for team in derby) and any(team in a for team in derby):
            return True
    return False

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

def shrink_edge(raw_edge: float) -> float:
    if raw_edge <= 0.05:
        return raw_edge * 0.90
    elif raw_edge <= 0.15:
        return raw_edge * 0.80
    else:
        return 0.12 + (raw_edge - 0.15) * 0.35

def calculate_adaptive_kelly(prob: float, odd: float, push_prob: float = 0.0) -> float:
    b = odd - 1.0
    if b <= 0.0 or prob <= 0.0:
        return 0.0
    loss_prob = max(0.0, 1.0 - prob - push_prob)
    f_star = (b * prob - loss_prob) / b
    if f_star <= 0.0:
        return 0.0
    
    stake = (f_star / 4.0) * 100.0
    if odd <= 1.60:
        max_stake = 1.25
    elif odd <= 1.85:
        max_stake = 1.00
    else:
        max_stake = 0.75
    return round(min(max_stake, max(0.40, stake)), 2)

def evaluate_markets(matrix, odds_dict):
    p_over15 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 1.5)
    p_under15 = 1.0 - p_over15
    p_over25 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 2.5)
    p_under25 = 1.0 - p_over25
    p_over35 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 3.5)
    p_under35 = 1.0 - p_over35

    p_btts_yes = sum(prob for (x, y), prob in matrix.items() if x > 0 and y > 0)
    p_btts_no = 1.0 - p_btts_yes

    # SPECIALIZZAZIONE ESCLUSIVA SUI MERCATI DEI GOL (UNDER/OVER E BTTS)
    markets = [
        {"key": "OVER_15", "label": "Over 1.5 Gol", "prob": p_over15, "push_prob": 0.0, "odd": odds_dict.get("OVER_15", 0.0)},
        {"key": "UNDER_15", "label": "Under 1.5 Gol", "prob": p_under15, "push_prob": 0.0, "odd": odds_dict.get("UNDER_15", 0.0)},
        {"key": "OVER_25", "label": "Over 2.5 Gol", "prob": p_over25, "push_prob": 0.0, "odd": odds_dict.get("OVER_25", 0.0)},
        {"key": "UNDER_25", "label": "Under 2.5 Gol", "prob": p_under25, "push_prob": 0.0, "odd": odds_dict.get("UNDER_25", 0.0)},
        {"key": "OVER_35", "label": "Over 3.5 Gol", "prob": p_over35, "push_prob": 0.0, "odd": odds_dict.get("OVER_35", 0.0)},
        {"key": "UNDER_35", "label": "Under 3.5 Gol", "prob": p_under35, "push_prob": 0.0, "odd": odds_dict.get("UNDER_35", 0.0)},
        {"key": "BTTS_YES", "label": "Entrambe Segnano (Gol)", "prob": p_btts_yes, "push_prob": 0.0, "odd": odds_dict.get("BTTS_YES", 0.0)},
        {"key": "BTTS_NO", "label": "NoGol", "prob": p_btts_no, "push_prob": 0.0, "odd": odds_dict.get("BTTS_NO", 0.0)},
    ]
    return [m for m in markets if m["odd"] and m["odd"] >= 1.40]

def normalize_match_str(s: str) -> str:
    n = s.lower()
    for drop in [" fc", " ac", " as", "cf", "ssc ", "afc ", " "]:
        n = n.replace(drop, "")
    return n

def main():
    if not FIXTURES_FILE.exists():
        print("Palinsesto non trovato per il Modello xG.")
        return

    fixtures_data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    matches = fixtures_data.get("fixtures", [])
    if not matches:
        return

    match_candidates = {}

    for item in matches:
        m_id = item.get("id")
        league_key = item.get("sport_key", item.get("league_key", "default"))
        profile = LEAGUE_GOAL_PROFILES.get(league_key, LEAGUE_GOAL_PROFILES["default"])
        
        home_team = item.get("home_team", "")
        away_team = item.get("away_team", "")
        odds = item.get("odds", {})
        open_odds = item.get("opening_odds", {})

        h_xg_f, h_xg_a, h_gap = get_team_xg_metrics(home_team)
        a_xg_f, a_xg_a, a_gap = get_team_xg_metrics(away_team)

        lambda_h = profile["mu_home"] * (h_xg_f * a_xg_a)
        mu_a = profile["mu_away"] * (a_xg_f * h_xg_a)
        rho = profile["tau"]

        h_low, a_low = home_team.lower(), away_team.lower()
        if any(team in h_low for team in EUROPEAN_COMPETITORS):
            lambda_h *= 0.93
        if any(team in a_low for team in EUROPEAN_COMPETITORS):
            mu_a *= 0.93

        matrix = build_score_matrix(lambda_h, mu_a, rho)
        evaluated = evaluate_markets(matrix, odds)

        is_derby = is_high_variance_derby(home_team, away_team)

        for ev in evaluated:
            prob = ev["prob"]
            odd = ev["odd"]
            m_key = ev["key"]
            raw_edge = (prob * odd) - 1.0
            
            edge = shrink_edge(raw_edge)
            ev_ratio = 1.0 + edge
            stake = calculate_adaptive_kelly(prob, odd, ev.get("push_prob", 0.0))

            op_odd = open_odds.get(m_key, odd)
            line_shift_pct = 0.0
            if op_odd > 0:
                line_shift_pct = round(((odd - op_odd) / op_odd) * 100, 1)

            tier = "STANDARD"
            is_official = False

            has_heavy_drift = line_shift_pct >= 2.5
            is_safe_fixture = not is_derby and not has_heavy_drift

            if prob >= 0.70 and 1.45 <= odd <= 2.80 and edge >= 0.04 and is_safe_fixture:
                is_official = True
                tier = "OFFICIAL"

                if prob >= 0.76 and odd >= 1.50 and edge >= 0.07:
                    tier = "GOLD"

                if (prob >= 0.72 and odd >= 1.70 and edge >= 0.10) or (edge >= 0.08 and line_shift_pct <= -2.0):
                    tier = "DIAMOND"

            # Performance Gap calibrato specificamente sui mercati di gol
            if m_key in ["OVER_15", "OVER_25", "OVER_35", "BTTS_YES"]:
                combined_gap = (h_xg_f + a_xg_f) - (h_xg_a + a_xg_a)
            else:
                combined_gap = max(0.0, 2.0 - (h_xg_a + a_xg_a))

            efficiency_score = (prob * 1.8) + (edge * 2.5) + (combined_gap * 0.8) - (max(0.0, line_shift_pct / 100.0) * 0.8)

            c_obj = {
                "match_id": m_id,
                "commence_time": item.get("commence_time"),
                "league": item.get("league_name", league_key),
                "home_team": home_team,
                "away_team": away_team,
                "match": f"{home_team} vs {away_team}",
                "market_key": m_key,
                "outcome_label": ev["label"],
                "odd": round(odd, 2),
                "line_shift_pct": line_shift_pct,
                "estimated_probability": round(prob, 4),
                "edge": round(edge, 4),
                "ev_ratio": round(ev_ratio, 3),
                "performance_gap": round(combined_gap, 2),
                "suggested_stake_pct": stake,
                "tier": tier,
                "efficiency_score": efficiency_score,
                "is_derby": is_derby,
                "is_official": is_official
            }

            if m_id not in match_candidates:
                match_candidates[m_id] = []
            match_candidates[m_id].append(c_obj)

    tier_weight = {"DIAMOND": 300, "GOLD": 200, "OFFICIAL": 100, "STANDARD": 0}
    diversified_picks = []

    for m_id, candidates_list in match_candidates.items():
        candidates_list.sort(
            key=lambda x: (tier_weight.get(x["tier"], 0) + x["efficiency_score"]), 
            reverse=True
        )
        diversified_picks.append(candidates_list[0])

    officials = [p for p in diversified_picks if p["is_official"]]
    officials.sort(
        key=lambda x: (tier_weight.get(x["tier"], 0), x["efficiency_score"]), 
        reverse=True
    )
    
    top_5_officials = officials[:5]

    total_exposure = sum(p["suggested_stake_pct"] for p in top_5_officials)
    if total_exposure > 2.5:
        scale_ratio = 2.5 / total_exposure
        for p in top_5_officials:
            p["suggested_stake_pct"] = round(p["suggested_stake_pct"] * scale_ratio, 2)

    official_match_ids = {p["match_id"] for p in top_5_officials}
    radar_pool = [
        p for p in diversified_picks 
        if p["match_id"] not in official_match_ids and p["estimated_probability"] >= 0.60
    ]
    radar_pool.sort(key=lambda x: x["estimated_probability"], reverse=True)
    top_10_radar = radar_pool[:10]

    output_payload = {
        "engine": "Model B (Dixon-Coles + Rolling xG Goals Specialist)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_officials": len(top_5_officials),
        "diamond_count": sum(1 for p in top_5_officials if p["tier"] == "DIAMOND"),
        "gold_count": sum(1 for p in top_5_officials if p["tier"] == "GOLD"),
        "all_selected_picks": top_5_officials,
        "radar_watchlist": top_10_radar
    }

    LATEST_XG_FILE.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Model xG] Analisi Conclusa (Goals Specialist): {len(top_5_officials)} selezioni generate in latest_xg.json.")

    tracker_xg_data = {
        "total_bets": 0, "won": 0, "lost": 0, "void": 0,
        "win_rate": 0.0, "net_profit_units": 0.0, "roi_pct": 0.0, "bets": []
    }
    
    if TRACKER_XG_FILE.exists():
        try:
            loaded = json.loads(TRACKER_XG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("bets"), list):
                tracker_xg_data = loaded
        except Exception:
            pass

    existing_pairs = set()
    for b in tracker_xg_data.get("bets", []):
        m_norm = normalize_match_str(b.get("match", ""))
        mkt = str(b.get("market_key", "")).strip().upper()
        existing_pairs.add((m_norm, mkt))

    new_added = 0
    for op in top_5_officials:
        op_match_norm = normalize_match_str(op["match"])
        op_mkt = str(op["market_key"]).strip().upper()
        pair_key = (op_match_norm, op_mkt)

        if pair_key not in existing_pairs:
            bet_id = f"{op['match_id']}_{op['market_key']}"
            tracker_xg_data["bets"].append({
                "id": bet_id,
                "event_id": op["match_id"],
                "date": op["commence_time"],
                "match": op["match"],
                "league": op["league"],
                "bet": op["outcome_label"],
                "market_key": op["market_key"],
                "odd": op["odd"],
                "prob": op["estimated_probability"],
                "edge": op["edge"],
                "performance_gap": op["performance_gap"],
                "stake_pct": op["suggested_stake_pct"],
                "tier": op["tier"],
                "status": "PENDING",
                "profit": 0.0
            })
            existing_pairs.add(pair_key)
            new_added += 1

    tracker_xg_data["total_bets"] = len(tracker_xg_data["bets"])
    TRACKER_XG_FILE.write_text(json.dumps(tracker_xg_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Model xG] Tracker sincronizzato: {new_added} nuove selezioni aggiunte.")

if __name__ == "__main__":
    main()
