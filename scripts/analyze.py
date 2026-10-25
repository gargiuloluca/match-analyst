"""
analyze.py — Quantitative Engine Multi-Campionato.
- Filtra quote con aggio eccessivo (> 8%).
- Analizza 1X2, Doppia Chance, Over/Under 2.5 e Goal/No Goal.
- Vincolo di quota: Minimo 1.40, Massimo 3.00.
- Seleziona i 3 pronostici con la massima probabilità assoluta di successo.
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

MIN_ODD = 1.40  # Soglia minima di quota richiesta
MAX_ODD = 3.00  # Evita azzardi a bassa percentuale


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

        # 1. Filtro di liquidità e affidabilità:
        # Calcolo della somma delle probabilità inverse (aggio).
        # Se supera 1.085 (8.5% di margine), la lavagna del bookmaker è troppo svantaggiosa.
        try:
            raw_sum = sum(1.0 / float(odds[k]) for k in ("home", "draw", "away") if float(odds[k]) > 1.0)
            if raw_sum > 1.085:
                continue
        except Exception:
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
            {"type": "1X", "label": f"1X ({home} o Pareggio)", "prob": probs["1X"], "odd": round(1.0 / (probs["1X"] * 1.04), 2)},
            {"type": "X2", "label": f"X2 ({away} o Pareggio)", "prob": probs["X2"], "odd": round(1.0 / (probs["X2"] * 1.04), 2)},
            {"type": "Over2.5", "label": "Over 2.5 Gol", "prob": probs["Over2.5"], "odd": round(1.0 / (probs["Over2.5"] * 1.05), 2)},
            {"type": "Under2.5", "label": "Under 2.5 Gol", "prob": probs["Under2.5"], "odd": round(1.0 / (probs["Under2.5"] * 1.05), 2)},
            {"type": "GG", "label": "Goal (Entrambe a segno)", "prob": probs["GG"], "odd": round(1.0 / (probs["GG"] * 1.05), 2)},
        ]

        for out in outcomes_spec:
            odd_val = out["odd"]
            prob_val = out["prob"]

            # Quota minima 1.40 e massima 3.00
            if odd_val < MIN_ODD or odd_val > MAX_ODD:
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
                "notes": f"Lega: {fx.get('league')} | Quota: {odd_val:.2f} | Prob: {int(prob_val*100)}%",
            })

    return candidates


def select_top_probability_picks(candidates: list) -> dict:
    """Seleziona i 3 pronostici con la più alta probabilità assoluta di successo."""
    picks = {}
    used_fixtures = set()

    # Ordina rigorosamente dal più probabile al meno probabile
    ranked = sorted(candidates, key=lambda c: c["estimated_probability"], reverse=True)

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


def main():
    if not FIXTURES_PATH.exists():
        print(f"File non trovato: {FIXTURES_PATH}")
        return

    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    candidates = build_candidates(fixtures)
    picks = select_top_probability_picks(candidates)

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
    print(f"Analisi completata su {len(fixtures)} partite. Selezionati i 3 esiti a probabilità più alta (quota >= 1.40).")


if __name__ == "__main__":
    main()
