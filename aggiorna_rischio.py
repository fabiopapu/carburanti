# -*- coding: utf-8 -*-
"""
Calcola un indice indicativo di rischio "il prezzo dei carburanti potrebbe
salire nei prossimi giorni", basato su fonti ufficiali pubbliche:
- Petrolio Brent: Federal Reserve Bank of St. Louis (FRED), serie DCOILBRENTEU
- Cambio EUR/USD: Banca Centrale Europea (BCE), tasso di riferimento giornaliero

Gira su GitHub Actions (accesso internet libero) perché PythonAnywhere free
blocca l'accesso diretto a FRED — stessa soluzione già usata per i dati
carburanti stessi.

IMPORTANTE: questo è un indicatore statistico approssimativo basato sulla
tendenza recente del petrolio, NON una previsione certa. Va presentato
sempre con questo chiarimento.

Uso: python3 aggiorna_rischio.py dati/rischio.json
"""

import csv
import io
import json
import sys
from datetime import datetime

import requests

HEADERS = {"User-Agent": "OsservaCarburanti/1.0 (uso civico)"}


def scarica_brent():
    """FRED restituisce un CSV con DATE,DCOILBRENTEU. Nei weekend/festivi il
    valore è '.' (mancante): scarto quelle righe e tengo solo dati veri."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    punti = []
    for riga in reader:
        valore = riga.get("DCOILBRENTEU", ".").strip()
        if valore == "." or not valore:
            continue
        try:
            punti.append((riga["observation_date"] if "observation_date" in riga else riga["DATE"], float(valore)))
        except (ValueError, KeyError):
            continue
    return punti  # [(data, prezzo), ...] in ordine cronologico


def scarica_eurusd():
    """BCE: tasso di riferimento giornaliero EUR/USD, formato CSV ufficiale."""
    url = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?lastNObservations=10&format=csvdata"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    punti = []
    for riga in reader:
        try:
            data = riga.get("TIME_PERIOD")
            valore = float(riga.get("OBS_VALUE"))
            if data and valore:
                punti.append((data, valore))
        except (ValueError, TypeError):
            continue
    return punti


def calcola_variazione_percentuale(punti, giorni_indietro=7):
    """Percentuale di variazione tra l'ultimo dato disponibile e quello di
    circa N giorni prima (non esattamente N: prendo il punto più vicino
    disponibile, per tollerare weekend/festivi mancanti)."""
    if len(punti) < 2:
        return None, None, None
    oggi_data, oggi_valore = punti[-1]
    indice_riferimento = max(0, len(punti) - 1 - giorni_indietro)
    prima_data, prima_valore = punti[indice_riferimento]
    if prima_valore == 0:
        return None, oggi_valore, oggi_data
    variazione = (oggi_valore - prima_valore) / prima_valore
    return variazione, oggi_valore, oggi_data


def main():
    if len(sys.argv) != 2:
        print("Uso: aggiorna_rischio.py rischio.json", file=sys.stderr)
        sys.exit(1)
    percorso_out = sys.argv[1]

    risultato = {
        "generato_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "indice_rischio": None,
        "brent_usd": None,
        "brent_variazione_7gg_pct": None,
        "eur_usd": None,
        "eur_usd_variazione_7gg_pct": None,
        "fonte": "FRED (Federal Reserve St. Louis) per il petrolio Brent, BCE per il cambio EUR/USD",
        "avviso": "Stima statistica approssimativa basata sulla tendenza recente, non una previsione certa.",
    }

    try:
        punti_brent = scarica_brent()
        var_brent, prezzo_brent, data_brent = calcola_variazione_percentuale(punti_brent)
        risultato["brent_usd"] = round(prezzo_brent, 2) if prezzo_brent else None
        risultato["brent_variazione_7gg_pct"] = round(var_brent * 100, 1) if var_brent is not None else None
        print(f"Brent: {prezzo_brent} USD ({data_brent}), variazione 7gg: {risultato['brent_variazione_7gg_pct']}%")
    except Exception as e:
        print(f"ATTENZIONE: impossibile scaricare il Brent: {e}")
        var_brent = None

    try:
        punti_eur = scarica_eurusd()
        var_eur, cambio_eur, data_eur = calcola_variazione_percentuale(punti_eur)
        risultato["eur_usd"] = round(cambio_eur, 4) if cambio_eur else None
        risultato["eur_usd_variazione_7gg_pct"] = round(var_eur * 100, 1) if var_eur is not None else None
        print(f"EUR/USD: {cambio_eur} ({data_eur}), variazione 7gg: {risultato['eur_usd_variazione_7gg_pct']}%")
    except Exception as e:
        print(f"ATTENZIONE: impossibile scaricare EUR/USD: {e}")
        var_eur = None

    # Indice 0-100: parto da 50 (neutro). Il petrolio che sale pesa di più
    # (è il fattore diretto sul prezzo dei carburanti); un dollaro che si
    # rafforza (EUR/USD scende) pesa un po' meno ma nella stessa direzione,
    # perché il petrolio si compra in dollari. Pesi scelti in modo
    # trasparente e prudente, non sono un modello scientifico.
    if var_brent is not None:
        indice = 50 + (var_brent * 250)  # +10% di Brent in una settimana -> +25 punti
        if var_eur is not None:
            indice += (-var_eur) * 100  # EUR/USD -2% (dollaro forte) -> +2 punti di rischio
        indice = max(0, min(100, round(indice)))
        risultato["indice_rischio"] = indice
        print(f"Indice di rischio calcolato: {indice}/100")
    else:
        print("Indice di rischio non calcolabile (dati Brent mancanti)")

    with open(percorso_out, "w", encoding="utf-8") as f:
        json.dump(risultato, f, ensure_ascii=False, indent=None, separators=(",", ":"))
    print(f"\nScritto {percorso_out}")


if __name__ == "__main__":
    main()
