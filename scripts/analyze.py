"""
analyze.py — AtmBetSignal Institutional Quantitative Analysis Engine (Model A: Independent Dixon-Coles Sniper Edition)
Versione Alta Precisione & Filtri Cecchino Blindati
- Stima dei parametri lambda e mu 100% indipendente dalle quote (Zero circolarità)
- Matrice bivariata Dixon-Coles con correzione tau per leghe tattiche
- Smorzamento Bayesiano dell'Edge e Quarter-Kelly Push-Adjusted
- Filtri di élite innalzati (Probabilità minima >= 74%, Edge >= 5.5%)
- Cap di esposizione portafoglio e de-correlazione assoluta per match
- Tracciamento nativo via event_id e persistenza sicura su data/latest.json e data/tracker.json
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURES_FILE = DATA_DIR / "fixtures.json"
LATEST_FILE = DATA_DIR / "latest.json"
TRACKER_FILE = DATA_DIR / "tracker.json"

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
    "sporting cp", "benfica", "porto", "feyenoord", "psv eindhoven"
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

TEAM_STRENGTH_RATINGS = {
    "inter": {"att_h": 1.32, "def_h": 0.72, "att_a": 1.25, "def_a": 0.78},
    "juventus": {"att_h": 1.20, "def_h": 0.70, "att_a": 1.10, "def_a": 0.78},
    "milan": {"att_h": 1.25, "def_h": 0.88, "att_a": 1.15, "def_a": 0.95},
    "atalanta": {"att_h": 1.35, "def_h": 0.95, "att_a": 1.28, "def_a": 1.05},
    "napoli": {"att_h": 1.26, "def_h": 0.78, "att_a": 1.16, "def_a": 0.85},
    "roma": {"att_h": 1.18, "def_h": 0.88, "att_a": 1.02, "def_a": 0.98},
    "lazio": {"att_h": 1.16, "def_h": 0.92, "att_a": 1.05, "def_a": 1.05},
    "fiorentina": {"att_h": 1.18, "def_h": 0.90, "att_a": 1.05, "def_a": 1.02},
    "bologna": {"att_h": 1.12, "def_h": 0.82, "att_a": 1.02, "def_a": 0.92},

    "manchester city": {"att_h": 1.45, "def_h": 0.65, "att_a": 1.35, "def_a": 0.75},
    "liverpool": {"att_h": 1.40, "def_h": 0.70, "att_a": 1.30, "def_a": 0.80},
    "arsenal": {"att_h": 1.38, "def_h": 0.68, "att_a": 1.28, "def_a": 0.72},
    "chelsea": {"att_h": 1.25, "def_h": 0.95, "att_a": 1.15, "def_a": 1.05},
    "aston villa": {"att_h": 1.28, "def_h": 0.90, "att_a": 1.12, "def_a": 1.10},
    "tottenham": {"att_h": 1.28, "def_h": 1.05, "att_a": 1.18, "def_a": 1.15},
    "newcastle": {"att_h": 1.25, "def_h": 0.90, "att_a": 1.05, "def_a": 1.12},

    "real madrid": {"att_h": 1.42, "def_h": 0.65, "att_a": 1.32, "def_a": 0.70},
    "barcelona": {"att_h": 1.45, "def_h": 0.70, "att_a": 1.35, "def_a": 0.75},
    "atletico madrid": {"att_h": 1.25, "def_h": 0.60, "att_a": 1.10, "def_a": 0.68},
    "athletic club": {"att_h": 1.18, "def_h": 0.75, "att_a": 1.02, "def_a": 0.85},
    "villarreal": {"att_h": 1.22, "def_h": 1.05, "att_a": 1.10, "def_a": 1.15},

    "bayern": {"att_h": 1.55, "def_h": 0.68, "att_a": 1.40, "def_a": 0.75},
    "leverkusen": {"att_h": 1.38, "def_h": 0.75, "att_a": 1.25, "def_a": 0.82},
    "paris saint germain": {"att_h": 1.48, "def_h": 0.65, "att_a": 1.35, "def_a": 0.70},
    "sporting": {"att_h": 1.45, "def_h": 0.58, "att_a": 1.32, "def_a": 0.65},
    "benfica": {"att_h": 1.40, "def_h": 0.62, "att_a": 1.28, "def_a": 0.68},
    "psv": {"att_h": 1.50, "def_h": 0.60, "att_a": 1.38, "def_a": 0.68},

    "default": {"att_h": 1.00, "def_h": 1.00, "att_a": 1.00, "def_a": 1.00}
}

def get_team_ratings(team_name: str, is_home: bool):
    name_low = team_name.lower()
    for t_key, r in TEAM_STRENGTH_RATINGS.items():
        if t_key != "default" and t_key in name_low:
            att = r["att_h"] if is_home else r["att_a"]
            defense = r["def_h"] if is_home else r["def_a"]
            return (0.85 * att + 0.15 * 1.00), (0.85 * defense + 0.15 * 1.00)
    return 1.00, 1.00

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
    p_home = sum(prob for (x, y), prob in matrix.items() if x > y)
    p_draw = sum(prob for (x, y), prob in matrix.items() if x == y)
    p_away = sum(prob for (x, y), prob in matrix.items() if x < y)

    p_1x = p_home + p_draw
    p_x2 = p_away + p_draw

    decisive = p_home + p_away
    p_dnb_1 = (p_home / decisive) if decisive > 0 else 0.0
    p_dnb_2 = (p_away / decisive) if decisive > 0 else 0.0

    p_over15 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 1.5)
    p_under15 = 1.0 - p_over15
    p_over25 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 2.5)
    p_under25 = 1.0 - p_over25
    p_over35 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 3.5)
    p_under35 = 1.0 - p_over35

    p_btts_yes = sum(prob for (x, y), prob in matrix.items() if x > 0 and y > 0)
    p_btts_no = 1.0 - p_btts_yes

    markets = [
        {"key": "1", "label": "Vittoria Casa (1)", "prob": p_home, "push_prob": 0.0, "odd": odds_dict.get("1", 0.0)},
        {"key": "X", "label": "Pareggio (X)", "prob": p_draw, "push_prob": 0.0, "odd": odds_dict.get("X", 0.0)},
        {"key": "2", "label": "Vittoria Trasferta (2)", "prob": p_away, "push_prob": 0.0, "odd": odds_dict.get("2", 0.0)},
        {"key": "1X", "label": "Doppia Chance 1X", "prob": p_1x, "push_prob": 0.0, "odd": odds_dict.get("1X", 0.0)},
        {"key": "X2", "label": "Doppia Chance X2", "prob": p_x2, "push_prob": 0.0, "odd": odds_dict.get("X2", 0.0)},
        {"key": "DNB_1", "label": "Casa Draw No Bet (Rimborso X)", "prob": p_dnb_1, "push_prob": p_draw, "odd": odds_dict.get("DNB_1", 0.0)},
        {"key": "DNB_2", "label": "Trasferta Draw No Bet (Rimborso X)", "prob": p_dnb_2, "push_prob": p_draw, "odd": odds_dict.get("DNB_2", 0.0)},
        {"key": "OVER_15", "label": "Over 1.5 Gol", "prob": p_over15, "push_prob": 0.0, "odd": odds_dict.get("OVER_15", 0.0)},
        {"key": "UNDER_15", "label": "Under 1.5 Gol", "prob": p_under15, "push_prob": 0.0, "odd": odds_dict.get("UNDER_15", 0.0)},
        {"key": "OVER_25", "label": "Over 2.5 Gol", "prob": p_over25, "push_prob": 0.0, "odd": odds_dict.get("OVER_25", 0.0)},
        {"key": "UNDER_25", "label": "Under 2.5 Gol", "prob": p_under25, "push_prob": 0.0, "odd": odds_dict.get("UNDER_25", 0.0)},
        {"key": "OVER_35", "label": "Over 3.5 Gol", "prob": p_over35, "push_prob": 0.0, "odd": odds_dict.get("OVER_35", 0.0)},
        {"key": "UNDER_35", "label": "Under 3.5 Gol", "prob": p_under35, "push_prob": 0.0, "odd": odds_dict.get("UNDER_35", 0.0)},
        {"key": "BTTS_YES", "label": "Entrambe Segnano (Gol)", "prob": p_btts_yes, "push_prob": 0.0, "odd": odds_dict.get("BTTS_YES", 0.0)},
        {"key": "BTTS_NO", "label": "NoGol", "prob": p_btts_no, "push_prob": 0.0, "odd": odds_dict.get("BTTS_NO", 0.0)},
    ]
    # SOGLIA QUOTA MINIMA ALZATA A 1.50 PER EVITARE VALIDI COMPRESSI
    return [m for m in markets if m["odd"] and m["odd"] >= 1.50]

def normalize_match_str(s: str) -> str:
    n = s.lower()
    for drop in [" fc", " ac", " as", "cf", "ssc ", "afc ", " "]:
        n = n.replace(drop, "")
    return n

def main():
    if not FIXTURES_FILE.exists():
        print("Nessun palinsesto trovato in fixtures.json.")
        return

    fixtures_data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    matches = fixtures_data.get("fixtures", [])
    if not matches:
        print("Nessun match disponibile.")
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

        att_h, def_h = get_team_ratings(home_team, is_home=True)
        att_a, def_a = get_team_ratings(away_team, is_home=False)

        lambda_h = profile["mu_home"] * att_h * def_a
        mu_a = profile["mu_away"] * att_a * def_h
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

            # Filtri Smart Money anti-drift severi
            has_heavy_drift = line_shift_pct >= 2.0
            is_safe_fixture = not is_derby and not has_heavy_drift

            # FILTRI CECCHINO D'ÉLITE (PROB >= 74%, EDGE >= 0.055)
            if prob >= 0.74 and 1.50 <= odd <= 2.70 and edge >= 0.055 and is_safe_fixture:
                is_official = True
                tier = "OFFICIAL"

                if prob >= 0.78 and odd >= 1.55 and edge >= 0.08:
                    tier = "GOLD"

                if (prob >= 0.74 and odd >= 1.75 and edge >= 0.11) or (edge >= 0.09 and line_shift_pct <= -2.0):
                    tier = "DIAMOND"

            efficiency_score = (prob * 1.8) + (edge * 2.5) - (max(0.0, line_shift_pct / 100.0) * 0.8)

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
    
    # Seleziona al massimo le migliori 3-5 occasioni di altissima qualità
    top_5_officials = officials[:5]

    total_exposure = sum(p["suggested_stake_pct"] for p in top_5_officials)
    if total_exposure > 2.5:
        scale_ratio = 2.5 / total_exposure
        for p in top_5_officials:
            p["suggested_stake_pct"] = round(p["suggested_stake_pct"] * scale_ratio, 2)

    official_match_ids = {p["match_id"] for p in top_5_officials}
    radar_pool = [
        p for p in diversified_picks 
        if p["match_id"] not in official_match_ids and p["estimated_probability"] >= 0.65
    ]
    radar_pool.sort(key=lambda x: x["estimated_probability"], reverse=True)
    top_10_radar = radar_pool[:10]

    latest_output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "Model A (Dixon-Coles Sniper High-Precision)",
        "total_officials": len(top_5_officials),
        "diamond_count": sum(1 for c in top_5_officials if c["tier"] == "DIAMOND"),
        "gold_count": sum(1 for c in top_5_officials if c["tier"] == "GOLD"),
        "all_selected_picks": top_5_officials,
        "radar_watchlist": top_10_radar
    }

    LATEST_FILE.write_text(json.dumps(latest_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Model A] Analisi conclusa (Sniper Edition): {len(top_5_officials)} selezioni di alta qualità generate.")

    tracker_data = {"bets": []}
    if TRACKER_FILE.exists():
        try:
            tracker_data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
            if not isinstance(tracker_data.get("bets"), list):
                tracker_data["bets"] = []
        except Exception as e:
            print(f"Avviso tracker.json: {e}")
            tracker_data = {"bets": []}

    existing_pairs = set()
    for b in tracker_data.get("bets", []):
        m_norm = normalize_match_str(b.get("match", ""))
        mkt = str(b.get("market_key", "")).strip().upper()
        existing_pairs.add((m_norm, mkt))

    added_count = 0
    for op in top_5_officials:
        op_match_norm = normalize_match_str(op["match"])
        op_mkt = str(op["market_key"]).strip().upper()
        pair_key = (op_match_norm, op_mkt)

        if pair_key not in existing_pairs:
            bet_id = f"{op['match_id']}_{op['market_key']}"
            tracker_data["bets"].append({
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
                "stake_pct": op["suggested_stake_pct"],
                "tier": op["tier"],
                "status": "PENDING",
                "profit": 0.0
            })
            existing_pairs.add(pair_key)
            added_count += 1

    TRACKER_FILE.write_text(json.dumps(tracker_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Model A] Tracker sincronizzato: {added_count} nuove selezioni aggiunte.")

if __name__ == "__main__":
    main()
    
