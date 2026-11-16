
import csv
import re
import time
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ORDNER = Path(r"C:\MaerkteBerlinPython")
ORDNER.mkdir(parents=True, exist_ok=True)

DATEINAME = ORDNER / "berliner_flohmaerkte.csv"
STARTSEITE = "https://www.berlin.de/special/shopping/flohmaerkte/"


class SeitenLeser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texte = []
        self.links = []
        self.link = None
        self.linktexte = []
        self.ignorieren = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignorieren += 1

        if tag == "a" and not self.ignorieren:
            self.link = dict(attrs).get("href")
            self.linktexte = []

    def handle_data(self, text):
        if self.ignorieren:
            return

        text = " ".join(text.split())

        if text:
            self.texte.append(text)

            if self.link is not None:
                self.linktexte.append(text)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignorieren = max(0, self.ignorieren - 1)

        if tag == "a" and self.link is not None:
            name = " ".join(self.linktexte).strip()

            if name:
                self.links.append((name, self.link))

            self.link = None
            self.linktexte = []


def lade_seite(url):
    anfrage = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urlopen(anfrage, timeout=20) as antwort:
        html = antwort.read().decode(
            "utf-8",
            errors="replace"
        )

    leser = SeitenLeser()
    leser.feed(html)
    return leser


def finde_marktlinks(leser):
    ergebnis = []
    bekannt = set()

    for name, href in leser.links:
        url = urljoin(STARTSEITE, href)
        pfad = urlparse(url).path.lower()

        if urlparse(url).netloc != "www.berlin.de":
            continue

        if not pfad.startswith(
            "/special/shopping/flohmaerkte/"
        ):
            continue

        if not pfad.endswith(".html"):
            continue

        if url in bekannt:
            continue

        bekannt.add(url)
        ergebnis.append((name, url))

    return ergebnis


def wert_nach(texte, begriff, anzahl=1):
    for i, text in enumerate(texte):
        if text.strip().lower() == begriff.lower():
            return " ".join(
                texte[i + 1:i + 1 + anzahl]
            ).strip()

    return ""


def finde_termine(texte):
    begriffe = [
        "Termine",
        "Termine 2026",
        "Termine 2027",
        "Nächster Termin",
        "Nächste Termine",
        "Veranstaltungstermine",
        "Wann",
    ]

    gefunden = []

    for i, text in enumerate(texte):
        sauber = text.strip()

        if sauber in begriffe or re.fullmatch(
            r"Termine\s+20\d{2}", sauber
        ):
            nachfolger = texte[i + 1:i + 5]

            if nachfolger:
                gefunden.append(
                    sauber + ": " + " | ".join(nachfolger)
                )

    return " || ".join(gefunden)


def untersuche_markt(name, url):
    leser = lade_seite(url)
    texte = leser.texte

    titel = wert_nach(texte, "Event") or name

    termine = wert_nach(texte, "Termine")
    weitere_termine = finde_termine(texte)

    uhrzeit = wert_nach(texte, "Öffnungszeiten")

    adresse = ""
    for i, text in enumerate(texte):
        if text.strip() == "Adresse":
            adresse = " ".join(texte[i + 1:i + 4])
            break

    aktualisierung = ""
    for text in texte:
        if "Aktualisierung:" in text:
            aktualisierung = text.replace(
                "Aktualisierung:", ""
            ).strip()
            break

    if termine:
        status = "Regelmäßige Angaben gefunden"
    elif weitere_termine:
        status = "Terminangaben gefunden - prüfen"
    else:
        status = "Keine Terminangaben erkannt"

    return {
        "Name": titel,
        "Termine": termine,
        "Weitere Terminangaben": weitere_termine,
        "Öffnungszeiten": uhrzeit,
        "Adresse": adresse,
        "Aktualisierung": aktualisierung,
        "Status": status,
        "Quelle": url
    }


def main():
    print("🛍️ MÄRKTE BERLIN")
    print("Schritt 12: Erweiterte Terminsuche\n")

    startseite = lade_seite(STARTSEITE)
    links = finde_marktlinks(startseite)

    print(f"Gefundene Marktseiten: {len(links)}\n")

    ergebnisse = []

    for nummer, (name, url) in enumerate(links, 1):
        print(f"[{nummer}/{len(links)}] {name}")

        try:
            markt = untersuche_markt(name, url)
            ergebnisse.append(markt)

            print("  Status:", markt["Status"])

            if markt["Termine"]:
                print(
                    "  Termine:",
                    markt["Termine"][:100]
                )

            if markt["Weitere Terminangaben"]:
                print(
                    "  Weitere Angaben:",
                    markt["Weitere Terminangaben"][:150]
                )

        except Exception as fehler:
            print("  FEHLER:", fehler)

        time.sleep(1)

    spalten = [
        "Name",
        "Termine",
        "Weitere Terminangaben",
        "Öffnungszeiten",
        "Adresse",
        "Aktualisierung",
        "Status",
        "Quelle"
    ]

    if ergebnisse:
        try:
            with open(
                DATEINAME,
                "w",
                newline="",
                encoding="utf-8-sig"
            ) as datei:

                schreiber = csv.DictWriter(
                    datei,
                    fieldnames=spalten,
                    delimiter=";"
                )

                schreiber.writeheader()
                schreiber.writerows(ergebnisse)

            print("\n" + "=" * 45)
            print("FERTIG!")
            print(f"Gespeicherte Märkte: {len(ergebnisse)}")
            print("Datei:", DATEINAME)

        except PermissionError:
            print("\nDie CSV-Datei ist möglicherweise")
            print("noch in Excel geöffnet.")
            print("Bitte Excel schließen und erneut starten.")

    print("\nWICHTIG:")
    print("Gefundene Texte sind noch keine")
    print("bestätigten Einzeltermine.")


try:
    main()

except Exception as fehler:
    print("\nFEHLER:", fehler)

finally:
    print("\n--------------------------------")
    input("Zum Beenden bitte ENTER drücken ...")
