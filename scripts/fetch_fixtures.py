"""
fetch_fixtures.py — AtmBetSignal Odds & Daily Window Fetcher (Multi-Key Fallback)
Scarica quote per le leghe europee con The Odds API (h2h, totals).
Supporta rotazione automatica su chiavi multiple (separate da virgola in ODDSAPI_KEY).
FILTRO TEMPORALE RIGIDO: analizza esclusivamente i match in programma entro le prossime 36 ore.
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

API_KEYS_RAW = os.environ.get("ODDSAPI_KEY", "").strip()
API_KEYS = [k.strip() for k in API_KEYS_RAW.split(",") if k.strip()]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "fixtures.json"

LEAGUES = [
    # Top 5 Europee
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    # Coppe Europee
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    # Leghe Strategiche ad Alta Efficienza & Liquidità
    "soccer_england_championship",
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_belgium_first_div",
    "soccer_england_league1",
    "soccer_england_efl_cup"
]

def fetch_league_odds_with_fallback(sport_key: str):
    if not API_KEYS:
        print("Errore: ODDSAPI_KEY non trovata nelle variabili d'ambiente.")
        return []

    for idx, key in enumerate(API_KEYS):
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": key,
            "regions": "eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal"
        }
        try:
            res = requests.get(url, params=params, timeout=20)
            if res.status_code == 200:
                return res.json()
            elif res.status_code in [401, 429]:
                print(f"Avviso: Chiave API #{idx+1} non valida o crediti esauriti (Status {res.status_code}). Tento con la successiva...")
            elif res.status_code == 404:
                return []
            else:
                print(f"Info: Status {res.status_code} per {sport_key} con chiave #{idx+1}")
        except Exception as e:
            print(f"Errore connessione su {sport_key} con chiave #{idx+1}: {e}")

    print(f"Errore critico: Tutte le chiavi API fornite sono fallite per {sport_key}.")
    return []

def parse_match_data(raw_matches, sport_key: str, existing_openings: dict):
    parsed = []
    now = datetime.now(timezone.utc)
    max_window = now + timedelta(hours=36)

    for m in raw_matches:
        commence_time_str = m.get("commence_time")
        if not commence_time_str:
            continue

        try:
            match_time = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
        except Exception:
            continue

        if match_time < now or match_time > max_window:
            continue

        home_team = m.get("home_team")
        away_team = m.get("away_team")
        m_id = m.get("id")
        bookmakers = m.get("bookmakers", [])

        if not bookmakers:
            continue

        h2h_home, h2h_draw, h2h_away = [], [], []
        over15, under15 = [], []
        over25, under25 = [], []
        over35, under35 = [], []

        for b in bookmakers:
            for market in b.get("markets", []):
                m_key = market.get("key")
                if m_key == "h2h":
                    for outcome in market.get("outcomes", []):
                        price = outcome.get("price", 0.0)
                        name = outcome.get("name")
                        if name == home_team and price > 1.0:
                            h2h_home.append(price)
                        elif name == away_team and price > 1.0:
                            h2h_away.append(price)
                        elif name.lower() in ["draw", "pareggio"] and price > 1.0:
                            h2h_draw.append(price)
                elif m_key == "totals":
                    for outcome in market.get("outcomes", []):
                        price = outcome.get("price", 0.0)
                        point = outcome.get("point", 0.0)
                        name_low = outcome.get("name", "").lower()
                        
                        if point == 1.5:
                            if name_low in ["over", "più"]: over15.append(price)
                            elif name_low in ["under", "meno"]: under15.append(price)
                        elif point == 2.5:
                            if name_low in ["over", "più"]: over25.append(price)
                            elif name_low in ["under", "meno"]: under25.append(price)
                        elif point == 3.5:
                            if name_low in ["over", "più"]: over35.append(price)
                            elif name_low in ["under", "meno"]: under35.append(price)

        if not (h2h_home and h2h_draw and h2h_away):
            continue

        odd_1 = sum(h2h_home) / len(h2h_home)
        odd_x = sum(h2h_draw) / len(h2h_draw)
        odd_2 = sum(h2h_away) / len(h2h_away)

        # Doppie Chance sintetiche con aggio banco reale
        prob_1x = (1.0 / odd_1) + (1.0 / odd_x)
        odd_1x = round(1.0 / (prob_1x * 1.05), 2) if prob_1x > 0 else 0.0

        prob_x2 = (1.0 / odd_2) + (1.0 / odd_x)
        odd_x2 = round(1.0 / (prob_x2 * 1.05), 2) if prob_x2 > 0 else 0.0

        # Draw No Bet sintetico (Rimborso Pareggio)
        decisive_prob = (1.0 / odd_1) + (1.0 / odd_2)
        odd_dnb_1 = round(1.0 / ((1.0 / odd_1) / decisive_prob * 1.05), 2) if decisive_prob > 0 else 0.0
        odd_dnb_2 = round(1.0 / ((1.0 / odd_2) / decisive_prob * 1.05), 2) if decisive_prob > 0 else 0.0

        # Totali Gol
        o25 = sum(over25) / len(over25) if over25 else 0.0
        u25 = sum(under25) / len(under25) if under25 else 0.0
        o15 = sum(over15) / len(over15) if over15 else (round(1.0 + (o25 - 1.0) * 0.45, 2) if o25 > 1.0 else 1.28)
        u15 = sum(under15) / len(under15) if under15 else 3.50
        o35 = sum(over35) / len(over35) if over35 else (round(o25 * 1.85, 2) if o25 > 1.0 else 3.20)
        u35 = sum(under35) / len(under35) if under35 else (round(1.0 + (u25 - 1.0) * 0.45, 2) if u25 > 1.0 else 1.30)

        # Gol / NoGol calibrato: quote protette senza divisioni errate
        # Nessun NoGol supera mai quota 1.85 (evita falsi allarmi e finti Edge)
        btts_yes = round(min(2.15, max(1.45, o25 * 0.95)), 2) if o25 > 1.0 else 1.80
        btts_no = round(min(1.85, max(1.40, 3.40 - btts_yes)), 2)

        current_odds = {
            "1": round(odd_1, 2),
            "X": round(odd_x, 2),
            "2": round(odd_2, 2),
            "1X": max(1.15, odd_1x),
            "X2": max(1.15, odd_x2),
            "DNB_1": max(1.18, odd_dnb_1),
            "DNB_2": max(1.18, odd_dnb_2),
            "OVER_15": max(1.15, o15),
            "UNDER_15": max(1.50, u15),
            "OVER_25": round(o25, 2) if o25 > 1.0 else 0.0,
            "UNDER_25": round(u25, 2) if u25 > 1.0 else 0.0,
            "OVER_35": max(1.60, o35),
            "UNDER_35": max(1.18, u35),
            "BTTS_YES": btts_yes,
            "BTTS_NO": btts_no
        }

        opening_odds = existing_openings.get(m_id, current_odds)

        parsed.append({
            "id": m_id,
            "sport_key": sport_key,
            "league_name": m.get("sport_title", sport_key),
            "commence_time": commence_time_str,
            "home_team": home_team,
            "away_team": away_team,
            "odds": current_odds,
            "opening_odds": opening_odds
        })

    return parsed

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    existing_openings = {}
    if OUTPUT_FILE.exists():
        try:
            prev = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            for fx in prev.get("fixtures", []):
                m_id = fx.get("id")
                if m_id:
                    existing_openings[m_id] = fx.get("opening_odds", fx.get("odds", {}))
        except Exception:
            pass

    all_fixtures = []
    print(f"Scansione flussi in corso su {len(LEAGUES)} campionati (Filtro 36h attivo con Multi-Key Fallback)...")
    for league in LEAGUES:
        raw = fetch_league_odds_with_fallback(league)
        matches = parse_match_data(raw, league, existing_openings)
        all_fixtures.extend(matches)

    output_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": len(all_fixtures),
        "fixtures": all_fixtures
    }

    OUTPUT_FILE.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completato: {len(all_fixtures)} match della giornata scaricati in data/fixtures.json.")

if __name__ == "__main__":
    main()
