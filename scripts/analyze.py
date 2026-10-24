"""
analyze.py

Combina partite+quote (fetch_fixtures.py) e notizie extra-campo
(fetch_news.py), applica un filtro di qualita' dei dati, stima le
probabilita' di ogni esito e produce 3 pronostici: conservativo, consigliato, hard.
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

# ---------------------------------------------------------------------------
# Parametri del filtro e del modello (ottimizzati per evitare zero risultati)
# ---------------------------------------------------------------------------

MIN_MATCHES_FOR_FORM = 1          # Almeno 1 partita analizzata per non escludere squadre a inizio stagione
MAX_HIGH_IMPACT_NEWS = 3          # Alzato da 1 a 3: non scarta la partita per normali notizie di formazione
MIN_EDGE_FOR_PICK = 0.01          # Edge minimo al +1.0% (invece di +3.0% che bloccava quasi tutto)


def implied_probabilities(odds: dict) -> dict:
    """Converte le quote 1X2 in probabilita' implicite normalizzate."""
    if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
        return {}
    try:
        raw = {k: 1 / float(odds[k]) for k in ("home", "draw", "away") if float(odds[k]) > 0}
        if len(raw) < 3:
            return {}
        total = sum(raw.values())
        return {k: v / total for k, v in raw.items()}
    except (ZeroDivisionError, ValueError, TypeError):
        return {}


def estimate_probabilities(fixture: dict, news_by_team: dict) -> dict:
    """Stima P(1)/P(X)/P(2) da forma recente, differenza reti e fattore campo."""
    home_form = fixture.get("home_team", {}).get("form", {})
    away_form = fixture.get("away_team", {}).get("form", {})

    home_pts = home_form.get("points_last5", 5)
    home_gd = home_form.get("goal_diff_last5", 0)
    away_pts = away_form.get("points_last5", 5)
    away_gd = away_form.get("goal_diff_last5", 0)

    # Vantaggio campo e forza relativa
    home_strength = home_pts + 0.5 * home_gd + 2.0
    away_strength = away_pts + 0.5 * away_gd

    total = home_strength + away_strength
    if total <= 0:
        base_home, base_away = 0.40, 0.35
    else:
        base_home = 0.75 * (home_strength / total)
        base_away = 0.75 * (away_strength / total)

    base_draw = max(0.15, 1.0 - base_home - base_away)
    probs = {"home": base_home, "draw": base_draw, "away": base_away}

    # Penalità per notizie rilevanti
    home_name = fixture.get("home_team", {}).get("name", "")
    away_name = fixture.get("away_team", {}).get("name", "")
    home_news = news_by_team.get(home_name, {})
    away_news = news_by_team.get(away_name, {})

    if home_news.get("high_impact_count", 0) > 0:
        probs["home"] *= 0.88
    if away_news.get("high_impact_count", 0) > 0:
        probs["away"] *= 0.88

    total_p = sum(probs.values())
    return {k: v / total_p for k, v in probs.items()}


def data_quality_ok(fixture: dict, news_by_team: dict) -> bool:
    """Verifica presenza quote, storico minimo e soglia notizie."""
    odds = fixture.get("odds")
    if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
        return False

    home_form = fixture.get("home_team", {}).get("form", {})
    away_form = fixture.get("away_team", {}).get("form", {})
    if home_form.get("matches_analyzed", 0) < MIN_MATCHES_FOR_FORM:
        return False
    if away_form.get("matches_analyzed", 0) < MIN_MATCHES_FOR_FORM:
        return False

    home_news = news_by_team.get(fixture.get("home_team", {}).get("name", ""), {})
    away_news = news_by_team.get(fixture.get("away_team", {}).get("name", ""), {})
    total_high_impact = home_news.get("high_impact_count", 0) + away_news.get("high_impact_count", 0)
    if total_high_impact > MAX_HIGH_IMPACT_NEWS:
        return False

    return True


def build_candidates(fixtures: list, news_by_team: dict) -> list:
    candidates = []
    for fx in fixtures:
        if not data_quality_ok(fx, news_by_team):
            continue

        implied = implied_probabilities(fx["odds"])
        if not implied:
            continue

        estimated = estimate_probabilities(fx, news_by_team)
        home_name = fx["home_team"]["name"]
        away_name = fx["away_team"]["name"]

        label = {
            "home": home_name,
            "draw": "Pareggio",
            "away": away_name,
        }

        for outcome in ("home", "draw", "away"):
            edge = estimated[outcome] - implied[outcome]
            candidates.append(
                {
                    "fixture_id": fx.get("fixture_id", f"{home_name}-{away_name}"),
                    "league": fx.get("league", ""),
                    "match": f"{home_name} - {away_name}",
                    "date": fx.get("date", TODAY),
                    "outcome": outcome,
                    "outcome_label": label[outcome],
                    "odd": float(fx["odds"][outcome]),
                    "estimated_probability": round(estimated[outcome], 3),
                    "implied_probability": round(implied[outcome], 3),
                    "edge": round(edge, 3),
                    "notes": build_notes(fx, news_by_team),
                }
            )
    return candidates


def build_notes(fixture: dict, news_by_team: dict) -> str:
    parts = []
    for side in ("home_team", "away_team"):
        team = fixture[side]["name"]
        form = fixture[side].get("form", {})
        pts = form.get("points_last5", "-")
        analyzed = form.get("matches_analyzed", "-")
        parts.append(f"{team}: {pts} pt nelle ultime {analyzed}")
        news = news_by_team.get(team, {})
        if news.get("high_impact_count", 0) > 0:
            cats = set()
            for art in news.get("flagged_articles", []):
                cats.update(art.get("categories", []))
            parts.append(f"⚠ {team}: notizie ({', '.join(sorted(cats)) if cats else 'rilevanti'})")
    return " | ".join(parts)


def select_three_picks(candidates: list) -> dict:
    used_fixtures = set()
    picks = {}

    if not candidates:
        return picks

    # 1. Conservativo: probabilità stimata più alta con edge non negativo (o il migliore in assoluto)
    conservative_pool = sorted(
        candidates,
        key=lambda c: (c["edge"] >= 0, c["estimated_probability"]),
        reverse=True,
    )
    if conservative_pool:
        picks["conservativo"] = conservative_pool[0]
        used_fixtures.add(conservative_pool[0]["fixture_id"])

    # 2. Consigliato: miglior edge (priorità a probabilità >= 40%)
    consigliato_pool = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures],
        key=lambda c: (c["edge"] >= MIN_EDGE_FOR_PICK, c["estimated_probability"] >= 0.40, c["edge"]),
        reverse=True,
    )
    if consigliato_pool:
        picks["consigliato"] = consigliato_pool[0]
        used_fixtures.add(consigliato_pool[0]["fixture_id"])

    # 3. Hard: quota più alta tra le rimanenti che mantengono edge favorevole
    hard_pool = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures],
        key=lambda c: (c["edge"] >= 0, c["odd"]),
        reverse=True,
    )
    if hard_pool:
        picks["hard"] = hard_pool[0]

    return picks


def main():
    if not FIXTURES_PATH.exists():
        raise SystemExit(f"File partite non trovato: {FIXTURES_PATH}")

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
        "all_candidates": sorted(candidates, key=lambda c: c["edge"], reverse=True),
    }

    (DATA_DIR / "latest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (HISTORY_DIR / f"{TODAY}.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Analisi completata: {len(candidates)} candidati validi, {len(picks)} pronostici selezionati.")


if __name__ == "__main__":
    main()
