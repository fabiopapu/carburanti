# -*- coding: utf-8 -*-
"""
Scarica le notizie più recenti sui carburanti da Google News (feed RSS
pubblico, gratuito, nessuna chiave richiesta) ed estrae SOLO titolo, fonte
e link — mai il testo dell'articolo, che resta protetto da copyright e va
letto sul sito originale.

Gira su GitHub Actions per lo stesso motivo di sempre: accesso internet
libero, senza i blocchi del piano gratuito di PythonAnywhere.

Uso: python3 aggiorna_notizie.py dati/notizie.json
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote

import requests

HEADERS = {"User-Agent": "OsservaCarburanti/1.0 (uso civico)"}
QUERY = "carburanti prezzo benzina distributori"
MAX_NOTIZIE = 6


def scarica_notizie():
    url = f"https://news.google.com/rss/search?q={quote(QUERY)}&hl=it&gl=IT&ceid=IT:it"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.text)

    notizie = []
    visti = set()  # per non ripetere due volte lo stesso titolo

    for item in root.findall(".//item"):
        titolo_grezzo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        fonte_tag = item.find("source")
        fonte = fonte_tag.text.strip() if fonte_tag is not None and fonte_tag.text else None

        if not titolo_grezzo or not link:
            continue

        # Google News mette quasi sempre " - NomeTestata" alla fine del
        # titolo, ANCHE quando il tag <source> dedicato è già presente
        # (caso più comune) — quindi ripulisco sempre, non solo se manca.
        titolo = titolo_grezzo
        if fonte and titolo_grezzo.endswith(f" - {fonte}"):
            titolo = titolo_grezzo[: -(len(fonte) + 3)]
        elif not fonte and " - " in titolo_grezzo:
            titolo, fonte = titolo_grezzo.rsplit(" - ", 1)

        if titolo in visti:
            continue
        visti.add(titolo)

        notizie.append({
            "titolo": titolo.strip(),
            "fonte": (fonte or "").strip(),
            "link": link,
            "data": pub_date,
        })

        if len(notizie) >= MAX_NOTIZIE:
            break

    return notizie


def main():
    if len(sys.argv) != 2:
        print("Uso: aggiorna_notizie.py notizie.json", file=sys.stderr)
        sys.exit(1)
    percorso_out = sys.argv[1]

    try:
        notizie = scarica_notizie()
    except Exception as e:
        print(f"ATTENZIONE: impossibile scaricare le notizie: {e}")
        notizie = []

    risultato = {
        "generato_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "notizie": notizie,
    }

    with open(percorso_out, "w", encoding="utf-8") as f:
        json.dump(risultato, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Scritte {len(notizie)} notizie in {percorso_out}")
    for n in notizie:
        print(f"  - {n['titolo']} ({n['fonte']})")


if __name__ == "__main__":
    main()
