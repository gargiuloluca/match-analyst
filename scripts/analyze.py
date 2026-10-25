"""
analyze.py — AtmBetSignal Dynamic Value Engine.
- Nessun freno artificiale: prende tutti gli eventi ad alta probabilità (>= 65%).
- Tetto massimo di sicurezza: fino a 7 pronostici al giorno (così non perdi i turni infrasettimanali da 5-6 eventi).
- Quota minima 1.40, massima 3.00.
- Modello Dixon-Coles con correzione per leghe e correlazione rho.
- Quarter-Kelly dinamico per il corretto dimensionamento del bankroll.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

NOW_UTC = datetime.now(timezone.utc)
TODAY = NOW_UTC.strftime("%Y-%m-%d")
WEEKDAY = NOW_UTC.weekday()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
HISTORY_DIR = DATA_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

FIXTURES_PATH = RAW_DIR / f"fixtures_{TODAY}.json"
TRACKER_PATH = DATA_DIR / "tracker.json"

# Parametri Qualitativi
MIN_PROBABILITY_THRESHOLD = 0.65  # Minimo 65% di probabilità stimata
MIN_ODD = 1.40
MAX_ODD = 3.00
MAX_KELLY_STAKE = 2.5

# TETTO MASSIMO DI SICUREZZA:
# Permette di prendere fino a 6-7 eventi se la giornata è ricca (es. Coppe o Weekend),
# ma evita di scommettere su 15 partite contemporaneamente.
MAX_DAILY_PICKS = 7

LEAGUE_GOAL_PROFILES = {
    "Serie A": (1.46, 1.14),
    "Premier League": (1.58, 1.28),
    "La Liga": (1.42, 1.08),
    "Bundesliga": (1.75, 1.42),
    "Ligue 1": (1.48, 1.18),
    "Champions League": (1.65, 1.35),
    "Europa League": (1.55, 1.28),
    "Conference League": (1.52, 1.25),
    "Serie B (Italia)": (1.28, 0.98),
    "Championship (Inghilterra)": (1.42, 1.15),
    "Segunda División (Spagna)": (1.22, 0.88),
    "2. Bundesliga (Germania)": (1.68, 1.38),
    "Eredivisie (Olanda)": (1.78, 1.40),
    "Primeira Liga (Portogallo)": (1.38, 1.05),
    "Jupiler Pro League (Belgio)": (1.58, 1.28),
    "Süper Lig (Turchia)": (1.52, 1.22),
    "Premiership (Scozia)": (1.45, 1.15),
    "Super League (Svizzera)": (1.62, 1.32),
    "Bundesliga (Austria)": (1.55, 1.25),
    "Brasileirão (Brasile)": (1.35, 0.98),
    "MLS (USA)": (1.60, 1.25),
}

DEFAULT_LAMBDA = 1.48
DEFAULT_MU = 1.12
RHO_CORRELATION = -0.11


def remove_margin(odds: dict) -> dict:
    try:
        inv = {k: 1.0 / float(odds[k]) for k in ("home", "draw", "away") if float(odds[k]) > 1.0}
        tot = sum(inv.values())
        return {k: inv[k] / tot for k in ("home", "draw", "away")}
    except Exception:
        return {}


def dixon_coles_tau(x: int, y: int, lamb: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1.0 - (lamb * mu * rho)
    elif x == 0 and y == 1:
        return 1.0 + (lamb * rho)
    elif x == 1 and y == 0:
        return 1.0 + (mu * rho)
    elif x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def poisson_prob(k: int, lamb: float) -> float:
    return (math.pow(lamb, k) * math.exp(-lamb)) / math.factorial(k)


def generate_dixon_coles_probabilities(fair_1x2: dict, league_name: str) -> dict:
    base_l, base_m = LEAGUE_GOAL_PROFILES.get(league_name, (DEFAULT_LAMBDA, DEFAULT_MU))
    ratio = fair_1x2["home"] / max(0.01, fair_1x2["away"])
    lamb = max(0.60, min(2.80, base_l * math.sqrt(ratio)))
    mu = max(0.45, min(2.40, base_m / math.sqrt(ratio)))

    p_matrix = {}
    for h in range(7):
        for a in range(7):
            tau = dixon_coles_tau(h, a, lamb, mu, RHO_CORRELATION)
            p_matrix[(h, a)] = tau * poisson_prob(h, lamb) * poisson_prob(a, mu)

    tot_mat = sum(p_matrix.values())
    p_matrix = {k: v / tot_mat for k, v in p_matrix.items()}

    prob_under25 = sum(prob for (h, a), prob in p_matrix.items() if (h + a) <= 2)
    prob_over25 = 1.0 - prob_under25

    prob_ng = sum(prob for (h, a), prob in p_matrix.items() if h == 0 or a == 0)
    prob_gg = 1.0 - prob_ng

    p_1 = sum(prob for (h, a), prob in p_matrix.items() if h > a)
    p_x = sum(prob for (h, a), prob in p_matrix.items() if h == a)
    p_2 = sum(prob for (h, a), prob in p_matrix.items() if a > h)

    return {
        "1": p_1,
        "X": p_x,
        "2": p_2,
        "1X": p_1 + p_x,
        "X2": p_x + p_2,
        "Over2.5": prob_over25,
        "Under2.5": prob_under25,
        "GG": prob_gg,
        "NG": prob_ng,
    }


def calculate_quarter_kelly(prob: float, odd: float) -> float:
    b = odd - 1.0
    if b <= 0:
        return 0.5
    raw_kelly = (b * prob - (1.0 - prob)) / b
    if raw_kelly <= 0:
        return 0.5
    quarter_kelly = (raw_kelly * 0.25) * 100
    return round(max(0.5, min(MAX_KELLY_STAKE, quarter_kelly)), 1)


def build_candidates(fixtures: list) -> list:
    candidates = []

    for fx in fixtures:
        odds = fx.get("odds")
        if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
            continue

        fair_1x2 = remove_margin(odds)
        if not fair_1x2:
            continue

        league = fx.get("league", "")
        probs = generate_dixon_coles_probabilities(fair_1x2, league)
        home = fx.get("home_team", {}).get("name", "Casa")
        away = fx.get("away_team", {}).get("name", "Trasferta")
        match_title = f"{home} - {away}"

        outcomes_spec = [
            {"type": "1", "label": f"Vittoria {home}", "prob": probs["1"], "odd": float(odds["home"])},
            {"type": "2", "label": f"Vittoria {away}", "prob": probs["2"], "odd": float(odds["away"])},
            {"type": "1X", "label": f"1X ({home} o Pareggio)", "prob": probs["1X"], "odd": round(1.0 / (probs["1X"] * 1.035), 2)},
            {"type": "X2", "label": f"X2 ({away} o Pareggio)", "prob": probs["X2"], "odd": round(1.0 / (probs["X2"] * 1.035), 2)},
            {"type": "Over2.5", "label": "Over 2.5 Gol", "prob": probs["Over2.5"], "odd": round(1.0 / (probs["Over2.5"] * 1.04), 2)},
            {"type": "Under2.5", "label": "Under 2.5 Gol", "prob": probs["Under2.5"], "odd": round(1.0 / (probs["Under2.5"] * 1.04), 2)},
            {"type": "GG", "label": "Goal (Entrambe a segno)", "prob": probs["GG"], "odd": round(1.0 / (probs["GG"] * 1.04), 2)},
        ]

        for out in outcomes_spec:
            odd_val = out["odd"]
            prob_val = out["prob"]

            if odd_val < MIN_ODD or odd_val > MAX_ODD:
                continue

            if prob_val < MIN_PROBABILITY_THRESHOLD:
                continue

            implied_prob = 1.0 / odd_val
            edge = prob_val - implied_prob
            stake_pct = calculate_quarter_kelly(prob_val, odd_val)

            candidates.append({
                "fixture_id": fx.get("fixture_id"),
                "league": league,
                "match": match_title,
                "date": TODAY,
                "market_type": out["type"],
                "outcome_label": out["label"],
                "odd": odd_val,
                "estimated_probability": round(prob_val, 4),
                "implied_probability": round(implied_prob, 4),
                "edge": round(edge, 4),
                "suggested_stake_pct": stake_pct,
                "notes": f"Lega: {league} | Quota: {odd_val:.2f} | Stake: {stake_pct}%",
            })

    return candidates


def select_dynamic_picks(candidates: list) -> list:
    used_fixtures = set()
    selected = []

    # Ordina per Massima Probabilità Assoluta Decrescente (e miglior Edge a parità)
    ranked = sorted(
        candidates,
        key=lambda c: (c["estimated_probability"], c["edge"], c["odd"]),
        reverse=True
    )

    for c in ranked:
        if c["fixture_id"] not in used_fixtures:
            selected.append(c)
            used_fixtures.add(c["fixture_id"])
        if len(selected) == MAX_DAILY_PICKS:
            break

    return selected


def record_picks_to_tracker(selected_picks: list):
    tracker_data = {
        "total_bets": 0, "won": 0, "lost": 0,
        "win_rate": 0.0, "net_profit_units": 0.0, "roi_pct": 0.0,
        "bets": []
    }

    if TRACKER_PATH.exists():
        try:
            tracker_data = json.loads(TRACKER_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_ids = {b.get("id") for b in tracker_data.get("bets", [])}

    for p in selected_picks:
        unique_id = f"{p['date']}_{p['fixture_id']}_{p['market_type']}"
        if unique_id not in existing_ids:
            tracker_data.setdefault("bets", []).append({
                "id": unique_id,
                "date": p["date"],
                "fixture_id": p["fixture_id"],
                "match": p["match"],
                "league": p.get("league", ""),
                "market_type": p["market_type"],
                "outcome_label": p["outcome_label"],
                "odd": float(p["odd"]),
                "estimated_prob": p.get("estimated_probability"),
                "suggested_stake_pct": p.get("suggested_stake_pct", 1.0),
                "status": "PENDING",
                "score": "-",
                "profit": 0.0
            })

    TRACKER_PATH.write_text(json.dumps(tracker_data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if not FIXTURES_PATH.exists():
        print(f"File non trovato: {FIXTURES_PATH}")
        return

    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    candidates = build_candidates(fixtures)
    picks = select_dynamic_picks(candidates)

    record_picks_to_tracker(picks)

    picks_dict = {}
    keys = ["conservativo", "consigliato", "hard"]
    for idx, p in enumerate(picks[:3]):
        picks_dict[keys[idx]] = p

    output = {
        "date": TODAY,
        "weekday": WEEKDAY,
        "max_allowed_today": MAX_DAILY_PICKS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures_scanned": len(fixtures),
        "candidates_above_65pct": len(candidates),
        "selected_picks_count": len(picks),
        "picks": picks_dict,
        "all_selected_picks": picks,
        "all_candidates": sorted(candidates, key=lambda c: c["estimated_probability"], reverse=True)[:30],
    }

    (DATA_DIR / "latest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (HISTORY_DIR / f"{TODAY}.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Dynamic Engine: {len(picks)} pronostici selezionati oggi con probabilità >= 65%.")


if __name__ == "__main__":
    main()
