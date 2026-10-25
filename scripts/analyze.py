"""
analyze.py — AtmBetSignal (Win-Rate First Engine).
- Priorità assoluta: Massima probabilità di vittoria stimata.
- Vincolo di quota: Minimo 1.40, Massimo 3.00.
- Calcolo probabilità con Poisson e correzione Dixon-Coles per i pareggi.
- Estrae sempre i 3 eventi più probabili della giornata senza filtri restrittivi che bloccano il podio.
- Registra automaticamente le 3 Top Pick nel tracker come PENDING.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
HISTORY_DIR = DATA_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

FIXTURES_PATH = RAW_DIR / f"fixtures_{TODAY}.json"
TRACKER_PATH = DATA_DIR / "tracker.json"

DEFAULT_LAMBDA = 1.48
DEFAULT_MU = 1.12
RHO_CORRELATION = -0.11

MIN_ODD = 1.40
MAX_ODD = 3.00


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


def generate_dixon_coles_probabilities(fair_1x2: dict) -> dict:
    ratio = fair_1x2["home"] / max(0.01, fair_1x2["away"])
    lamb = max(0.65, min(2.70, DEFAULT_LAMBDA * math.sqrt(ratio)))
    mu = max(0.50, min(2.35, DEFAULT_MU / math.sqrt(ratio)))

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


def build_candidates(fixtures: list) -> list:
    candidates = []

    for fx in fixtures:
        odds = fx.get("odds")
        if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
            continue

        fair_1x2 = remove_margin(odds)
        if not fair_1x2:
            continue

        probs = generate_dixon_coles_probabilities(fair_1x2)
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

            # Quota minima 1.40 e massima 3.00
            if odd_val < MIN_ODD or odd_val > MAX_ODD:
                continue

            implied_prob = 1.0 / odd_val
            edge = prob_val - implied_prob

            candidates.append({
                "fixture_id": fx.get("fixture_id"),
                "league": fx.get("league", ""),
                "match": match_title,
                "date": TODAY,
                "market_type": out["type"],
                "outcome_label": out["label"],
                "odd": odd_val,
                "estimated_probability": round(prob_val, 4),
                "implied_probability": round(implied_prob, 4),
                "edge": round(edge, 4),
                "notes": f"Lega: {fx.get('league')} | Quota: {odd_val:.2f}",
            })

    return candidates


def select_top_probability_picks(candidates: list) -> dict:
    picks = {}
    used_fixtures = set()

    # PRIORITÀ ASSOLUTA: Probabilità stimata decrescente.
    # In caso di parità, premia chi ha l'Edge o la Quota migliore.
    ranked = sorted(
        candidates,
        key=lambda c: (c["estimated_probability"], c["edge"], c["odd"]),
        reverse=True
    )

    selected = []
    for c in ranked:
        if c["fixture_id"] not in used_fixtures:
            selected.append(c)
            used_fixtures.add(c["fixture_id"])
        if len(selected) == 3:
            break

    if len(selected) > 0:
        picks["conservativo"] = selected[0]
    if len(selected) > 1:
        picks["consigliato"] = selected[1]
    if len(selected) > 2:
        picks["hard"] = selected[2]

    return picks


def record_picks_to_tracker(picks: dict):
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

    for key in ("conservativo", "consigliato", "hard"):
        p = picks.get(key)
        if not p:
            continue

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
    picks = select_top_probability_picks(candidates)

    record_picks_to_tracker(picks)

    output = {
        "date": TODAY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures_scanned": len(fixtures),
        "candidates_after_filter": len(candidates),
        "picks": picks,
        "all_candidates": sorted(candidates, key=lambda c: c["estimated_probability"], reverse=True)[:40],
    }

    (DATA_DIR / "latest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (HISTORY_DIR / f"{TODAY}.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"AtmBetSignal: Selezionati i 3 eventi a più alta probabilità assoluta (quota >= {MIN_ODD}).")


if __name__ == "__main__":
    main()
