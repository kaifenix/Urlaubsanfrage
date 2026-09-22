"""KI-Anbindung an die Claude-API.

Zwei Aufgaben:
1. Aus dem Text einer Hotel-Webseite strukturierte Felder extrahieren.
2. Aus einer Angebots-Antwort (Mail-Text + evtl. verlinkte Seiten) ein oder
   mehrere Angebote als strukturierte Daten extrahieren.

Es wird bewusst das günstigste Modell (Claude Haiku 4.5) als Standard genutzt –
Extraktion ist eine einfache Aufgabe, für die Haiku gut geeignet und sehr
kostengünstig ist. Das Modell ist in den Einstellungen änderbar.

Grundprinzip: Unsichere Felder bleiben leer (null) statt geraten zu werden.
"""

from __future__ import annotations

import json
import re

from . import config


class AIError(RuntimeError):
    """Fehler bei der KI-Nutzung (z. B. fehlender API-Key)."""


def _client():
    api_key = config.get_api_key()
    if not api_key:
        raise AIError(
            "Kein Anthropic-API-Key hinterlegt. Bitte in den Einstellungen "
            "eintragen oder die Umgebungsvariable ANTHROPIC_API_KEY setzen."
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise AIError(
            "Paket 'anthropic' nicht installiert. Bitte 'pip install -r "
            "requirements.txt' ausführen."
        ) from exc
    return anthropic.Anthropic(api_key=api_key)


def _call(system: str, user: str, max_tokens: int = 2000) -> str:
    client = _client()
    model = config.get_model()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as exc:  # anthropic-Fehler nutzerfreundlich weiterreichen
        raise AIError(f"Claude-API-Fehler: {exc}") from exc

    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def _parse_json(raw: str):
    """JSON aus der Antwort robust extrahieren (auch wenn Text drumherum steht)."""
    raw = raw.strip()
    # ```json ... ``` Zäune entfernen
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Ersten JSON-Block (Objekt oder Array) suchen
    for opener, closer in (("[", "]"), ("{", "}")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise AIError("Antwort der KI war kein gültiges JSON:\n" + raw[:500])


# --------------------------------------------------------------------------
# 1) Hoteldaten aus Webseite extrahieren
# --------------------------------------------------------------------------

HOTEL_SYSTEM = """Du extrahierst strukturierte Stammdaten eines Hotels aus dem \
Text einer Hotel-Webseite. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, ohne \
weitere Erklärung.

Felder:
- "name": Name des Hotels (String) oder null.
- "ort": Ort/Gemeinde (String) oder null.
- "region": Urlaubs-/Ferienregion, z. B. "Südtirol", "Toskana", "Allgäu" \
(String) oder null.
- "email": Kontakt-E-Mail-Adresse für Anfragen (String) oder null.
- "features": Array von Merkmalen als kurze deutsche Schlagworte, z. B. \
"Adults Only", "Wellness/Spa", "Pool", "Halbpension", "Familienfreundlich", \
"Hund erlaubt", "Bergblick". Leeres Array, wenn nichts sicher erkennbar ist.

WICHTIG: Rate nichts. Wenn ein Wert nicht eindeutig aus dem Text hervorgeht, \
setze null (bzw. leeres Array bei features). Erfinde keine E-Mail-Adressen. \
Setze "Adults Only" nur, wenn das Hotel ausdrücklich Erwachsenen-/kinderfrei ist."""


def extract_hotel(page_text: str, url: str, found_emails: list[str] | None = None) -> dict:
    hint = ""
    if found_emails:
        hint = (
            "\n\nAuf der Seite gefundene E-Mail-Adressen (nutze die für Anfragen "
            "passendste, sonst null): " + ", ".join(found_emails)
        )
    user = f"URL: {url}\n\nSeitentext:\n{page_text}{hint}"
    data = _parse_json(_call(HOTEL_SYSTEM, user, max_tokens=1200))

    if not isinstance(data, dict):
        raise AIError("Unerwartetes Format der KI-Antwort (Hotel).")

    def clean(v):
        return v.strip() if isinstance(v, str) and v.strip() else ""

    features = data.get("features") or []
    if not isinstance(features, list):
        features = []
    features = [str(f).strip() for f in features if str(f).strip()]

    return {
        "name": clean(data.get("name")),
        "ort": clean(data.get("ort")),
        "region": clean(data.get("region")),
        "email": clean(data.get("email")),
        "features": features,
    }


# --------------------------------------------------------------------------
# 2) Angebote aus Antwort-Mail extrahieren
# --------------------------------------------------------------------------

OFFER_SYSTEM = """Du extrahierst Hotel-Angebote aus dem Text einer E-Mail-Antwort \
(und ggf. daraus verlinkten Seiten). Eine E-Mail kann MEHRERE Angebote enthalten \
(z. B. verschiedene Zimmer, Zeiträume oder Pakete) – gib dann mehrere Einträge zurück.

Antworte AUSSCHLIESSLICH mit einem JSON-Array von Objekten, ohne weitere Erklärung. \
Jedes Objekt hat die Felder:
- "price": Gesamtpreis des Angebots als Zahl (nur Ziffern, kein Währungszeichen) \
oder null.
- "currency": Währungscode, z. B. "EUR", Standard "EUR".
- "von": Anreisedatum im Format YYYY-MM-DD oder null.
- "bis": Abreisedatum im Format YYYY-MM-DD oder null.
- "naechte": Anzahl Nächte als Zahl oder null.
- "personen": Anzahl Personen als Zahl oder null.
- "zimmer": Zimmer-/Kategoriebezeichnung (String) oder "".
- "verpflegung": z. B. "Halbpension", "Frühstück", "All Inclusive" oder "".
- "leistungen": enthaltene Leistungen als kurzer String (mit Komma getrennt) oder "".
- "storno": Stornobedingungen als kurzer String oder "".
- "notes": sonstige wichtige Hinweise als kurzer String oder "".

WICHTIG: Rate nichts. Wenn ein Wert nicht eindeutig hervorgeht, setze null bzw. "". \
Der Preis muss der tatsächlich genannte Gesamtpreis sein; rechne nichts hoch."""


def extract_offers(email_text: str, linked_pages: list[dict] | None = None) -> list[dict]:
    parts = [f"E-Mail-Text:\n{email_text}"]
    for page in linked_pages or []:
        parts.append(
            f"\n--- Inhalt von {page.get('url', '')} ---\n{page.get('text', '')}"
        )
    user = "\n".join(parts)

    data = _parse_json(_call(OFFER_SYSTEM, user, max_tokens=3000))

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise AIError("Unerwartetes Format der KI-Antwort (Angebote).")

    offers = []
    for item in data:
        if not isinstance(item, dict):
            continue

        def num(key):
            v = item.get(key)
            if isinstance(v, (int, float)):
                return v
            if isinstance(v, str):
                m = re.search(r"-?\d+(?:[.,]\d+)?", v)
                if m:
                    return float(m.group(0).replace(".", "").replace(",", "."))
            return None

        def s(key):
            v = item.get(key)
            return v.strip() if isinstance(v, str) else ""

        offers.append(
            {
                "price": num("price"),
                "currency": s("currency") or "EUR",
                "von": s("von"),
                "bis": s("bis"),
                "naechte": int(num("naechte")) if num("naechte") else None,
                "personen": int(num("personen")) if num("personen") else None,
                "zimmer": s("zimmer"),
                "verpflegung": s("verpflegung"),
                "leistungen": s("leistungen"),
                "storno": s("storno"),
                "notes": s("notes"),
            }
        )
    return offers
