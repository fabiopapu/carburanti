# -*- coding: utf-8 -*-
"""
Osserva Carburanti — versione leggera per Railway.

Il server scarica i CSV ufficiali del MIMIT (poche decine di KB, non i
mega-dataset degli impianti) e li tiene in cache in memoria. Nessun proxy
CORS necessario: girando su un server, il blocco CORS del browser non si
applica.

Fonti ufficiali:
- Prezzi medi regionali:      MediaRegionaleStradale.csv
- Prezzi medi autostrade:     MediaNazionaleAutostradale.csv
"""

import re
import threading
import time
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template

app = Flask(__name__)

URL_REGIONI = "https://www.mimit.gov.it/images/stories/carburanti/MediaRegionaleStradale.csv"
URL_AUTOSTRADE = "https://www.mimit.gov.it/images/stories/carburanti/MediaNazionaleAutostradale.csv"

DURATA_CACHE_SECONDI = 3 * 3600  # il MIMIT pubblica una volta al giorno, alle 8:30
TIMEOUT_HTTP = 30
HEADERS = {"User-Agent": "OsservaCarburanti/1.0 (dati open IODL 2.0)"}

_cache = {"dati": None, "timestamp": 0.0}
_lock = threading.Lock()


def _scarica(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_HTTP)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text


def _parse_csv_medie(testo):
    """Formato: 'Aggiornamento GG-MM-AAAA' poi righe REGIONE;TIPOLOGIA;EROGAZIONE;PREZZO
    (per le autostrade manca la colonna REGIONE)."""
    data = None
    valori = {}
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga:
            continue
        m = re.match(r"aggiornamento\s+(\d{2}-\d{2}-\d{4})", riga, re.I)
        if m:
            data = m.group(1)
            continue
        campi = riga.split(";") if ";" in riga else riga.split("|")
        campi = [c.strip() for c in campi]
        if len(campi) < 3:
            continue
        if len(campi) >= 4:
            regione, tipologia, _erog, prezzo_str = campi[:4]
        else:
            regione, tipologia, _erog, prezzo_str = "_nazionale", campi[0], campi[1], campi[2]
        cat_l = tipologia.lower()
        if "benzina" in cat_l:
            chiave = "benzina"
        elif "gasolio" in cat_l:
            chiave = "gasolio"
        elif "gpl" in cat_l:
            chiave = "gpl"
        elif "metano" in cat_l:
            chiave = "metano"
        else:
            continue
        try:
            prezzo = float(prezzo_str.replace(",", "."))
        except ValueError:
            continue
        if prezzo <= 0:
            continue
        valori.setdefault(regione, {})[chiave] = prezzo
    return data, valori


def _elabora():
    testo_reg = _scarica(URL_REGIONI)
    data_reg, regioni = _parse_csv_medie(testo_reg)

    autostrade, data_auto = None, None
    try:
        testo_auto = _scarica(URL_AUTOSTRADE)
        data_auto, valori_auto = _parse_csv_medie(testo_auto)
        autostrade = valori_auto.get("_nazionale") or (next(iter(valori_auto.values()), None))
    except Exception:
        pass  # le autostrade sono un extra: se falliscono non blocco il resto

    return {
        "dataAggiornamento": data_reg,
        "regioni": regioni,
        "autostrade": autostrade,
        "dataAutostrade": data_auto,
        "aggiornatoAlle": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def dati_correnti():
    with _lock:
        scaduti = (time.time() - _cache["timestamp"]) > DURATA_CACHE_SECONDI
        if _cache["dati"] is not None and not scaduti:
            return _cache["dati"], None
        try:
            dati = _elabora()
            if not dati["regioni"]:
                raise ValueError("CSV regionale vuoto o non riconosciuto")
            _cache.update(dati=dati, timestamp=time.time())
            return dati, None
        except Exception as e:
            return _cache["dati"], str(e)  # se ho dati vecchi li servo comunque


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/prezzi")
def api_prezzi():
    dati, errore = dati_correnti()
    if dati is None:
        return jsonify({"errore": errore or "dati non disponibili"}), 503
    risposta = dict(dati)
    if errore:
        risposta["avviso"] = "Aggiornamento odierno non riuscito, mostro l'ultima rilevazione disponibile."
    return jsonify(risposta)


if __name__ == "__main__":
    app.run(debug=True)
