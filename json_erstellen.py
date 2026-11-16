
import csv
import json
import re
import os
import sys
from datetime import date, timedelta, datetime
from pathlib import Path

# Funktioniert auf Windows und GitHub
ORDNER = Path(__file__).resolve().parent
CSV_DATEI = ORDNER / "berliner_flohmaerkte.csv"
JSON_DATEI = ORDNER / "maerkte_berlin.json"

MONATE = {
    "januar": 1, "februar": 2, "märz": 3,
    "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9,
    "oktober": 10, "november": 11,
    "dezember": 12
}

WOCHENTAGE = {
    "montag": 0, "dienstag": 1,
    "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5,
    "sonntag": 6
}

MONATSNAMEN = (
    "Januar|Februar|März|April|Mai|Juni|"
    "Juli|August|September|Oktober|"
    "November|Dezember"
)


def datum_erstellen(jahr, monat, tag):
    try:
        return date(int(jahr), int(monat), int(tag))
    except ValueError:
        return None


def erkenne_wochentage(text):
    text = text.lower()
    ergebnis = []

    for name, nummer in WOCHENTAGE.items():
        if re.search(r"\b" + name + r"\b", text):
            ergebnis.append(nummer)

    return ergebnis


def erkenne_datumsbereiche(text):
    daten = set()

    muster = (
        r"\b(\d{1,2})\.\s*bis\s*"
        r"(\d{1,2})\.\s*"
        r"(" + MONATSNAMEN + r")\s+"
        r"(20\d{2})\b"
    )

    for treffer in re.finditer(
        muster, text, re.IGNORECASE
    ):
        start_tag = int(treffer.group(1))
        ende_tag = int(treffer.group(2))
        monat = MONATE[treffer.group(3).lower()]
        jahr = int(treffer.group(4))

        start = datum_erstellen(jahr, monat, start_tag)
        ende = datum_erstellen(jahr, monat, ende_tag)

        if start and ende and start <= ende:
            tag = start

            while tag <= ende:
                daten.add(tag.isoformat())
                tag += timedelta(days=1)

    return daten


def erkenne_numerische_daten(text):
    daten = set()

    muster_paar = (
        r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*"
        r"und\s*"
        r"(\d{1,2})\.\s*(\d{1,2})\.\s*"
        r"(20\d{2})\b"
    )

    for treffer in re.finditer(muster_paar, text):
        t1, m1, t2, m2, jahr = map(
            int, treffer.groups()
        )

        for tag, monat in [(t1, m1), (t2, m2)]:
            wert = datum_erstellen(jahr, monat, tag)

            if wert:
                daten.add(wert.isoformat())

    muster_einzel = (
        r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*"
        r"(20\d{2})\b"
    )

    for treffer in re.finditer(muster_einzel, text):
        tag, monat, jahr = map(
            int, treffer.groups()
        )

        wert = datum_erstellen(jahr, monat, tag)

        if wert:
            daten.add(wert.isoformat())

    return daten


def erkenne_monatsdaten(text, jahr):
    daten = set()

    muster = (
        r"\b(\d{1,2})\.\s*"
        r"(" + MONATSNAMEN + r")\b"
    )

    for treffer in re.finditer(
        muster, text, re.IGNORECASE
    ):
        tag = int(treffer.group(1))
        monat = MONATE[treffer.group(2).lower()]

        wert = datum_erstellen(jahr, monat, tag)

        if wert:
            daten.add(wert.isoformat())

    return daten


def erkenne_einzeltermine(text):
    daten = set()

    abschnitte = re.findall(
        r"Termine\s+(20\d{2}):\s*"
        r"(.*?)(?=\s*\|\s*|$)",
        text,
        re.IGNORECASE
    )

    for jahr_text, inhalt in abschnitte:
        jahr = int(jahr_text)

        daten.update(
            erkenne_monatsdaten(inhalt, jahr)
        )

        daten.update(
            erkenne_numerische_daten(inhalt)
        )

        daten.update(
            erkenne_datumsbereiche(
                inhalt + " " + str(jahr)
            )
        )

    daten.update(erkenne_datumsbereiche(text))

    return sorted(daten)


def erkenne_ausnahmen(text):
    daten = erkenne_numerische_daten(text)

    muster = (
        r"\b(\d{1,2})\.\s*"
        r"(" + MONATSNAMEN + r")\s+"
        r"(20\d{2})\b"
    )

    for treffer in re.finditer(
        muster, text, re.IGNORECASE
    ):
        tag = int(treffer.group(1))
        monat = MONATE[treffer.group(2).lower()]
        jahr = int(treffer.group(3))

        wert = datum_erstellen(jahr, monat, tag)

        if wert:
            daten.add(wert.isoformat())

    return sorted(daten)


def erkenne_pruefhinweise(text):
    text = text.lower()
    hinweise = []

    begriffe = {
        "totensonntag": "Totensonntag prüfen",
        "volkstrauertag": "Volkstrauertag prüfen",
        "winterpause": "Winterpause prüfen",
        "weihnachten": "Weihnachtsregel prüfen",
        "feiertag": "Feiertagsregel prüfen",
        "karlshorst": "Karlshorst-Ausnahme prüfen",
        "sommerzeit": "Sommer-/Winterzeiten prüfen"
    }

    for begriff, hinweis in begriffe.items():
        if begriff in text:
            hinweise.append(hinweis)

    return hinweise


def verarbeite_markt(zeile):
    name = zeile.get("Name", "").strip()
    termine = zeile.get("Termine", "").strip()
    weitere = zeile.get(
        "Weitere Terminangaben", ""
    ).strip()

    regelmaessig = []

    if (
        "jeden" in termine.lower()
        or "samstag und sonntag" in termine.lower()
    ):
        regelmaessig = erkenne_wochentage(termine)

    einzeltermine = erkenne_einzeltermine(weitere)
    ausnahmen = erkenne_ausnahmen(termine)

    einzeltermine = sorted(
        set(einzeltermine) - set(ausnahmen)
    )

    pruefhinweise = erkenne_pruefhinweise(
        termine + " " + weitere
    )

    if regelmaessig:
        status = "regelmaessig_ungeprueft"
    elif einzeltermine:
        status = "einzeltermine_ungeprueft"
    else:
        status = "termine_unbekannt"

    return {
        "name": name,
        "adresse": zeile.get("Adresse", "").strip(),
        "oeffnungszeiten": zeile.get(
            "Öffnungszeiten", ""
        ).strip(),
        "wochentage": regelmaessig,
        "einzeltermine": einzeltermine,
        "ausnahmen": ausnahmen,
        "pruefhinweise": pruefhinweise,
        "termintext": termine,
        "weitere_terminangaben": weitere,
        "status": status,
        "quelle": zeile.get("Quelle", "").strip(),
        "aktualisierung": zeile.get(
            "Aktualisierung", ""
        ).strip()
    }


def main():
    print("MÄRKTE BERLIN")
    print("Datumsprüfung\n")

    if not CSV_DATEI.exists():
        raise FileNotFoundError(
            f"CSV-Datei fehlt: {CSV_DATEI}"
        )

    maerkte = []

    with open(
        CSV_DATEI,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as datei:
        leser = csv.DictReader(
            datei,
            delimiter=";"
        )

        for zeile in leser:
            maerkte.append(
                verarbeite_markt(zeile)
            )

    if len(maerkte) < 20:
        raise ValueError(
            "SICHERHEIT: Weniger als 20 Märkte. "
            "JSON-Datei wird nicht ersetzt."
        )

    ausgabe = {
        "projekt": "Märkte Berlin",
        "version": 2,
        "erstellt_am": datetime.now().isoformat(
            timespec="seconds"
        ),
        "anzahl": len(maerkte),
        "maerkte": maerkte
    }

    zwischen_datei = JSON_DATEI.with_suffix(
        ".json.tmp"
    )

    with open(
        zwischen_datei,
        "w",
        encoding="utf-8"
    ) as datei:
        json.dump(
            ausgabe,
            datei,
            ensure_ascii=False,
            indent=2
        )

    os.replace(zwischen_datei, JSON_DATEI)

    print("FERTIG!")
    print("Märkte:", len(maerkte))
    print("Datei:", JSON_DATEI)

    print("\nWICHTIGE KONTROLLEN")
    print("-" * 45)

    for markt in maerkte:
        name = markt["name"].lower()

        if (
            "schöneberg" in name
            or "karlshorst" in name
            or "ufafabrik" in name
        ):
            print("\n", markt["name"])
            print("Einzeltermine:", markt["einzeltermine"])
            print("Ausnahmen:", markt["ausnahmen"])
            print("Prüfhinweise:", markt["pruefhinweise"])

    print("\nHinweis:")
    print("Die Termine sind noch nicht vollständig geprüft.")
    print("Keine automatische Veröffentlichung aktiv.")


try:
    main()

except Exception as fehler:
    print("\nFEHLER:", fehler)
    if not sys.stdin.isatty():
        raise

finally:
    print("\n--------------------------------")
    if sys.stdin.isatty():
        input("Zum Beenden bitte ENTER drücken ...")
