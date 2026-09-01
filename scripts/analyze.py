"""
analyze.py

Combina partite+quote (fetch_fixtures.py) e notizie extra-campo
(fetch_news.py), applica un filtro di qualita' dei dati, stima le
probabilita' di ogni esito con un modello placeholder, e produce 3
pronostici per la giornata: conservativo, consigliato, hard.

NB: il modello di probabilita' qui e' volutamente semplice (basato su forma
recente + differenza reti + penalita' per notizie ad alto impatto). E'
pensato come punto di partenza da sostituire con un modello piu' robusto
(es. Poisson sui gol attesi, o un modello allenato su dati storici) non
appena hai raccolto abbastanza storico tramite questo stesso sistema.

Output: data/latest.json + data/history/YYYY-MM-DD.json
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
# Parametri del filtro e del modello — modifica liberamente in base ai tuoi
# criteri di selezione.
# ---------------------------------------------------------------------------

MIN_MATCHES_FOR_FORM = 3          # sotto questa soglia i dati di forma sono inaffidabili
MAX_HIGH_IMPACT_NEWS = 1          # oltre questa soglia l'evento viene scartato (troppa incertezza)
MIN_EDGE_FOR_PICK = 0.03          # margine minimo (stima - implicita) per considerare un pick "di valore"


def implied_probabilities(odds: dict) -> dict:
    """Converte le quote 1X2 in probabilita' implicite, rimuovendo il margine
    del bookmaker (overround) tramite normalizzazione."""
    if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
        return {}
    raw = {k: 1 / odds[k] for k in ("home", "draw", "away")}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def estimate_probabilities(fixture: dict, news_by_team: dict) -> dict:
    """Modello placeholder: stima P(1)/P(X)/P(2) da forma recente e
    differenza reti, poi applica una penalita' se una squadra ha notizie
    negative ad alto impatto non ancora riflesse pienamente nella quota."""
    home_form = fixture["home_team"]["form"]
    away_form = fixture["away_team"]["form"]

    # Punteggio di forza grezzo: punti + peso sulla differenza reti
    home_strength = home_form["points_last5"] + 0.5 * home_form["goal_diff_last5"]
    away_strength = away_form["points_last5"] + 0.5 * away_form["goal_diff_last5"]

    # Vantaggio campo
    home_strength += 2

    total = home_strength + away_strength
    if total <= 0:
        base_home, base_away = 0.4, 0.35
    else:
        base_home = 0.75 * (home_strength / total) if total else 0.4
        base_away = 0.75 * (away_strength / total) if total else 0.35
    base_draw = max(0.15, 1 - base_home - base_away)

    probs = {"home": base_home, "draw": base_draw, "away": base_away}

    # Penalita' per notizie ad alto impatto
    home_news = news_by_team.get(fixture["home_team"]["name"], {})
    away_news = news_by_team.get(fixture["away_team"]["name"], {})
    if home_news.get("high_impact_count", 0) > 0:
        probs["home"] *= 0.85
    if away_news.get("high_impact_count", 0) > 0:
        probs["away"] *= 0.85

    # Rinormalizza
    total_p = sum(probs.values())
    return {k: v / total_p for k, v in probs.items()}


def data_quality_ok(fixture: dict, news_by_team: dict) -> bool:
    home_form = fixture["home_team"]["form"]
    away_form = fixture["away_team"]["form"]
    if home_form["matches_analyzed"] < MIN_MATCHES_FOR_FORM:
        return False
    if away_form["matches_analyzed"] < MIN_MATCHES_FOR_FORM:
        return False
    home_news = news_by_team.get(fixture["home_team"]["name"], {})
    away_news = news_by_team.get(fixture["away_team"]["name"], {})
    total_high_impact = home_news.get("high_impact_count", 0) + away_news.get("high_impact_count", 0)
    if total_high_impact > MAX_HIGH_IMPACT_NEWS:
        return False
    if not fixture.get("odds"):
        return False
    return True


def build_candidates(fixtures: list, news_by_team: dict) -> list:
    """Per ogni partita che supera il filtro, calcola i candidati (esito +
    probabilita' stimata + probabilita' implicita + edge)."""
    candidates = []
    for fx in fixtures:
        if not data_quality_ok(fx, news_by_team):
            continue

        implied = implied_probabilities(fx["odds"])
        if not implied:
            continue
        estimated = estimate_probabilities(fx, news_by_team)

        label = {
            "home": fx["home_team"]["name"],
            "draw": "Pareggio",
            "away": fx["away_team"]["name"],
        }
        odd_key = {"home": "home", "draw": "draw", "away": "away"}

        for outcome in ("home", "draw", "away"):
            edge = estimated[outcome] - implied[outcome]
            candidates.append(
                {
                    "fixture_id": fx["fixture_id"],
                    "league": fx.get("league", ""),
                    "match": f"{fx['home_team']['name']} - {fx['away_team']['name']}",
                    "date": fx["date"],
                    "outcome": outcome,
                    "outcome_label": label[outcome],
                    "odd": fx["odds"][odd_key[outcome]],
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
        form = fixture[side]["form"]
        parts.append(f"{team}: {form['points_last5']} pt nelle ultime {form['matches_analyzed']}")
        news = news_by_team.get(team, {})
        if news.get("high_impact_count", 0) > 0:
            cats = set()
            for art in news.get("flagged_articles", []):
                cats.update(art["categories"])
            parts.append(f"⚠ {team}: notizie rilevanti ({', '.join(sorted(cats))})")
    return " | ".join(parts)


def select_three_picks(candidates: list) -> dict:
    """Sceglie 1 conservativo, 1 consigliato, 1 hard tra tutti i candidati
    del giorno, evitando di riproporre lo stesso evento due volte."""
    used_fixtures = set()
    picks = {}

    # Conservativo: probabilita' stimata piu' alta, edge non negativo
    conservative_pool = sorted(
        [c for c in candidates if c["edge"] >= 0],
        key=lambda c: c["estimated_probability"],
        reverse=True,
    )
    if conservative_pool:
        picks["conservativo"] = conservative_pool[0]
        used_fixtures.add(conservative_pool[0]["fixture_id"])

    # Consigliato: miglior edge tra i candidati con probabilita' ragionevole (>=45%)
    consigliato_pool = sorted(
        [c for c in candidates if c["edge"] >= MIN_EDGE_FOR_PICK and c["estimated_probability"] >= 0.45
         and c["fixture_id"] not in used_fixtures],
        key=lambda c: c["edge"],
        reverse=True,
    )
    if consigliato_pool:
        picks["consigliato"] = consigliato_pool[0]
        used_fixtures.add(consigliato_pool[0]["fixture_id"])

    # Hard: quota piu' alta tra i candidati con edge comunque positivo
    hard_pool = sorted(
        [c for c in candidates if c["edge"] >= MIN_EDGE_FOR_PICK and c["fixture_id"] not in used_fixtures],
        key=lambda c: c["odd"],
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
