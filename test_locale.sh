#!/usr/bin/env bash
# Esegue l'intera pipeline in locale, per testare prima di spostare tutto
# su GitHub. Richiede le variabili d'ambiente FOOTBALLDATA_KEY e ODDSAPI_KEY.
#
# Uso:
#   export FOOTBALLDATA_KEY="la-tua-chiave"
#   export ODDSAPI_KEY="la-tua-chiave"
#   ./test_locale.sh

set -e

if [ -z "$FOOTBALLDATA_KEY" ]; then
  echo "Errore: variabile FOOTBALLDATA_KEY non impostata."
  echo "Esegui prima: export FOOTBALLDATA_KEY=\"la-tua-chiave\""
  exit 1
fi

echo "1/4 — Installo le dipendenze..."
pip install -r scripts/requirements.txt --quiet

echo "2/4 — Scarico partite, classifica e quote..."
python scripts/fetch_fixtures.py

echo "3/4 — Scarico e classifico le notizie..."
python scripts/fetch_news.py

echo "4/4 — Eseguo l'analisi e genero i pronostici..."
python scripts/analyze.py

echo ""
echo "Fatto. Per vedere la dashboard, esegui:"
echo "  python -m http.server 8000"
echo "e apri http://localhost:8000 nel browser."
