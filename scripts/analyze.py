"""
analyze.py
Combina partite, quote e notizie.
Seleziona pronostici realistici:
- Conservativo: Quota bassa/alta probabilità (favorita solida)
- Consigliato: Quota bilanciata (1.60 - 2.20)
- Hard: Quota da valore/azzardo controllato (2.20 - 3.50)
"""

import json
from datetime import date
from pathlib import Path

TODAY = date.today().isoformat()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
HISTORY_DIR = DATA_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

FIXTURES_PATH = RAW_DIR / f"fixtures_{TODAY}.json"
NEWS_PATH = RAW_DIR / f"news_{TODAY}.json"


def implied_probabilities(odds: dict) -> dict:
    if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
        return {}
    try:
        raw = {k: 1 / float(odds[k]) for k in ("home", "draw", "away") if float(odds[k]) > 0}
        total = sum(raw.values())
        return {k: v / total for k, v in raw.items()}
    except Exception:
        return {}


def estimate_probabilities(fixture: dict, news_by_team: dict, implied: dict) -> dict:
    """Stima le probabilità ancorandosi al mercato reale e applicando

    bonus/malus basati su forma recente e notizie.
    """
    home_form = fixture.get("home_team", {}).get("form", {})
    away_form = fixture.get("away_team", {}).get("form", {})

    home_pts = home_form.get("points_last5", 5)
    away_pts = away_form.get("points_last5", 5)

    # Modificatori leggeri (-5% .. +5%) basati sulla forma
    form_diff = home_pts - away_pts
    home_mult = 1.0 + (form_diff * 0.01)
    away_mult = 1.0 - (form_diff * 0.01)

    home_name = fixture.get("home_team", {}).get("name", "")
    away_name = fixture.get("away_team", {}).get("name", "")
    home_news = news_by_team.get(home_name, {})
    away_news = news_by_team.get(away_name, {})

    if home_news.get("high_impact_count", 0) > 0:
        home_mult *= 0.96
    if away_news.get("high_impact_count", 0) > 0:
        away_mult *= 0.96

    est_home = implied["home"] * home_mult
    est_away = implied["away"] * away_mult
    est_draw = implied["draw"]

    total = est_home + est_draw + est_away
    return {
        "home": est_home / total,
        "draw": est_draw / total,
        "away": est_away / total,
    }


def build_candidates(fixtures: list, news_by_team: dict) -> list:
    candidates = []
    for fx in fixtures:
        odds = fx.get("odds")
        if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
            continue

        implied = implied_probabilities(odds)
        if not implied:
            continue

        estimated = estimate_probabilities(fx, news_by_team, implied)
        home_name = fx.get("home_team", {}).get("name", "Casa")
        away_name = fx.get("away_team", {}).get("name", "Trasferta")

        labels = {
            "home": f"Vittoria {home_name}",
            "draw": "Pareggio",
            "away": f"Vittoria {away_name}",
        }

        for outcome in ("home", "draw", "away"):
            edge = estimated[outcome] - implied[outcome]
            odd_val = float(odds[outcome])

            candidates.append(
                {
                    "fixture_id": fx.get("fixture_id", f"{home_name}-{away_name}"),
                    "league": fx.get("league", ""),
                    "match": f"{home_name} - {away_name}",
                    "date": fx.get("date", TODAY),
                    "outcome": outcome,
                    "outcome_label": labels[outcome],
                    "odd": odd_val,
                    "estimated_probability": round(estimated[outcome], 3),
                    "implied_probability": round(implied[outcome], 3),
                    "edge": round(edge, 3),
                    "notes": f"Quota: {odd_val:.2f} | Prob. Stimata: {int(estimated[outcome]*100)}%",
                }
            )
    return candidates


def select_three_picks(candidates: list) -> dict:
    used_fixtures = set()
    picks = {}

    if not candidates:
        return picks

    # 1. CONSERVATIVO: Probabilità più alta (la favorita più forte della giornata, quota tipica 1.20 - 1.65)
    conservativi = sorted(
        [c for c in candidates if 1.15 <= c["odd"] <= 1.70 and c["estimated_probability"] >= 0.55],
        key=lambda c: c["estimated_probability"],
        reverse=True,
    )
    if not conservativi:
        conservativi = sorted(candidates, key=lambda c: c["estimated_probability"], reverse=True)

    if conservativi:
        picks["conservativo"] = conservativi[0]
        used_fixtures.add(conservativi[0]["fixture_id"])

    # 2. CONSIGLIATO: Quota equilibrata (1.65 - 2.25) con edge positivo o miglior probabilità
    consigliati = sorted(
        [c for c in candidates if 1.65 <= c["odd"] <= 2.25 and c["fixture_id"] not in used_fixtures],
        key=lambda c: (c["edge"] > 0, c["estimated_probability"]),
        reverse=True,
    )
    if not consigliati:
        consigliati = [c for c in candidates if c["fixture_id"] not in used_fixtures]

    if consigliati:
        picks["consigliato"] = consigliati[0]
        used_fixtures.add(consigliati[0]["fixture_id"])

    # 3. HARD: Quota alta (2.30 - 3.60) sensata, evitando quote da lotteria (superiori a 4.00)
    hard = sorted(
        [c for c in candidates if 2.30 <= c["odd"] <= 3.80 and c["fixture_id"] not in used_fixtures],
        key=lambda c: (c["edge"] > 0, c["estimated_probability"]),
        reverse=True,
    )
    if hard:
        picks["hard"] = hard[0]
    else:
        # Fallback se non ci sono quote in quel range
        rimanenti = sorted([c for c in candidates if c["fixture_id"] not in used_fixtures], key=lambda c: c["odd"], reverse=True)
        if rimanenti:
            picks["hard"] = rimanenti[0]

    return picks


def main():
    if not FIXTURES_PATH.exists():
        raise SystemExit(f"File non trovato: {FIXTURES_PATH}")

    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    news_by_team = json.loads(NEWS_PATH.read_text(encoding="utf-8")) if NEWS_PATH.exists() else {}

    candidates = build_candidates(fixtures, news_by_team)
    picks = select_three_picks(candidates)

    output = {
        "date": TODAY,
        "generated_at": date.today().isoformat(),
        "total_fixtures_scanned": len(fixtures),
        "candidates_after_filter": len(candidates),
        "picks": picks,
        "all_candidates": sorted(candidates, key=lambda c: c["estimated_probability"], reverse=True)[:25],
    }

    (DATA_DIR / "latest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (HISTORY_DIR / f"{TODAY}.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completato: {len(candidates)} opzioni analizzate.")


if __name__ == "__main__":
    main()
