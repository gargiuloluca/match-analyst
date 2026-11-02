"""
analyze_safe.py — AtmBetSignal High-Probability Sniper Engine (Model C: Safe80 Rigorous)
- Nessun compromesso di palinsesto: 0 selezioni forzate, le Top 5 sono un limite massimo
- Probabilità stimata: >= 74.0%
- Quota minima reale: >= 1.40
- Valore Atteso Minimo (EV): >= +3.0% (Eliminato il bug del 95% Fair Odd)
- Kelly Push-Adjusted specifico per mercati Draw No Bet (DNB)
- Cap rigoroso di portafoglio: max 1.5% a giocata, max 3.0% complessivo di giornata
- Filtro Smart Money anti-drift: scarta se quota sale oltre +2.5%
- Ranking composito: Probabilità + EV - Drift di mercato
Salva i risultati in data/latest_safe.json e data/tracker_safe.json.
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

def calculate_kelly_stake(prob: float, odd: float, push_prob: float = 0.0) -> float:
    """
    Calcola il Quarter-Kelly.
    Per i mercati DNB con rimborso, la formula tiene conto del push rate:
    f* = (p * b - (1 - p - push_prob)) / b
    """
    b = odd - 1.0
    if b <= 0.0 or prob <= 0.0:
        return 0.0

    loss_prob = max(0.0, 1.0 - prob - push_prob)
    raw_kelly = ((b * prob) - loss_prob) / b
    if raw_kelly <= 0.0:
        return 0.0

    # Quarter-Kelly (1/4 di frazione ottimale) con cap rigido a 1.5%
    stake = (raw_kelly * 0.25) * 100.0
    return round(min(1.50, max(0.50, stake)), 2)

def evaluate_sniper_markets(matrix, odds_dict, open_odds_dict):
    p_home = sum(prob for (x, y), prob in matrix.items() if x > y)
    p_draw = sum(prob for (x, y), prob in matrix.items() if x == y)
    p_away = sum(prob for (x, y), prob in matrix.items() if x < y)

    p_1x = p_home + p_draw
    p_x2 = p_away + p_draw

    decisive = p_home + p_away
    p_dnb_1 = (p_home / decisive) if decisive > 0 else 0.0
    p_dnb_2 = (p_away / decisive) if decisive > 0 else 0.0

    p_over15 = sum(prob for (x, y), prob in matrix.items() if (x + y) > 1.5)
    p_under35 = sum(prob for (x, y), prob in matrix.items() if (x + y) < 3.5)

    markets = [
        {"key": "1", "label": "Vittoria Casa (1)", "prob": p_home, "push_prob": 0.0, "odd": odds_dict.get("1", 0.0)},
        {"key": "2", "label": "Vittoria Trasferta (2)", "prob": p_away, "push_prob": 0.0, "odd": odds_dict.get("2", 0.0)},
        {"key": "1X", "label": "Doppia Chance 1X", "prob": p_1x, "push_prob": 0.0, "odd": odds_dict.get("1X", 0.0)},
        {"key": "X2", "label": "Doppia Chance X2", "prob": p_x2, "push_prob": 0.0, "odd": odds_dict.get("X2", 0.0)},
        {"key": "DNB_1", "label": "Casa Draw No Bet (Rimborso X)", "prob": p_dnb_1, "push_prob": p_draw, "odd": odds_dict.get("DNB_1", 0.0)},
        {"key": "DNB_2", "label": "Trasferta Draw No Bet (Rimborso X)", "prob": p_dnb_2, "push_prob": p_draw, "odd": odds_dict.get("DNB_2", 0.0)},
        {"key": "OVER_15", "label": "Over 1.5 Gol", "prob": p_over15, "push_prob": 0.0, "odd": odds_dict.get("OVER_15", 0.0)},
        {"key": "UNDER_35", "label": "Under 3.5 Gol", "prob": p_under35, "push_prob": 0.0, "odd": odds_dict.get("UNDER_35", 0.0)}
    ]

    valid = []
    for m in markets:
        # FILTRO DI FERRO: Quota >= 1.40 e Probabilità stimata >= 74.0%
        if m["odd"] >= 1.40 and m["prob"] >= 0.74:
            ev = (m["prob"] * m["odd"]) - 1.0

            # VINCOLO MATEMATICO RIGOROSO: Valore Atteso netto minimo del +3.0%
            if ev < 0.03:
                continue

            # FILTRO SMART MONEY STRINGENTE (Anti-drift <= +2.5%)
            op_odd = open_odds_dict.get(m["key"], m["odd"])
            line_shift_pct = round(((m["odd"] - op_odd) / op_odd) * 100, 1) if op_odd > 0 else 0.0
            if line_shift_pct > 2.5:
                continue

            # Score composito per ranking qualitativo: Probabilità + EV - Drift
            composite_score = (m["prob"] * 0.50) + (ev * 0.35) - (max(0.0, line_shift_pct / 100.0) * 0.15)

            m["ev"] = round(ev, 4)
            m["line_shift_pct"] = line_shift_pct
            m["composite_score"] = round(composite_score, 4)
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

    all_candidate_picks = []

    for item in fixtures:
        m_id = item.get("id")
        league_key = item.get("sport_key", "default")
        profile = LEAGUE_GOAL_PROFILES.get(league_key, LEAGUE_GOAL_PROFILES["default"])

        odds = item.get("odds", {})
        open_odds = item.get("opening_odds", odds)

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
        valid_markets = evaluate_sniper_markets(matrix, odds, open_odds)

        match_candidates = []
        for mkt in valid_markets:
            stake = calculate_kelly_stake(mkt["prob"], mkt["odd"], mkt.get("push_prob", 0.0))

            match_candidates.append({
                "match_id": m_id,
                "match": f"{item.get('home_team')} vs {item.get('away_team')}",
                "commence_time": item.get("commence_time"),
                "league": item.get("league_name", league_key),
                "market_key": mkt["key"],
                "outcome_label": mkt["label"],
                "odd": round(mkt["odd"], 2),
                "line_shift_pct": mkt["line_shift_pct"],
                "estimated_probability": round(mkt["prob"], 4),
                "ev": mkt["ev"],
                "edge": mkt["ev"],
                "composite_score": mkt["composite_score"],
                "suggested_stake_pct": stake,
                "tier": "SAFE 80+"
            })

        # DE-CORRELAZIONE RIGIDA: 1 sola selezione per incontro (la migliore per Composite Score)
        if match_candidates:
            match_candidates.sort(key=lambda x: x["composite_score"], reverse=True)
            all_candidate_picks.append(match_candidates[0])

    # Ordinamento complessivo basato su Composite Score
    all_candidate_picks.sort(key=lambda x: x["composite_score"], reverse=True)

    # CAP MASSIMO: Fino a un massimo di 5 selezioni (se presenti, altrimenti quelle effettivamente idonee)
    final_picks = all_candidate_picks[:5]

    # CONTROLLO CAP ESPOSIZIONE DI PORTAFOGLIO (Max 3.0% complessivo sul bankroll)
    total_exposure = sum(p["suggested_stake_pct"] for p in final_picks)
    if total_exposure > 3.0:
        scale_ratio = 3.0 / total_exposure
        for p in final_picks:
            p["suggested_stake_pct"] = round(p["suggested_stake_pct"] * scale_ratio, 2)

    payload = {
        "engine": "Model C (Safe80 Sniper EV >= +3% @ Quota >= 1.40)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_probability": "74%",
        "min_odd": 1.40,
        "min_ev": "+3.0%",
        "max_portfolio_exposure": "3.0%",
        "total_officials": len(final_picks),
        "all_selected_picks": final_picks,
        "radar_watchlist": []
    }

    OUTPUT_SAFE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Model C Safe80] Analisi completata: trovate {len(final_picks)} selezioni autenticamente a valore positivo.")

    # Sincronizzazione Tracker Safe80 con persistenza id e quote
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
    for op in final_picks:
        op_match_norm = normalize_match_str(op["match"])
        op_mkt = str(op["market_key"]).strip().upper()
        pair_key = (op_match_norm, op_mkt)

        if pair_key not in existing_pairs:
            bet_id = f"{op['match_id']}_{op['market_key']}"
            tracker_safe_data["bets"].append({
                "id": bet_id,
                "event_id": op["match_id"],
                "date": op["commence_time"],
                "match": op["match"],
                "league": op["league"],
                "bet": op["outcome_label"],
                "market_key": op["market_key"],
                "odd": op["odd"],
                "prob": op["estimated_probability"],
                "ev": op["ev"],
                "stake_pct": op["suggested_stake_pct"],
                "tier": op["tier"],
                "status": "PENDING",
                "profit": 0.0
            })
            existing_pairs.add(pair_key)
            new_added += 1

    tracker_safe_data["total_bets"] = len(tracker_safe_data["bets"])
    TRACKER_SAFE_FILE.write_text(json.dumps(tracker_safe_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Model C Safe80] Tracker sincronizzato: {new_added} nuove selezioni aggiunte.")

if __name__ == "__main__":
    main()
    
