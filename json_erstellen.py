import csv
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ORDNER = Path(__file__).resolve().parent
CSV_DATEI = ORDNER / 'berliner_flohmaerkte.csv'
JSON_DATEI = ORDNER / 'maerkte_berlin.json'

MONATE = {'januar':1,'februar':2,'märz':3,'maerz':3,'april':4,'mai':5,'juni':6,'juli':7,'august':8,'september':9,'oktober':10,'november':11,'dezember':12}
MONATS_REGEX = r'(?:Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)'
WOCHENTAGE = {'montag':0,'dienstag':1,'mittwoch':2,'donnerstag':3,'freitag':4,'samstag':5,'sonntag':6}


def datum(jahr, monat, tag):
    try:
        return date(int(jahr), int(monat), int(tag))
    except ValueError:
        return None


def ostersonntag(jahr):
    a = jahr % 19
    b = jahr // 100
    c = jahr % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat = (h + l - 7 * m + 114) // 31
    tag = ((h + l - 7 * m + 114) % 31) + 1
    return date(jahr, monat, tag)


def totensonntag(jahr):
    weihnachten = date(jahr, 12, 25)
    vierter_advent = weihnachten - timedelta(days=(weihnachten.weekday() + 1) % 7)
    return vierter_advent - timedelta(days=28)


def volkstrauertag(jahr):
    return totensonntag(jahr) - timedelta(days=7)


def feiertage_berlin(jahr):
    ostern = ostersonntag(jahr)
    return {
        date(jahr, 1, 1), date(jahr, 3, 8),
        ostern - timedelta(days=2),
        ostern + timedelta(days=1),
        date(jahr, 5, 1),
        ostern + timedelta(days=39),
        ostern + timedelta(days=50),
        date(jahr, 10, 3),
        date(jahr, 12, 25), date(jahr, 12, 26),
    }


def erkenne_wochentage(text):
    text = text.lower()
    return [nummer for name, nummer in WOCHENTAGE.items() if re.search(r'\b' + name + r'\b', text)]


def erkenne_numerische_daten(text):
    daten = set()
    paar = r'\b(\d{1,2})\.\s*(\d{1,2})\.\s*und\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b'
    for t in re.finditer(paar, text, re.I):
        tag1, monat1, tag2, monat2, jahr = map(int, t.groups())
        for tag, monat in ((tag1, monat1), (tag2, monat2)):
            wert = datum(jahr, monat, tag)
            if wert:
                daten.add(wert.isoformat())
    einzeln = r'\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b'
    for t in re.finditer(einzeln, text):
        tag, monat, jahr = map(int, t.groups())
        wert = datum(jahr, monat, tag)
        if wert:
            daten.add(wert.isoformat())
    return daten


def erkenne_datumsbereiche(text, jahr=None):
    daten = set()
    muster = rf'\b(\d{{1,2}})\.\s*bis\s*(\d{{1,2}})\.\s*({MONATS_REGEX})(?:\s+(20\d{{2}}))?\b'
    for t in re.finditer(muster, text, re.I):
        start_tag, ende_tag = int(t.group(1)), int(t.group(2))
        monat = MONATE[t.group(3).lower()]
        jahr_wert = int(t.group(4)) if t.group(4) else jahr
        if jahr_wert is None:
            continue
        start, ende = datum(jahr_wert, monat, start_tag), datum(jahr_wert, monat, ende_tag)
        if start and ende and start <= ende and (ende-start).days <= 31:
            for offset in range((ende-start).days+1):
                daten.add((start+timedelta(days=offset)).isoformat())
    return daten


def erkenne_monatsdaten(text, jahr):
    daten = set()
    muster = rf'\b(\d{{1,2}})\.\s*({MONATS_REGEX})(?:\s+(20\d{{2}}))?\b'
    for t in re.finditer(muster, text, re.I):
        tag, monat = int(t.group(1)), MONATE[t.group(2).lower()]
        verwendetes_jahr = int(t.group(3)) if t.group(3) else jahr
        wert = datum(verwendetes_jahr, monat, tag)
        if wert:
            daten.add(wert.isoformat())
    return daten


def erkenne_einzeltermine(text):
    daten = set()
    # Nur den Abschnitt bis zum nächsten Feld (z.B. Öffnungszeiten) verwenden.
    abschnitte = re.findall(
        r'Termine\s+(20\d{2}):\s*(.*?)(?=\s*\|\s*(?:Öffnungszeiten|Location|Eintritt)\b|$)',
        text, re.I | re.S
    )
    for jahr_text, inhalt in abschnitte:
        if 'noch nicht bekannt' in inhalt.lower():
            continue
        jahr = int(jahr_text)
        daten.update(erkenne_monatsdaten(inhalt, jahr))
        daten.update(erkenne_datumsbereiche(inhalt, jahr))
        daten.update(erkenne_numerische_daten(inhalt))
    return sorted(daten)


def erkenne_ausnahmen(text):
    daten = erkenne_numerische_daten(text)
    muster = rf'\b(\d{{1,2}})\.\s*({MONATS_REGEX})\s+(20\d{{2}})\b'
    for t in re.finditer(muster, text, re.I):
        wert = datum(int(t.group(3)), MONATE[t.group(2).lower()], int(t.group(1)))
        if wert:
            daten.add(wert.isoformat())
    return sorted(daten)


def pruefhinweise(text):
    begriffe = {'totensonntag':'Totensonntag beachten', 'volkstrauertag':'Volkstrauertag beachten',
                'winterpause':'Winterpause beachten', 'weihnachten':'Weihnachtspause beachten',
                'feiertag':'Feiertagsregel prüfen', 'karlshorst':'Karlshorst-Termine abgleichen',
                'sommerzeit':'Sommer-/Winteröffnungszeiten beachten'}
    return [hinweis for begriff, hinweis in begriffe.items() if begriff in text.lower()]


def ausnahme_regeln(name, termine, weitere):
    name = name.lower()
    text = (termine + ' ' + weitere).lower()
    regeln = []
    if 'totensonntag' in text:
        regeln.append('kein_totensonntag')
    if 'volkstrauertag' in text:
        regeln.append('kein_volkstrauertag')
    if 'goerzallee' in name and 'winterpause' in text:
        regeln.append('goerzallee_winterpause')
    if 'fehrbelliner' in name and 'zwischen weihnachten und silvester' in text:
        regeln.append('fehrbelliner_weihnachtspause')
    if 'ostbahnhof' in name and 'karlshorst' in text:
        regeln.append('ostbahnhof_karlshorst_abgleich')
    return regeln


def zusaetzliche_regeln(name, termine):
    text = termine.lower()
    regeln = []
    if 'fehrbelliner' in name.lower() and all(x in text for x in ('ostermontag', 'pfingstmontag', '1. mai')):
        regeln.append('ostermontag_mai1_pfingstmontag')
    if 'bode-museum' in name.lower() and 'feiertag' in text:
        regeln.append('berliner_feiertage')
    return regeln


def verarbeite_markt(zeile):
    name = (zeile.get('Name') or '').strip()
    termine = (zeile.get('Termine') or '').strip()
    weitere = (zeile.get('Weitere Terminangaben') or '').strip()
    regelmaessig = []
    if 'jeden' in termine.lower() or 'samstag und sonntag' in termine.lower():
        regelmaessig = erkenne_wochentage(termine)
    einzeltermine = erkenne_einzeltermine(weitere)
    ausnahmen = erkenne_ausnahmen(termine)
    einzeltermine = sorted(set(einzeltermine) - set(ausnahmen))
    status = ('regelmaessig_ungeprueft' if regelmaessig else
              'einzeltermine_ungeprueft' if einzeltermine else 'termine_unbekannt')
    return {
        'name': name,
        'adresse': (zeile.get('Adresse') or '').strip(),
        'oeffnungszeiten': (zeile.get('Öffnungszeiten') or '').strip(),
        'wochentage': regelmaessig,
        'einzeltermine': einzeltermine,
        'ausnahmen': ausnahmen,
        'ausnahme_regeln': ausnahme_regeln(name, termine, weitere),
        'zusatztermine_regeln': zusaetzliche_regeln(name, termine),
        'pruefhinweise': pruefhinweise(termine + ' ' + weitere),
        'termintext': termine,
        'weitere_terminangaben': weitere,
        'status': status,
        'quelle': (zeile.get('Quelle') or '').strip(),
        'aktualisierung': (zeile.get('Aktualisierung') or '').strip(),
    }


def ist_termin(markt, tag, karlshorst_tage=None):
    """True/False/None: statt unklarer Termine lieber 'unbekannt'."""
    iso = tag.isoformat()
    if iso in markt['ausnahmen']:
        return False
    regeln = markt['ausnahme_regeln']
    if 'kein_totensonntag' in regeln and tag == totensonntag(tag.year):
        return False
    if 'kein_volkstrauertag' in regeln and tag == volkstrauertag(tag.year):
        return False
    if 'goerzallee_winterpause' in regeln:
        beginn = totensonntag(tag.year) if tag.month >= 3 else totensonntag(tag.year - 1)
        if beginn <= tag <= date(beginn.year + 1, 2, 28 if (beginn.year + 1) % 4 else 29):
            return False
    if 'fehrbelliner_weihnachtspause' in regeln and tag.month == 12 and 25 <= tag.day <= 31:
        return False
    if 'ostbahnhof_karlshorst_abgleich' in regeln and tag.weekday() == 6:
        if karlshorst_tage is None:
            return None
        if iso in karlshorst_tage:
            return False
    if iso in markt['einzeltermine']:
        return True
    if tag.weekday() in markt['wochentage']:
        return True
    zusatz = markt['zusatztermine_regeln']
    if 'ostermontag_mai1_pfingstmontag' in zusatz:
        ostern = ostersonntag(tag.year)
        if tag in {ostern+timedelta(days=1), date(tag.year, 5, 1), ostern+timedelta(days=50)}:
            return True
    if 'berliner_feiertage' in zusatz and tag in feiertage_berlin(tag.year):
        return True
    if not markt['wochentage'] and not markt['einzeltermine']:
        return None
    return False


def pruefe_beispiele(maerkte):
    nach_name = {m['name']: m for m in maerkte}
    def markt_gefunden(teil):
        kandidaten = [m for name, m in nach_name.items() if teil.lower() in name.lower()]
        if len(kandidaten) != 1:
            raise ValueError(f'Prüfmarkt nicht eindeutig gefunden: {teil}')
        return kandidaten[0]
    schoeneberg = markt_gefunden('Rathaus Schöneberg')
    ufafabrik = markt_gefunden('ufaFabrik')
    karlshorst = markt_gefunden('Trabrennbahn Karlshorst')
    flowmarkt = markt_gefunden('Schoeneboerg Flowmarkt')
    guetermarkt = markt_gefunden('Gütermarkt')
    goerzallee = markt_gefunden('Goerzallee')
    arkona = markt_gefunden('Arkonaplatz')
    fehrbelliner = markt_gefunden('Fehrbelliner Platz')
    ostbahnhof = markt_gefunden('Ostbahnhof')
    karlshorst_tage = set(karlshorst['einzeltermine'])
    pruefungen = [
        (len(maerkte) == 26, '26 Märkte vorhanden'),
        (len(flowmarkt['einzeltermine']) == 15, 'Schoeneboerg: 15 Einzeltermine'),
        (len(guetermarkt['einzeltermine']) == 5, 'Gütermarkt: 5 Einzeltermine'),
        (len(ufafabrik['einzeltermine']) == 2, 'ufaFabrik: 2 Einzeltermine'),
        (len(karlshorst['einzeltermine']) == 7, 'Karlshorst: 7 Veranstaltungstage'),
        (len(schoeneberg['ausnahmen']) == 4, 'Schöneberg: 4 ausdrückliche Ausnahmen'),
        (ist_termin(schoeneberg, date(2026, 11, 22)) is False, 'Schöneberg am Totensonntag geschlossen'),
        (ist_termin(arkona, date(2026, 11, 22)) is False, 'Arkonaplatz am Totensonntag geschlossen'),
        (ist_termin(goerzallee, date(2026, 12, 6)) is False, 'Goerzallee in Winterpause'),
        (ist_termin(fehrbelliner, date(2026, 12, 27)) is False, 'Fehrbelliner in Weihnachtspause'),
        (ist_termin(ostbahnhof, date(2027, 5, 9), karlshorst_tage) is False, 'Ostbahnhof bei Karlshorst-Termin geschlossen'),
    ]
    for bestanden, beschreibung in pruefungen:
        print(('OK' if bestanden else 'FEHLER') + ': ' + beschreibung)
    if not all(bestanden for bestanden, _ in pruefungen):
        raise ValueError('Terminprüfung fehlgeschlagen. JSON wird nicht ersetzt.')


def main():
    print('MÄRKTE BERLIN – Sicherheitsprüfung\n')
    if not CSV_DATEI.is_file():
        raise FileNotFoundError(f'CSV-Datei fehlt: {CSV_DATEI}')
    with CSV_DATEI.open('r', encoding='utf-8-sig', newline='') as datei:
        maerkte = [verarbeite_markt(zeile) for zeile in csv.DictReader(datei, delimiter=';')]
    if len(maerkte) < 20:
        raise ValueError('Zu wenige Märkte – JSON wird nicht ersetzt.')
    pruefe_beispiele(maerkte)
    ausgabe = {'projekt':'Märkte Berlin', 'version':3,
               'erstellt_am':datetime.now().isoformat(timespec='seconds'),
               'anzahl':len(maerkte), 'maerkte':maerkte}
    zwischen = JSON_DATEI.with_suffix('.json.tmp')
    try:
        with zwischen.open('w', encoding='utf-8') as datei:
            json.dump(ausgabe, datei, ensure_ascii=False, indent=2)
        os.replace(zwischen, JSON_DATEI)
    finally:
        if zwischen.exists():
            zwischen.unlink()
    print(f'\nFERTIG! {len(maerkte)} Märkte. Datei: {JSON_DATEI}')
    print('WICHTIG: Termine sind noch ungeprüft; keine automatische Veröffentlichung.')


try:
    main()
except Exception as fehler:
    print('\nFEHLER:', fehler)
    if not sys.stdin.isatty():
        raise
finally:
    if sys.stdin.isatty():
        input('\nZum Beenden bitte ENTER drücken ...')
