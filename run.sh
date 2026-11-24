#!/usr/bin/env bash
# Avvio del Simulatore Fido SIAD su macOS / Linux: ./run.sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
if [ ! -x ".venv/bin/python" ]; then
    echo "Prima configurazione: creo l'ambiente Python isolato..."
    if ! "$PY" -m venv .venv; then
        echo "Creazione dell'ambiente non riuscita. Verifica che Python 3.10 o superiore sia installato (python.org)."
        exit 1
    fi
fi
VPY=.venv/bin/python
"$VPY" -m pip install -q --upgrade pip
if ! "$VPY" -m pip install -q -r requirements.txt; then
    echo "Installazione delle librerie non riuscita."
    exit 1
fi
"$VPY" -m streamlit run app.py
