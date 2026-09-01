"""
fetch_news.py

Per ogni squadra presente nelle partite del giorno, cerca notizie recenti
nei feed RSS di testate sportive italiane e le classifica per categoria
(infortunio, crisi societaria, spogliatoio, panchina, squalifica).

Nessuna registrazione o API key richiesta: i feed RSS sono pubblici.
Se in futuro vuoi più copertura, puoi aggiungere altri feed alla lista
RSS_FEEDS qui sotto (cerca "nome-sito.it rss" per trovarne altri).

Output: data/raw/news_YYYY-MM-DD.json
"""

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import feedparser

TODAY = date.today().isoformat()
SINCE = datetime.now(timezone.utc) - timedelta(days=3)

FIXTURES_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / f"fixtures_{TODAY}.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Feed RSS pubblici di testate sportive italiane. Aggiungi/rimuovi liberamente.
RSS_FEEDS = [
    "https://www.gazzetta.it/rss/calcio.xml",
    "https://www.ansa.it/sito/notizie/sport/calcio/calcio_rss.xml",
    "https://www.tuttomercatoweb.com/rss/tmwnews.xml",
]

# Categorie di notizie rilevanti e relative parole chiave (italiano).
CATEGORY_KEYWORDS = {
    "infortunio": ["infortunio", "infortunato", "si e' fatto male", "lesione", "salta la partita", "ko", "stop forzato"],
    "crisi_societaria": ["debiti", "crisi societaria", "pignoramento", "stipendi non pagati", "fallimento", "cessione societa'"],
    "spogliatoio": ["litigio", "spogliatoio", "malumori", "tensione interna", "ammutinamento", "rottura con lo spogliatoio"],
    "panchina": ["esonero", "esonerato", "dimissioni allenatore", "cambio allenatore", "sfiducia"],
    "squalifica": ["squalificato", "squalifica", "giudice sportivo", "diffidato"],
}
HIGH_IMPACT_CATEGORIES = set(CATEGORY_KEYWORDS.keys())


def normalize(text: str) -> str:
    return re.sub(r"[’']", "'", text or "").lower()


def parse_entry_date(entry) -> datetime:
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_all_articles() -> list:
    """Scarica e unisce tutti gli articoli recenti da tutti i feed configurati."""
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries:
                pub_date = parse_entry_date(entry)
                if pub_date < SINCE:
                    continue
                articles.append(
                    {
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", ""),
                        "url": entry.get("link", ""),
                        "published_at": pub_date.isoformat(),
                        "source": feed_url,
                    }
                )
        except Exception as e:
            print(f"Attenzione: impossibile leggere il feed {feed_url}: {e}")
    return articles


def classify_article(article: dict) -> list:
    text = normalize(f"{article.get('title', '')} {article.get('summary', '')}")
    return [cat for cat, keywords in CATEGORY_KEYWORDS.items() if any(kw in text for kw in keywords)]


def team_mentioned(article: dict, team_name: str) -> bool:
    text = normalize(f"{article.get('title', '')} {article.get('summary', '')}")
    # Usa la prima parola del nome squadra per tollerare varianti (es. "Inter" da "FC Internazionale")
    key = normalize(team_name).split()[0]
    return key in text


def analyze_team_news(team_name: str, all_articles: list) -> dict:
    relevant = [a for a in all_articles if team_mentioned(a, team_name)]
    flagged = []
    for art in relevant:
        categories = classify_article(art)
        if categories:
            flagged.append({**art, "categories": categories})
    high_impact_count = sum(1 for a in flagged if any(c in HIGH_IMPACT_CATEGORIES for c in a["categories"]))
    return {
        "team": team_name,
        "articles_scanned": len(relevant),
        "flagged_articles": flagged,
        "high_impact_count": high_impact_count,
    }


def main():
    if not FIXTURES_PATH.exists():
        raise SystemExit(f"File partite non trovato: {FIXTURES_PATH}. Esegui prima fetch_fixtures.py.")

    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    team_names = set()
    for fx in fixtures:
        team_names.add(fx["home_team"]["name"])
        team_names.add(fx["away_team"]["name"])

    all_articles = fetch_all_articles()
    print(f"Scaricati {len(all_articles)} articoli dagli ultimi 3 giorni da {len(RSS_FEEDS)} feed.")

    news_by_team = {name: analyze_team_news(name, all_articles) for name in sorted(team_names)}

    out_path = OUTPUT_DIR / f"news_{TODAY}.json"
    out_path.write_text(json.dumps(news_by_team, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Notizie analizzate per {len(news_by_team)} squadre, salvate in {out_path}")


if __name__ == "__main__":
    main()
