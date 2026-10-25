"""
analyze.py — Quantitative Engine ad Alta Probabilità (Quota Minima 1.40).
Filtra mercati 1X2, Doppia Chance, Over/Under 2.5 e Goal con Edge positivo.
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

DEFAULT_LAMBDA = 1.45
DEFAULT_MU = 1.15

MIN_ODD_ALLOWED = 1.40  # Soglia minima imposta dall'utente
MAX_ODD_ALLOWED = 3.20  # Soglia massima per evitare varianza estrema


def remove_margin(odds: dict) -> dict:
    try:
        inv = {k: 1.0 / float(odds[k]) for k in ("home", "draw", "away") if float(odds[k]) > 1.0}
        tot = sum(inv.values())
        return {k: inv[k] / tot for k in ("home", "draw", "away")}
    except Exception:
        return {}


def poisson(k: int, lamb: float) -> float:
    return (math.pow(lamb, k) * math.exp(-lamb)) / math.factorial(k)


def generate_market_probabilities(fair_1x2: dict) -> dict:
    ratio = fair_1x2["home"] / max(0.01, fair_1x2["away"])
    lamb = max(0.6, min(2.8, DEFAULT_LAMBDA * math.sqrt(ratio)))
    mu = max(0.5, min(2.4, DEFAULT_MU / math.sqrt(ratio)))

    p_matrix = {}
    for h in range(7):
        for a in range(7):
            p_matrix[(h, a)] = poisson(h, lamb) * poisson(a, mu)

    tot_mat = sum(p_matrix.values())
    p_matrix = {k: v / tot_mat for k, v in p_matrix.items()}

    prob_under25 = sum(prob for (h, a), prob in p_matrix.items() if (h + a) <= 2)
    prob_over25 = 1.0 - prob_under25

    prob_ng = sum(prob for (h, a), prob in p_matrix.items() if h == 0 or a == 0)
    prob_gg = 1.0 - prob_ng

    p_1 = fair_1x2["home"]
    p_x = fair_1x2["draw"]
    p_2 = fair_1x2["away"]

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

        probs = generate_market_probabilities(fair_1x2)
        home = fx.get("home_team", {}).get("name", "Casa")
        away = fx.get("away_team", {}).get("name", "Trasferta")
        match_title = f"{home} - {away}"

        outcomes_spec = [
            {"type": "1", "label": f"Vittoria {home}", "prob": probs["1"], "odd": float(odds["home"])},
            {"type": "2", "label": f"Vittoria {away}", "prob": probs["2"], "odd": float(odds["away"])},
            {"type": "1X", "label": f"1X (Doppia Chance {home})", "prob": probs["1X"], "odd": round(1.0 / (probs["1X"] * 1.04), 2)},
            {"type": "X2", "label": f"X2 (Doppia Chance {away})", "prob": probs["X2"], "odd": round(1.0 / (probs["X2"] * 1.04), 2)},
            {"type": "Over2.5", "label": "Over 2.5 Gol", "prob": probs["Over2.5"], "odd": round(1.0 / (probs["Over2.5"] * 1.05), 2)},
            {"type": "Under2.5", "label": "Under 2.5 Gol", "prob": probs["Under2.5"], "odd": round(1.0 / (probs["Under2.5"] * 1.05), 2)},
            {"type": "GG", "label": "Goal (Entrambe segnano)", "prob": probs["GG"], "odd": round(1.0 / (probs["GG"] * 1.05), 2)},
        ]

        for out in outcomes_spec:
            odd_val = out["odd"]
            prob_val = out["prob"]

            # Quota minima 1.40 e massima 3.20
            if odd_val < MIN_ODD_ALLOWED or odd_val > MAX_ODD_ALLOWED:
                continue

            # Calcolo Half-Kelly per lo stake consigliato
            b = odd_val - 1.0
            kelly = ((b * prob_val) - (1.0 - prob_val)) / b if b > 0 else 0
            stake_pct = max(0.0, round((kelly * 0.5) * 100, 1))

            candidates.append({
                "fixture_id": fx.get("fixture_id"),
                "league": fx.get("league", ""),
                "match": match_title,
                "date": TODAY,
                "market_type": out["type"],
                "outcome_label": out["label"],
                "odd": odd_val,
                "estimated_probability": round(prob_val, 3),
                "implied_probability": round(1.0 / odd_val, 3),
                "edge": round(prob_val - (1.0 / odd_val), 3),
                "stake_kelly": f"{stake_pct}%",
                "notes": f"Quota: {odd_val:.2f} | Prob: {int(prob_val*100)}% | Stake: {stake_pct}%",
            })

    return candidates


def select_best_picks(candidates: list) -> dict:
    picks = {}
    used_fixtures = set()

    if not candidates:
        return picks

    # 1. CONSERVATIVO: Alta probabilità reale (>= 65%), quota protetta compresa tra 1.40 e 1.65
    conservativi = sorted(
        [c for c in candidates if c["estimated_probability"] >= 0.65 and 1.40 <= c["odd"] <= 1.65],
        key=lambda c: c["estimated_probability"],
        reverse=True,
    )
    if conservativi:
        picks["conservativo"] = conservativi[0]
        used_fixtures.add(conservativi[0]["fixture_id"])

    # 2. CONSIGLIATO: Quota bilanciata (1.65 - 2.20) con probabilità stimata solida (>= 50%)
    consigliati = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures and 1.65 <= c["odd"] <= 2.20 and c["estimated_probability"] >= 0.50],
        key=lambda c: (c["edge"] > 0, c["estimated_probability"]),
        reverse=True,
    )
    if consigliati:
        picks["consigliato"] = consigliati[0]
        used_fixtures.add(consigliati[0]["fixture_id"])

    # 3. HARD: Quota controllata (2.20 - 3.20) ad alto valore
    hard = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures and 2.20 <= c["odd"] <= 3.20],
        key=lambda c: (c["edge"] > 0, c["estimated_probability"]),
        reverse=True,
    )
    if hard:
        picks["hard"] = hard[0]

    return picks


def main():
    if not FIXTURES_PATH.exists():
        print(f"File non trovato: {FIXTURES_PATH}")
        return

    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    candidates = build_candidates(fixtures)
    picks = select_best_picks(candidates)

    output = {
        "date": TODAY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures_scanned": len(fixtures),
        "candidates_after_filter": len(candidates),
        "picks": picks,
        "all_candidates": sorted(candidates, key=lambda c: c["estimated_probability"], reverse=True)[:35],
    }

    (DATA_DIR / "latest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (HISTORY_DIR / f"{TODAY}.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completato: {len(picks)} pronostici selezionati con quota >= 1.40.")


if __name__ == "__main__":
    main()
