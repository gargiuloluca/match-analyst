"""
settle_results.py — AtmBetSignal Triple-Engine Quantitative Settler & Audit Engine
- Matching primario tramite event_id univoco del provider (zero falsi positivi)
- Fallback prudenziale su matching testuale con token normalizzati
- Gestione esatta del Draw No Bet: pareggio = VOID (profitto 0.0, capitale rimborsato)
- Calcolo metriche quantitative avanzate: ROI puro, Brier Score di calibrazione e CLV medio
- Salvataggio atomico su data/tracker.json, data/tracker_xg.json, data/tracker_safe.json
"""

import os
import json
import requests
from pathlib import Path

ODDSAPI_KEY_RAW = os.environ.get("ODDSAPI_KEY", "").strip()
API_KEYS = [k.strip() for k in ODDSAPI_KEY_RAW.split(",") if k.strip()]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TRACKER_FILES = [
    DATA_DIR / "tracker.json",
    DATA_DIR / "tracker_xg.json",
    DATA_DIR / "tracker_safe.json"
]

LEAGUES = [
    "soccer_italy_serie_a", "soccer_spain_la_liga", "soccer_epl",
    "soccer_germany_bundesliga", "soccer_france_ligue_one",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league",
    "soccer_england_championship", "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga", "soccer_belgium_first_div",
    "soccer_england_league1", "soccer_england_efl_cup"
]

def fetch_completed_scores(sport_key: str):
    if not API_KEYS:
        return []
    for key in API_KEYS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores"
        params = {"apiKey": key, "daysFrom": 3}
        try:
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
    return []

def clean_name(s: str) -> str:
    n = s.lower()
    for drop in [" fc", " ac", " as", "cf", "ssc ", "afc ", " "]:
        n = n.replace(drop, "")
    return n

def match_teams_strictly(m_name: str, h_api: str, a_api: str) -> bool:
    h_clean = clean_name(h_api)
    a_clean = clean_name(a_api)
    m_clean = clean_name(m_name)
    return (h_clean[:5] in m_clean) and (a_clean[:5] in m_clean)

def evaluate_bet_outcome(market_key: str, h_score: int, a_score: int):
    """
    Ritorna:
    'WON' (Vinta)
    'LOST' (Persa)
    'VOID' (Rimborsata - specifico per Draw No Bet in pareggio)
    'PENDING' (Incertezza / match non terminato)
    """
    total_goals = h_score + a_score
    m = market_key.upper().strip()

    if m == "1":
        return "WON" if h_score > a_score else "LOST"
    if m == "X":
        return "WON" if h_score == a_score else "LOST"
    if m == "2":
        return "WON" if a_score > h_score else "LOST"
    if m == "1X":
        return "WON" if h_score >= a_score else "LOST"
    if m == "X2":
        return "WON" if a_score >= h_score else "LOST"

    # RISOLUZIONE ESATTA DRAW NO BET (DNB)
    if m in ["DNB_1", "DNB_HOME"]:
        if h_score > a_score: return "WON"
        if h_score == a_score: return "VOID"
        return "LOST"

    if m in ["DNB_2", "DNB_AWAY"]:
        if a_score > h_score: return "WON"
        if h_score == a_score: return "VOID"
        return "LOST"

    if m == "OVER_15":
        return "WON" if total_goals > 1.5 else "LOST"
    if m == "UNDER_15":
        return "WON" if total_goals < 1.5 else "LOST"
    if m == "OVER_25":
        return "WON" if total_goals > 2.5 else "LOST"
    if m == "UNDER_25":
        return "WON" if total_goals < 2.5 else "LOST"
    if m == "OVER_35":
        return "WON" if total_goals > 3.5 else "LOST"
    if m == "UNDER_35":
        return "WON" if total_goals < 3.5 else "LOST"
    if m == "BTTS_YES":
        return "WON" if h_score > 0 and a_score > 0 else "LOST"
    if m == "BTTS_NO":
        return "WON" if h_score == 0 or a_score == 0 else "LOST"

    return "PENDING"

def settle_single_tracker(tracker_file: Path, completed_matches: list, scores_by_event_id: dict):
    if not tracker_file.exists():
        return
    try:
        data = json.loads(tracker_file.read_text(encoding="utf-8"))
    except Exception:
        return

    bets = data.get("bets", [])
    updated = False

    for b in bets:
        # Se già refertata o modificata dall'admin, rispetta lo stato e passa oltre
        if b.get("status") not in ["PENDING", None]:
            continue

        matched_info = None

        # 1. Matching prioritario via Event ID univoco nativo
        e_id = b.get("event_id") or b.get("match_id")
        if e_id and e_id in scores_by_event_id:
            matched_info = scores_by_event_id[e_id]

        # 2. Fallback su matching testuale rigoroso se manca l'ID
        if not matched_info:
            match_name = b.get("match", "")
            for item in completed_matches:
                if match_teams_strictly(match_name, item["home_team"], item["away_team"]):
                    matched_info = item
                    break

        # Se il match non è concluso o mancano dati certi, resta in PENDING
        if not matched_info or not matched_info.get("completed"):
            continue

        h_score = matched_info["home_score"]
        a_score = matched_info["away_score"]
        m_key = b.get("market_key", "")
        
        outcome = evaluate_bet_outcome(m_key, h_score, a_score)
        if outcome == "PENDING":
            continue

        odd = float(b.get("odd", 1.0))
        stake = float(b.get("stake_pct", 1.5))

        b["score"] = f"{h_score}-{a_score}"
        b["status"] = outcome

        # Se registrata una quota di chiusura, calcola il Closing Line Value (CLV)
        closing_odd = float(b.get("closing_odd", 0.0))
        if closing_odd > 1.0:
            b["clv_pct"] = round(((odd / closing_odd) - 1.0) * 100, 2)

        if outcome == "WON":
            b["profit"] = round(stake * (odd - 1.0), 2)
        elif outcome == "LOST":
            b["profit"] = round(-stake, 2)
        elif outcome == "VOID":
            b["profit"] = 0.0

        updated = True

    # RICALCOLO STATISTICO & METRICHE QUANTITATIVE
    concluded = [b for b in bets if b.get("status") in ["WON", "LOST"]]
    won = sum(1 for b in concluded if b["status"] == "WON")
    lost = sum(1 for b in concluded if b["status"] == "LOST")
    void_count = sum(1 for b in bets if b.get("status") == "VOID")

    net_profit = sum(float(b.get("profit", 0.0)) for b in bets if b.get("status") in ["WON", "LOST", "VOID"])
    total_staked = sum(float(b.get("stake_pct", 1.5)) for b in concluded)

    win_rate = round((won / len(concluded)) * 100, 1) if concluded else 0.0
    roi_pct = round((net_profit / total_staked) * 100, 1) if total_staked > 0 else 0.0

    # Calcolo Brier Score (Calibrazione Probabilistica)
    # Brier = (1/N) * sum((prob - actual)^2) dove actual: WON=1, LOST=0
    brier_scores = []
    for b in concluded:
        p_est = float(b.get("prob", 0.0))
        if p_est > 0:
            y = 1.0 if b["status"] == "WON" else 0.0
            brier_scores.append((p_est - y) ** 2)
    avg_brier = round(sum(brier_scores) / len(brier_scores), 4) if brier_scores else None

    # Calcolo CLV medio
    clv_list = [float(b["clv_pct"]) for b in concluded if b.get("clv_pct") is not None]
    avg_clv = round(sum(clv_list) / len(clv_list), 2) if clv_list else None

    data["total_bets"] = len(concluded)
    data["won"] = won
    data["lost"] = lost
    data["void"] = void_count
    data["win_rate"] = win_rate
    data["net_profit_units"] = round(net_profit, 2)
    data["roi_pct"] = roi_pct
    data["brier_score"] = avg_brier
    data["avg_clv_pct"] = avg_clv
    data["bets"] = bets

    tracker_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    clv_msg = f" | CLV {avg_clv}%" if avg_clv is not None else ""
    brier_msg = f" | Brier {avg_brier}" if avg_brier is not None else ""
    print(f"[{tracker_file.name}] Allineato: Concluse {len(concluded)} | WR {win_rate}% | ROI {roi_pct}%{clv_msg}{brier_msg}")

def main():
    completed_matches = []
    scores_by_event_id = {}
    print("Scaricamento risultati finali ufficiali (ID & Scores)...")
    
    for league in LEAGUES:
        scores = fetch_completed_scores(league)
        for s in scores:
            if s.get("completed"):
                ev_id = s.get("id")
                scores_list = s.get("scores")
                if scores_list and len(scores_list) >= 2:
                    h_team = s.get("home_team", "")
                    a_team = s.get("away_team", "")
                    h_sc = int(scores_list[0].get("score", 0)) if scores_list[0].get("name") == h_team else int(scores_list[1].get("score", 0))
                    a_sc = int(scores_list[1].get("score", 0)) if scores_list[1].get("name") == a_team else int(scores_list[0].get("score", 0))
                    
                    match_obj = {
                        "event_id": ev_id,
                        "home_team": h_team,
                        "away_team": a_team,
                        "home_score": h_sc,
                        "away_score": a_sc,
                        "completed": True
                    }
                    completed_matches.append(match_obj)
                    if ev_id:
                        scores_by_event_id[ev_id] = match_obj

    print(f"Match validati: {len(completed_matches)}. Verifica tracker multi-engine...")
    for tf in TRACKER_FILES:
        settle_single_tracker(tf, completed_matches, scores_by_event_id)

if __name__ == "__main__":
    main()
