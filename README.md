# 🏔️ Hotel-Urlaubsplaner (lokaler Prototyp)

Ein **lokales** Tool zur Automatisierung deiner Hotel-Urlaubsplanung. Es läuft
komplett auf deinem Rechner – kein Hosting, kein Server, kein Abo. Die einzigen
(nutzungsabhängigen) Kosten entstehen durch die Claude-API für die KI-Extraktion
(siehe [Kosten](#geschätzte-laufende-kosten)).

## Was das Tool kann

1. **Hotel-Datenbank** – Link einfügen → Name, Ort, Region, Kontakt-E-Mail und
   Merkmale (z. B. „Adults Only") werden automatisch ausgelesen. Unsichere Felder
   bleiben leer statt geraten zu werden; alles bleibt jederzeit editierbar.
2. **Tags & Filter** – nach Region und Merkmalen filtern, um eigene Gruppen
   zusammenzustellen (z. B. „nur Südtirol, Adults Only").
3. **Anfragen** – Formular für Zeitraum, Personenzahl und weitere Angaben erzeugt
   personalisierte Angebotsanfragen. **Vor dem Versand: Vorschau aller Mails, die
   du bestätigen musst.**
4. **KI-Auslesen von Antworten** – Angebots-Mail einfügen (optional inkl. Links),
   Claude extrahiert Preis, Zeitraum, Leistungen usw. – auch bei mehreren
   Angeboten pro Mail.
5. **Vergleichstabelle** – automatisch im Tool, das günstigste Angebot ist
   markiert. Optional: Zusammenfassungs-Mail an dich selbst.

## Technik (bewusst kostenlos / günstig gewählt)

| Baustein | Technologie | Kosten |
|---|---|---|
| Oberfläche + Backend | Python + Flask (eine lokale Web-App im Browser) | 0 € |
| Datenbank | SQLite (eine lokale Datei `data.db`) | 0 € |
| Webseiten auslesen | `requests` + `BeautifulSoup` | 0 € |
| KI-Extraktion | Claude API, Modell **Haiku 4.5** (günstigstes) | pay-per-use |
| E-Mail-Versand | dein eigenes Postfach per SMTP (z. B. Gmail App-Passwort) | 0 € |
| Anfrage-Texte | Vorlage/Template (keine KI) | 0 € |

## Installation & Start

Voraussetzung: Python 3.10+.

```bash
cd Urlaubsanfrage

# 1) Virtuelle Umgebung + Abhängigkeiten
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) Starten
python app.py
```

Dann im Browser öffnen: **http://127.0.0.1:5000**

## Einrichtung (einmalig, im Tab „Einstellungen")

- **Anthropic API-Key**: Konto auf <https://console.anthropic.com> anlegen, Key
  erstellen, ins Feld eintragen (oder als Umgebungsvariable `ANTHROPIC_API_KEY`
  setzen – die hat Vorrang). **Tipp:** In der Console unter *Billing → Limits* ein
  monatliches Ausgabenlimit setzen, damit keine Überraschung entsteht.
- **Absender**: dein Name + Kontaktzeile für die Grußformel, eigene E-Mail für die
  Zusammenfassung.
- **E-Mail-Versand (SMTP)**: für Gmail ein
  [App-Passwort](https://myaccount.google.com/apppasswords) erzeugen (nicht das
  normale Passwort) und Host `smtp.gmail.com`, Port `587`, TLS aktiv eintragen.
  Ohne SMTP funktionieren Vorschau und alles andere trotzdem – nur der direkte
  Versand ist dann deaktiviert.

Die Einstellungen landen in `config.json` (lokal, per `.gitignore` vom Git
ausgeschlossen, weil sie Key/Passwort enthalten kann).

## Typischer Ablauf

1. **Hotels** anlegen: URL einfügen → „Auslesen" → prüfen/ergänzen → speichern.
2. **Anfrage**: Reisedaten eingeben, Hotels (gefiltert) auswählen → „Vorschau
   erzeugen" → prüfen → „Alle senden".
3. **Angebote & Vergleich**: eingehende Angebots-Mails einfügen → „Auslesen" →
   prüfen/speichern → Vergleichstabelle zeigt automatisch das günstigste Angebot.

## Geschätzte laufende Kosten

Modell **Claude Haiku 4.5** (Standard): 1,00 $ pro 1 Mio. Input-Tokens,
5,00 $ pro 1 Mio. Output-Tokens. Grobe Praxiswerte:

| Aktion | ca. Kosten |
|---|---|
| 1 Hotel aus Webseite auslesen | ~0,3–0,5 Cent |
| 1 Angebots-Mail auslesen (ohne Links) | ~0,3 Cent |
| 1 Angebots-Mail auslesen (mit bis zu 3 Links) | ~1–1,5 Cent |
| Anfrage-Mails erzeugen & versenden | **0 €** (Vorlage + eigenes Postfach) |
| Webseiten/Scraping | **0 €** |

**Beispiel für eine komplette Urlaubsplanung** (30 Hotels auslesen + 20 Angebote
auswerten): **deutlich unter 0,30 €**. Selbst intensive Nutzung über ein Jahr
bleibt im einstelligen Euro-Bereich. Es gibt **kein Abo** – du zahlst nur die
tatsächliche Nutzung, und mit dem Ausgabenlimit in der Console deckelst du das
Ganze zusätzlich.

> Genauer/teurer geht auch: In den Einstellungen kannst du auf `claude-sonnet-5`
> oder `claude-opus-5` umstellen (ca. 2× bzw. 5× teurer beim Input). Für reine
> Extraktion reicht Haiku aber i. d. R. gut aus.

## Grenzen des Prototyps (mögliche nächste Ausbaustufen)

- **Angebots-Mails werden aktuell manuell eingefügt.** Automatisches Abholen aus
  deinem Postfach ließe sich später per IMAP (dein eigenes Postfach, kostenlos)
  ergänzen.
- **Rein JavaScript-gerenderte Hotelseiten** liefern per einfachem Scraping evtl.
  wenig Text. Bei Bedarf kann man später Playwright (kostenlos, lokal) ergänzen.
- Kein Login/Mehrbenutzer – bewusst, da rein lokal für dich gedacht.

## Projektstruktur

```
app.py                  Flask-App + API-Routen
hotelplaner/
  config.py             Konfiguration laden/speichern
  db.py                 SQLite-Schema + Zugriffe
  scraper.py            Webseite laden & Text extrahieren
  ai.py                 Claude-API: Hotel- & Angebots-Extraktion
  emailer.py            Anfrage-Texte + SMTP-Versand
templates/index.html    Oberfläche (Tabs)
static/style.css        Styling
static/app.js           Frontend-Logik
config.example.json     Vorlage für config.json
```
