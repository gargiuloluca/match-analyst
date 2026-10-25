"""
analyze.py — Quantitative Value Engine multi-mercato.
Calcola 1X2, Doppia Chance (1X, X2), Over/Under 2.5 e Goal/No Goal (GG/NG)
tramite matrice di Poisson bivariata.
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

DEFAULT_LAMBDA = 1.45  # media gol casa
DEFAULT_MU = 1.15      # media gol trasferta


def remove_margin_1x2(odds: dict) -> dict:
    """De-margining delle quote 1X2."""
    try:
        inv = {k: 1.0 / float(odds[k]) for k in ("home", "draw", "away") if float(odds[k]) > 1.0}
        tot = sum(inv.values())
        return {k: inv[k] / tot for k in ("home", "draw", "away")}
    except Exception:
        return {}


def poisson(k: int, lamb: float) -> float:
    return (math.pow(lamb, k) * math.exp(-lamb)) / math.factorial(k)


def generate_market_probabilities(fair_1x2: dict) -> dict:
    """Calcola la matrice punteggi e ricava probabilità per 1X2, Doppia Chance,

    Over/Under 2.5 e Goal/No Goal.
    """
    # Stima dei parametri Poisson ancorati alle probabilità implicite de-margined
    ratio = fair_1x2["home"] / max(0.01, fair_1x2["away"])
    lamb = max(0.6, min(2.8, DEFAULT_LAMBDA * math.sqrt(ratio)))
    mu = max(0.5, min(2.4, DEFAULT_MU / math.sqrt(ratio)))

    # Matrice esiti fino a 6 gol per squadra
    p_matrix = {}
    for h in range(7):
        for a in range(7):
            p_matrix[(h, a)] = poisson(h, lamb) * poisson(a, mu)

    # Normalizzazione matrice
    tot_mat = sum(p_matrix.values())
    p_matrix = {k: v / tot_mat for k, v in p_matrix.items()}

    # Calcolo Over / Under 2.5
    prob_under25 = sum(prob for (h, a), prob in p_matrix.items() if (h + a) <= 2)
    prob_over25 = 1.0 - prob_under25

    # Calcolo Goal / No Goal
    prob_ng = sum(prob for (h, a), prob in p_matrix.items() if h == 0 or a == 0)
    prob_gg = 1.0 - prob_ng

    # Calcolo 1X2 e Doppia Chance
    p_1 = fair_1x2["home"]
    p_x = fair_1x2["draw"]
    p_2 = fair_1x2["away"]

    p_1x = p_1 + p_x
    p_x2 = p_x + p_2

    return {
        "1": p_1,
        "X": p_x,
        "2": p_2,
        "1X": p_1x,
        "X2": p_x2,
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

        fair_1x2 = remove_margin_1x2(odds)
        if not fair_1x2:
            continue

        probs = generate_market_probabilities(fair_1x2)
        home = fx.get("home_team", {}).get("name", "Casa")
        away = fx.get("away_team", {}).get("name", "Trasferta")
        match_title = f"{home} - {away}"

        # 1. Mercato 1X2 e Doppie Chance
        outcomes_spec = [
            {"type": "1", "label": f"Vittoria {home}", "prob": probs["1"], "odd": float(odds["home"])},
            {"type": "2", "label": f"Vittoria {away}", "prob": probs["2"], "odd": float(odds["away"])},
            {"type": "1X", "label": f"1X (Doppia Chance {home})", "prob": probs["1X"], "odd": round(1.0 / (probs["1X"] * 1.05), 2)},
            {"type": "X2", "label": f"X2 (Doppia Chance {away})", "prob": probs["X2"], "odd": round(1.0 / (probs["X2"] * 1.05), 2)},
            {"type": "Over2.5", "label": "Over 2.5 Gol", "prob": probs["Over2.5"], "odd": round(1.0 / (probs["Over2.5"] * 1.06), 2)},
            {"type": "Under2.5", "label": "Under 2.5 Gol", "prob": probs["Under2.5"], "odd": round(1.0 / (probs["Under2.5"] * 1.06), 2)},
            {"type": "GG", "label": "Goal (Entrambe segnano)", "prob": probs["GG"], "odd": round(1.0 / (probs["GG"] * 1.06), 2)},
        ]

        for out in outcomes_spec:
            odd_val = out["odd"]
            prob_val = out["prob"]

            # Filtri di sicurezza e quota
            if odd_val < 1.18 or odd_val > 3.60:
                continue

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
                "notes": f"Mercato: {out['type']} | Quota: {odd_val:.2f} | Prob: {int(prob_val*100)}%",
            })

    return candidates


def select_best_picks(candidates: list) -> dict:
    picks = {}
    used_fixtures = set()

    if not candidates:
        return picks

    # 1. CONSERVATIVO: Alta affidabilità (probabilità >= 70%, ottima per 1X o Over 1.5/Doppia Chance)
    conservativi = sorted(
        [c for c in candidates if c["estimated_probability"] >= 0.68 and 1.22 <= c["odd"] <= 1.55],
        key=lambda c: c["estimated_probability"],
        reverse=True,
    )
    if conservativi:
        picks["conservativo"] = conservativi[0]
        used_fixtures.add(conservativi[0]["fixture_id"])

    # 2. CONSIGLIATO: Quota bilanciata (1.60 - 2.15) con solidità statistica (es. Goal, 1 secco o Over 2.5)
    consigliati = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures and 1.60 <= c["odd"] <= 2.15],
        key=lambda c: (c["estimated_probability"] >= 0.52, c["estimated_probability"]),
        reverse=True,
    )
    if consigliati:
        picks["consigliato"] = consigliati[0]
        used_fixtures.add(consigliati[0]["fixture_id"])

    # 3. HARD: Quota alta controllata (2.20 - 3.40)
    hard = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures and 2.20 <= c["odd"] <= 3.40],
        key=lambda c: c["estimated_probability"],
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
    print(f"Analisi multi-mercato completata: {len(candidates)} opzioni analizzate.")


if __name__ == "__main__":
    main()
