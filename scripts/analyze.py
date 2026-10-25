"""
analyze.py
Motore quantitativo di selezione segnali a valore reale (Value Betting).
Scarta quote da lotteria (>3.80) e seleziona i segnali a maggior solidità statistica.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
HISTORY_DIR = DATA_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

FIXTURES_PATH = RAW_DIR / f"fixtures_{TODAY}.json"


def remove_margin(odds: dict) -> dict:
    """Calcola le probabilità reali del mercato eliminando l'aggio del bookmaker."""
    try:
        inv = {k: 1.0 / float(odds[k]) for k in ("home", "draw", "away") if float(odds[k]) > 1.0}
        total = sum(inv.values())
        return {k: inv[k] / total for k in ("home", "draw", "away")}
    except Exception:
        return {}


def build_signals(fixtures: list) -> list:
    signals = []

    for fx in fixtures:
        odds = fx.get("odds")
        if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
            continue

        fair_probs = remove_margin(odds)
        if not fair_probs:
            continue

        home_name = fx.get("home_team", {}).get("name", "Casa")
        away_name = fx.get("away_team", {}).get("name", "Trasferta")

        labels = {
            "home": f"Vittoria {home_name}",
            "draw": "Pareggio",
            "away": f"Vittoria {away_name}",
        }

        # Bonus campo standard: il mercato tende a sottostimare leggermente il fattore campo sulle favorite
        model_probs = {
            "home": fair_probs["home"] * 1.025,
            "draw": fair_probs["draw"] * 0.98,
            "away": fair_probs["away"] * 0.99,
        }
        tot = sum(model_probs.values())
        model_probs = {k: v / tot for k, v in model_probs.items()}

        for outcome in ("home", "draw", "away"):
            odd_val = float(odds[outcome])

            # Scarta quote da lotteria: sopra quota 3.80 il rischio matematico è eccessivo
            if odd_val > 3.80 or odd_val < 1.15:
                continue

            est_p = model_probs[outcome]
            mkt_p = fair_probs[outcome]
            edge = est_p - mkt_p

            signals.append({
                "fixture_id": fx.get("fixture_id"),
                "league": fx.get("league", ""),
                "match": f"{home_name} - {away_name}",
                "date": TODAY,
                "outcome": outcome,
                "outcome_label": labels[outcome],
                "odd": odd_val,
                "estimated_probability": round(est_p, 3),
                "implied_probability": round(mkt_p, 3),
                "edge": round(edge, 3),
                "notes": f"Quota: {odd_val:.2f} | Probabilità Reale: {int(est_p*100)}%",
            })

    return signals


def pick_top_signals(candidates: list) -> dict:
    picks = {}
    used_fixtures = set()

    if not candidates:
        return picks

    # 1. CONSERVATIVO: Massima probabilità di riuscita (quota 1.25 - 1.65, prob >= 58%)
    conservativi = sorted(
        [c for c in candidates if 1.20 <= c["odd"] <= 1.65 and c["estimated_probability"] >= 0.58],
        key=lambda c: c["estimated_probability"],
        reverse=True,
    )
    if conservativi:
        picks["conservativo"] = conservativi[0]
        used_fixtures.add(conservativi[0]["fixture_id"])

    # 2. CONSIGLIATO: Quota bilanciata ideale (1.65 - 2.25) con il miglior rapporto probabilità/quota
    consigliati = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures and 1.65 <= c["odd"] <= 2.25],
        key=lambda c: (c["edge"] > 0, c["estimated_probability"]),
        reverse=True,
    )
    if consigliati:
        picks["consigliato"] = consigliati[0]
        used_fixtures.add(consigliati[0]["fixture_id"])

    # 3. HARD: Quota alta controllata (2.30 - 3.50) con solidità statistica
    hard = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures and 2.30 <= c["odd"] <= 3.50],
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
    candidates = build_signals(fixtures)
    picks = pick_top_signals(candidates)

    output = {
        "date": TODAY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures_scanned": len(fixtures),
        "candidates_after_filter": len(candidates),
        "picks": picks,
        "all_candidates": sorted(candidates, key=lambda c: c["estimated_probability"], reverse=True)[:25],
    }

    (DATA_DIR / "latest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (HISTORY_DIR / f"{TODAY}.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Analisi completata: {len(fixtures)} match odierni, {len(picks)} pronostici selezionati.")


if __name__ == "__main__":
    main()
