#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprime l'anagrafica impianti + i prezzi puntuali del MIMIT in un unico
JSON leggero, pensato per essere scaricato dal browser e disegnato su una
mappa Leaflet. Eseguito da GitHub Actions (accesso internet pieno, nessun
blocco), non da PythonAnywhere.

Chiavi corte per risparmiare spazio (il file finale è comunque di alcuni MB):
  la = latitudine, lo = longitudine, c = comune, p = provincia,
  b = bandiera, s = nome impianto/gestore, pz = prezzi per categoria
  (benzina/gasolio in self se disponibile altrimenti servito; gpl/metano
  in servito, come da metodologia ufficiale del decreto 31/03/2023),
  sf = 1 se il prezzo benzina/gasolio riportato è self, 0 se servito.

Uso: python3 costruisci_impianti.py anagrafica.csv prezzi.csv impianti.json
"""

import csv
import io
import json
import sys


def rileva_separatore(riga):
    return "|" if riga.count("|") >= riga.count(";") else ";"


def leggi_csv_mimit(percorso):
    with open(percorso, encoding="utf-8", errors="replace") as f:
        testo = f.read()
    righe = testo.splitlines()
    if not righe:
        return []
    inizio = 1 if righe[0].lower().startswith("estrazione") else 0
    sep = rileva_separatore(righe[inizio])
    reader = csv.DictReader(io.StringIO("\n".join(righe[inizio:])), delimiter=sep)
    risultato = []
    for r in reader:
        pulito = {}
        for k, v in r.items():
            if k is None:
                continue  # campi extra oltre l'ultima colonna attesa: scartati
            if isinstance(v, list):
                v = v[0] if v else ""  # non dovrebbe capitare per le chiavi note, ma per sicurezza
            pulito[(k or "").strip().lower()] = (v or "").strip()
        risultato.append(pulito)
    return risultato


def categoria(nome):
    f = nome.lower()
    if "metano" in f or "gnl" in f or "gnc" in f:
        return "metano"
    if "gpl" in f:
        return "gpl"
    if "gasolio" in f or "diesel" in f:
        return "gasolio"
    if "benzina" in f:
        return "benzina"
    return None


def main():
    if len(sys.argv) != 4:
        print("Uso: costruisci_impianti.py anagrafica.csv prezzi.csv impianti.json", file=sys.stderr)
        sys.exit(1)

    percorso_anag, percorso_prezzi, percorso_out = sys.argv[1:4]

    righe_anag = leggi_csv_mimit(percorso_anag)
    impianti = {}
    for r in righe_anag:
        idi = r.get("idimpianto")
        try:
            lat, lng = float(r.get("latitudine", "")), float(r.get("longitudine", ""))
        except ValueError:
            continue
        if not idi or not (35 < lat < 47.5) or not (6 < lng < 19):
            continue  # scarto coordinate mancanti o palesemente fuori dall'Italia
        impianti[idi] = {
            "la": round(lat, 5), "lo": round(lng, 5),
            "c": r.get("comune", ""), "p": (r.get("provincia") or "").upper(),
            "b": r.get("bandiera", "") or "Indipendente",
            "s": r.get("nome impianto") or r.get("gestore") or "",
            "pz": {},
        }

    righe_prezzi = leggi_csv_mimit(percorso_prezzi)
    # Per ogni impianto+categoria tengo il prezzo self se esiste, altrimenti servito
    grezzo = {}
    for r in righe_prezzi:
        idi = r.get("idimpianto")
        imp = impianti.get(idi)
        if not imp:
            continue
        cat = categoria(r.get("desccarburante", ""))
        if not cat:
            continue
        try:
            prezzo = float((r.get("prezzo") or "").replace(",", "."))
        except ValueError:
            continue
        if not (0.1 < prezzo < 10):
            continue
        self_flag = r.get("isself") == "1"
        chiave = (idi, cat)
        attuale = grezzo.get(chiave)
        # preferisco il self se disponibile (prezzo più basso, standard per benzina/gasolio)
        if attuale is None or (self_flag and not attuale[1]):
            grezzo[chiave] = (prezzo, self_flag)

    for (idi, cat), (prezzo, self_flag) in grezzo.items():
        impianti[idi]["pz"][cat] = round(prezzo, 3)
        if cat in ("benzina", "gasolio"):
            impianti[idi].setdefault("sf", {})[cat] = 1 if self_flag else 0

    # Scarto impianti senza nessun prezzo valido (anagrafica orfana)
    lista = [v for v in impianti.values() if v["pz"]]

    with open(percorso_out, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Scritti {len(lista)} impianti con almeno un prezzo in {percorso_out}")


if __name__ == "__main__":
    main()
