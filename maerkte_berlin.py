import csv
import re
import sys
import time
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen

ORDNER = Path(__file__).resolve().parent
DATEINAME = ORDNER / 'berliner_flohmaerkte.csv'
VORSCHAU = ORDNER / 'berliner_flohmaerkte_neu.csv'
STARTSEITE = 'https://www.berlin.de/special/shopping/flohmaerkte/'
SPALTEN = ['Name', 'Termine', 'Weitere Terminangaben', 'Öffnungszeiten', 'Adresse', 'Aktualisierung', 'Status', 'Quelle']
MINDESTANZAHL = 20

class SeitenLeser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texte = []
        self.links = []
        self.link = None
        self.linktexte = []
        self.ignorieren = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.ignorieren += 1
        if tag == 'a' and not self.ignorieren:
            self.link = dict(attrs).get('href')
            self.linktexte = []

    def handle_data(self, text):
        if self.ignorieren:
            return
        text = ' '.join(text.split())
        if text:
            self.texte.append(text)
            if self.link is not None:
                self.linktexte.append(text)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.ignorieren = max(0, self.ignorieren - 1)
        if tag == 'a' and self.link is not None:
            name = ' '.join(self.linktexte).strip()
            if name:
                self.links.append((name, self.link))
            self.link = None
            self.linktexte = []


def lade_seite(url):
    anfrage = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; MaerkteBerlin/1.0)'})
    with urlopen(anfrage, timeout=25) as antwort:
        html = antwort.read().decode('utf-8', errors='replace')
    leser = SeitenLeser()
    leser.feed(html)
    return leser


def finde_marktlinks(leser):
    ergebnis = []
    bekannt = set()
    for name, href in leser.links:
        url, _ = urldefrag(urljoin(STARTSEITE, href))
        teile = urlparse(url)
        pfad = teile.path.lower()
        if teile.scheme != 'https' or teile.netloc.lower() != 'www.berlin.de':
            continue
        if not pfad.startswith('/special/shopping/flohmaerkte/') or not pfad.endswith('.html'):
            continue
        if url in bekannt:
            continue
        bekannt.add(url)
        ergebnis.append((name, url))
    return ergebnis


def wert_nach(texte, begriff, anzahl=1):
    for i, text in enumerate(texte):
        if text.strip().lower() == begriff.lower():
            return ' '.join(texte[i + 1:i + 1 + anzahl]).strip()
    return ''


def finde_termine(texte):
    begriffe = {'Termine', 'Termine 2026', 'Termine 2027', 'Nächster Termin', 'Nächste Termine', 'Veranstaltungstermine', 'Wann'}
    gefunden = []
    for i, text in enumerate(texte):
        sauber = text.strip()
        if sauber in begriffe or re.fullmatch(r'Termine\s+20\d{2}', sauber):
            nachfolger = texte[i + 1:i + 5]
            if nachfolger:
                gefunden.append(sauber + ': ' + ' | '.join(nachfolger))
    return ' || '.join(gefunden)


def untersuche_markt(name, url):
    leser = lade_seite(url)
    texte = leser.texte
    titel = wert_nach(texte, 'Event') or name
    termine = wert_nach(texte, 'Termine')
    weitere_termine = finde_termine(texte)
    uhrzeit = wert_nach(texte, 'Öffnungszeiten')
    adresse = ''
    for i, text in enumerate(texte):
        if text.strip() == 'Adresse':
            adresse = ' '.join(texte[i + 1:i + 4])
            break
    aktualisierung = ''
    for text in texte:
        if 'Aktualisierung:' in text:
            aktualisierung = text.replace('Aktualisierung:', '').strip()
            break
    if termine:
        status = 'Regelmäßige Angaben gefunden'
    elif weitere_termine:
        status = 'Terminangaben gefunden - prüfen'
    else:
        status = 'Keine Terminangaben erkannt'
    return {'Name': titel, 'Termine': termine, 'Weitere Terminangaben': weitere_termine,
            'Öffnungszeiten': uhrzeit, 'Adresse': adresse, 'Aktualisierung': aktualisierung,
            'Status': status, 'Quelle': url}


def lese_bisherige_daten():
    if not DATEINAME.exists():
        raise FileNotFoundError(f'Bisherige CSV fehlt: {DATEINAME}')
    with DATEINAME.open(newline='', encoding='utf-8-sig') as datei:
        zeilen = list(csv.DictReader(datei, delimiter=';'))
    if len(zeilen) < MINDESTANZAHL:
        raise ValueError(f'Bisherige CSV enthält nur {len(zeilen)} Märkte.')
    return zeilen


def schreibe_vorschau(zeilen):
    with VORSCHAU.open('w', newline='', encoding='utf-8-sig') as datei:
        schreiber = csv.DictWriter(datei, fieldnames=SPALTEN, delimiter=';')
        schreiber.writeheader()
        schreiber.writerows(zeilen)


def main():
    print('MÄRKTE BERLIN – Online-Änderungsprüfung', flush=True)
    bisher = lese_bisherige_daten()
    startseite = lade_seite(STARTSEITE)
    links = finde_marktlinks(startseite)
    print(f'Gefundene Marktseiten: {len(links)}', flush=True)
    if len(links) < MINDESTANZAHL:
        raise ValueError('Zu wenige Marktseiten gefunden. Bestehende CSV bleibt unverändert.')

    ergebnisse = []
    fehler = []
    for nummer, (name, url) in enumerate(links, 1):
        print(f'[{nummer}/{len(links)}] {name}', flush=True)
        try:
            ergebnisse.append(untersuche_markt(name, url))
        except Exception as ausnahme:
            fehler.append(f'{url}: {ausnahme}')
            print('  Abruf fehlgeschlagen:', ausnahme, flush=True)
        time.sleep(1)

    if fehler or len(ergebnisse) < MINDESTANZAHL:
        raise RuntimeError(f'{len(fehler)} Seitenfehler, {len(ergebnisse)} erfolgreiche Märkte. Keine Vorschau gespeichert.')

    alt = {z['Quelle']: z for z in bisher if z.get('Quelle')}
    neu = {z['Quelle']: z for z in ergebnisse if z.get('Quelle')}
    hinzu = sorted(set(neu) - set(alt))
    verschwunden = sorted(set(alt) - set(neu))
    feldnamen = ['Name', 'Termine', 'Weitere Terminangaben', 'Öffnungszeiten', 'Adresse', 'Aktualisierung']
    veraendert = []
    for url in sorted(set(alt) & set(neu)):
        felder = [feld for feld in feldnamen if (alt[url].get(feld) or '').strip() != (neu[url].get(feld) or '').strip()]
        if felder:
            veraendert.append((neu[url]['Name'], felder, url))

    schreibe_vorschau(ergebnisse)
    print('\nERGEBNIS – NUR ZUR PRÜFUNG')
    print('Bisherige Märkte:', len(bisher))
    print('Neu gefundene Märkte:', len(ergebnisse))
    print('Neue Marktseiten:', len(hinzu))
    print('Nicht mehr gefundene Marktseiten:', len(verschwunden))
    print('Veränderte Marktseiten:', len(veraendert))
    for url in hinzu:
        print('NEU:', neu[url]['Name'], url)
    for url in verschwunden:
        print('NICHT MEHR GEFUNDEN (nicht automatisch abgesagt):', alt[url]['Name'], url)
    for name, felder, url in veraendert:
        print('GEÄNDERT:', name, '| Felder:', ', '.join(felder), '|', url)
    print('\nVorschau gespeichert:', VORSCHAU)
    print('Die bestehende berliner_flohmaerkte.csv und die JSON-Datei bleiben unverändert.')
    print('Änderungen sind Hinweise, keine bestätigten Termine oder Absagen.')


if __name__ == '__main__':
    try:
        main()
    except Exception as fehler:
        print('\nFEHLER:', fehler, file=sys.stderr)
        sys.exit(1)
