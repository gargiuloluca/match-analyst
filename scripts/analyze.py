"""
analyze.py — Quantitative Poisson Model & Value Betting Engine.
Modello bivariato di Poisson per la stima indipendente di gol attesi (xG),
matrice esiti esatti e calcolo dell'Edge netto sul mercato 1X2.
"""

import json
import math
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
# Parametri Quantitativi Istituzionali
# ---------------------------------------------------------------------------
# Medie storiche standard campionati europei top-5
DEFAULT_LEAGUE_AVG_HOME_GOALS = 1.55
DEFAULT_LEAGUE_AVG_AWAY_GOALS = 1.20

# Solo value betting pura: scarta qualsiasi pick senza reale vantaggio matematico
MIN_STRICT_EDGE = 0.025        # Almeno +2.5% di edge vs quota de-margined
MIN_PROB_CONSERVATIVO = 0.58   # Probabilità minima per la giocata conservativa


def remove_bookmaker_margin(odds: dict) -> dict:
    """Rimuove l'overround tramite normalizzazione inversa proporzionale (Shin simplified)."""
    try:
        inv = {k: 1.0 / float(odds[k]) for k in ("home", "draw", "away") if float(odds[k]) > 1.0}
        if len(inv) < 3:
            return {}
        overround = sum(inv.values())
        return {k: inv[k] / overround for k in ("home", "draw", "away")}
    except Exception:
        return {}


def poisson_probability(actual_goals: int, lambda_param: float) -> float:
    """Calcola P(X = k) per una variabile casuale di Poisson."""
    return (math.pow(lambda_param, actual_goals) * math.exp(-lambda_param)) / math.factorial(actual_goals)


def calculate_expected_goals(fixture: dict) -> tuple[float, float]:
    """Stima lambda (gol attesi casa) e mu (gol attesi trasferta)

    tramite forza offensiva e difensiva normalizzata.
    """
    home_form = fixture.get("home_team", {}).get("form", {})
    away_form = fixture.get("away_team", {}).get("form", {})

    home_played = max(1, home_form.get("matches_analyzed", 5))
    away_played = max(1, away_form.get("matches_analyzed", 5))

    # Stima dei gol fatti/subiti medi a partita dalla forma recente
    # Con fallback sui gol storici o parametri di default
    home_scored_pg = max(0.5, (home_form.get("points_last5", 5) / home_played) * 0.75 + 0.6)
    home_conceded_pg = max(0.5, 1.4 - (home_form.get("goal_diff_last5", 0) / (home_played * 2)))

    away_scored_pg = max(0.4, (away_form.get("points_last5", 5) / away_played) * 0.6 + 0.4)
    away_conceded_pg = max(0.5, 1.5 - (away_form.get("goal_diff_last5", 0) / (away_played * 2)))

    # Attacco e difesa relativi alle medie del campionato
    home_attack = home_scored_pg / DEFAULT_LEAGUE_AVG_HOME_GOALS
    home_defense = home_conceded_pg / DEFAULT_LEAGUE_AVG_AWAY_GOALS

    away_attack = away_scored_pg / DEFAULT_LEAGUE_AVG_AWAY_GOALS
    away_defense = away_conceded_pg / DEFAULT_LEAGUE_AVG_HOME_GOALS

    # Gol attesi finali (Poisson Rate parameters)
    lambda_home = home_attack * away_defense * DEFAULT_LEAGUE_AVG_HOME_GOALS
    mu_away = away_attack * home_defense * DEFAULT_LEAGUE_AVG_AWAY_GOALS

    # Clamping per evitare estremi matematicamente irrealistici
    return max(0.35, min(3.8, lambda_home)), max(0.25, min(3.2, mu_away))


def simulate_match_poisson(lambda_home: float, mu_away: float, max_goals: int = 6) -> dict:
    """Genera la matrice di probabilità per tutti i punteggi da 0-0 a 5-5

    e ricava le probabilità complessive di 1, X, 2.
    """
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0

    for h in range(max_goals):
        for a in range(max_goals):
            prob = poisson_probability(h, lambda_home) * poisson_probability(a, mu_away)
            if h > a:
                p_home += prob
            elif h == a:
                p_draw += prob
            else:
                p_away += prob

    total = p_home + p_draw + p_away
    return {
        "home": p_home / total,
        "draw": p_draw / total,
        "away": p_away / total,
        "xG_home": round(lambda_home, 2),
        "xG_away": round(mu_away, 2),
    }


def build_candidates(fixtures: list, news_by_team: dict) -> list:
    candidates = []

    for fx in fixtures:
        odds = fx.get("odds")
        if not odds or not all(odds.get(k) for k in ("home", "draw", "away")):
            continue

        true_market_prob = remove_bookmaker_margin(odds)
        if not true_market_prob:
            continue

        lambda_h, mu_a = calculate_expected_goals(fx)
        poisson_res = simulate_match_poisson(lambda_h, mu_a)

        home_name = fx.get("home_team", {}).get("name", "Casa")
        away_name = fx.get("away_team", {}).get("name", "Trasferta")

        # Modificatore opzionale notizie ad alto impatto
        h_news = news_by_team.get(home_name, {}).get("high_impact_count", 0)
        a_news = news_by_team.get(away_name, {}).get("high_impact_count", 0)

        est_probs = {
            "home": poisson_res["home"] * (0.95 if h_news > 0 else 1.0),
            "away": poisson_res["away"] * (0.95 if a_news > 0 else 1.0),
            "draw": poisson_res["draw"],
        }
        tot = sum(est_probs.values())
        est_probs = {k: v / tot for k, v in est_probs.items()}

        labels = {
            "home": f"Vittoria {home_name}",
            "draw": "Pareggio",
            "away": f"Vittoria {away_name}",
        }

        for outcome in ("home", "draw", "away"):
            est_p = est_probs[outcome]
            mkt_p = true_market_prob[outcome]
            edge = est_p - mkt_p
            odd_val = float(odds[outcome])

            # Formula di Kelly frazionaria (Half-Kelly) per il dimensionamento del rischio
            # f* = (bp - q) / b dove b = odd - 1
            b = odd_val - 1.0
            kelly = ((b * est_p) - (1.0 - est_p)) / b if b > 0 else 0
            stake_pct = max(0.0, round((kelly * 0.5) * 100, 1))

            candidates.append(
                {
                    "fixture_id": fx.get("fixture_id", f"{home_name}-{away_name}"),
                    "league": fx.get("league", ""),
                    "match": f"{home_name} - {away_name}",
                    "date": fx.get("date", TODAY),
                    "outcome": outcome,
                    "outcome_label": labels[outcome],
                    "odd": odd_val,
                    "estimated_probability": round(est_p, 3),
                    "implied_probability": round(mkt_p, 3),
                    "edge": round(edge, 3),
                    "xG": f"{poisson_res['xG_home']} - {poisson_res['xG_away']}",
                    "notes": f"xG Stimati: {poisson_res['xG_home']} - {poisson_res['xG_away']} | Stake suggerito (Half-Kelly): {stake_pct}%",
                }
            )

    return candidates


def select_three_picks(candidates: list) -> dict:
    used_fixtures = set()
    picks = {}

    if not candidates:
        return picks

    # 1. CONSERVATIVO: Alta probabilità reale (>= 58%), edge positivo o neutro, quota protetta (<= 1.75)
    conservativi = sorted(
        [c for c in candidates if c["estimated_probability"] >= MIN_PROB_CONSERVATIVO and c["odd"] <= 1.75 and c["edge"] >= 0],
        key=lambda c: (c["edge"] >= MIN_STRICT_EDGE, c["estimated_probability"]),
        reverse=True,
    )
    if conservativi:
        picks["conservativo"] = conservativi[0]
        used_fixtures.add(conservativi[0]["fixture_id"])

    # 2. CONSIGLIATO: Il vero segnale quantitativo — massimo Edge reale in fascia di mercato giocabile (1.65 - 2.45)
    consigliati = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures and 1.65 <= c["odd"] <= 2.45 and c["edge"] >= MIN_STRICT_EDGE],
        key=lambda c: c["edge"],
        reverse=True,
    )
    if consigliati:
        picks["consigliato"] = consigliati[0]
        used_fixtures.add(consigliati[0]["fixture_id"])

    # 3. HARD: Value bet ad alta quota (2.45 - 3.80) ma sempre vincolata ad Edge rigorosamente positivo (>= +2.5%)
    hard = sorted(
        [c for c in candidates if c["fixture_id"] not in used_fixtures and 2.45 <= c["odd"] <= 3.80 and c["edge"] >= MIN_STRICT_EDGE],
        key=lambda c: (c["edge"], c["odd"]),
        reverse=True,
    )
    if hard:
        picks["hard"] = hard[0]

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
        "all_candidates": sorted(candidates, key=lambda c: c["edge"], reverse=True)[:25],
    }

    (DATA_DIR / "latest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (HISTORY_DIR / f"{TODAY}.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Modello Poisson completato: {len(picks)} pronostici a valore effettivo generati su {len(candidates)} esiti analizzati.")


if __name__ == "__main__":
    main()
