"""Hotel-Urlaubsplaner – lokale Flask-App (Prototyp).

Starten:
    python app.py
Danach im Browser öffnen: http://127.0.0.1:5000

Alles läuft lokal. Einzige (nutzungsabhängige) Kosten: die Claude-API für die
KI-Extraktion.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from flask import Flask, jsonify, request, send_from_directory

from hotelplaner import ai, config, db, emailer, scraper

app = Flask(__name__, static_folder="static", static_url_path="/static")
db.init_db()


# ---------------------------------------------------------------- Helpers ----

def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _parse_date(value: str):
    """Versucht ISO (YYYY-MM-DD) und dd.mm.yyyy zu parsen. Gibt date oder None."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _nights(von: str, bis: str):
    d1, d2 = _parse_date(von), _parse_date(bis)
    if d1 and d2 and d2 > d1:
        return (d2 - d1).days
    return None


def _enrich_offer(o: dict) -> dict:
    """Abgeleitete Felder für die Vergleichstabelle berechnen."""
    o = dict(o)
    naechte = o.get("naechte") or _nights(o.get("von", ""), o.get("bis", ""))
    o["naechte"] = naechte
    price = o.get("price")
    personen = o.get("personen")
    o["price_per_night"] = round(price / naechte, 2) if price and naechte else None
    if price and naechte and personen:
        o["price_per_person_night"] = round(price / naechte / personen, 2)
    else:
        o["price_per_person_night"] = None
    return o


# ------------------------------------------------------------------ Views ----

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


# ---------------- Hotels ----------------

@app.route("/api/hotels", methods=["GET"])
def list_hotels():
    region = (request.args.get("region") or "").strip()
    tag = (request.args.get("tag") or "").strip()
    rows = db.query("SELECT * FROM hotels ORDER BY name COLLATE NOCASE")
    hotels = [db.hotel_to_dict(r) for r in rows]
    if region:
        hotels = [h for h in hotels if h["region"].lower() == region.lower()]
    if tag:
        hotels = [
            h for h in hotels if any(tag.lower() == f.lower() for f in h["features"])
        ]
    return jsonify(hotels)


@app.route("/api/hotels/facets", methods=["GET"])
def hotel_facets():
    """Verfügbare Regionen und Merkmale (Tags) für die Filter."""
    rows = db.query("SELECT region, features FROM hotels")
    regions, tags = set(), set()
    for r in rows:
        if r["region"]:
            regions.add(r["region"])
        try:
            for f in json.loads(r["features"] or "[]"):
                if f:
                    tags.add(f)
        except json.JSONDecodeError:
            pass
    return jsonify(
        {"regions": sorted(regions, key=str.lower), "tags": sorted(tags, key=str.lower)}
    )


@app.route("/api/hotels/extract", methods=["POST"])
def extract_hotel():
    """Aus einer URL Hoteldaten ziehen (noch NICHT speichern – zur Prüfung)."""
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return _json_error("Bitte eine URL angeben.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        page = scraper.fetch_page(url)
    except Exception as exc:  # noqa: BLE001 – Netzwerkfehler nutzerfreundlich melden
        return _json_error(f"Seite konnte nicht geladen werden: {exc}", 502)

    try:
        extracted = ai.extract_hotel(page["text"], url, page.get("emails"))
    except ai.AIError as exc:
        # KI nicht verfügbar: Grunddaten trotzdem zurückgeben, Rest leer lassen
        return jsonify(
            {
                "url": url,
                "name": page.get("title", ""),
                "ort": "",
                "region": "",
                "email": (page.get("emails") or [""])[0],
                "features": [],
                "warning": str(exc),
            }
        )

    extracted["url"] = url
    return jsonify(extracted)


@app.route("/api/hotels", methods=["POST"])
def create_hotel():
    d = request.get_json(force=True, silent=True) or {}
    hid = db.execute(
        """INSERT INTO hotels (name, url, ort, region, email, features, notes, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            (d.get("name") or "").strip(),
            (d.get("url") or "").strip(),
            (d.get("ort") or "").strip(),
            (d.get("region") or "").strip(),
            (d.get("email") or "").strip(),
            json.dumps(d.get("features") or [], ensure_ascii=False),
            (d.get("notes") or "").strip(),
            db.now_iso(),
        ),
    )
    row = db.query("SELECT * FROM hotels WHERE id=?", (hid,), one=True)
    return jsonify(db.hotel_to_dict(row)), 201


@app.route("/api/hotels/<int:hid>", methods=["PUT"])
def update_hotel(hid):
    d = request.get_json(force=True, silent=True) or {}
    exists = db.query("SELECT id FROM hotels WHERE id=?", (hid,), one=True)
    if not exists:
        return _json_error("Hotel nicht gefunden.", 404)
    db.execute(
        """UPDATE hotels SET name=?, url=?, ort=?, region=?, email=?, features=?,
           notes=? WHERE id=?""",
        (
            (d.get("name") or "").strip(),
            (d.get("url") or "").strip(),
            (d.get("ort") or "").strip(),
            (d.get("region") or "").strip(),
            (d.get("email") or "").strip(),
            json.dumps(d.get("features") or [], ensure_ascii=False),
            (d.get("notes") or "").strip(),
            hid,
        ),
    )
    row = db.query("SELECT * FROM hotels WHERE id=?", (hid,), one=True)
    return jsonify(db.hotel_to_dict(row))


@app.route("/api/hotels/<int:hid>", methods=["DELETE"])
def delete_hotel(hid):
    db.execute("DELETE FROM hotels WHERE id=?", (hid,))
    return jsonify({"ok": True})


# ---------------- Anfragen (Vorschau + Versand) ----------------

@app.route("/api/requests/preview", methods=["POST"])
def preview_request():
    d = request.get_json(force=True, silent=True) or {}
    hotel_ids = d.get("hotel_ids") or []
    if not hotel_ids:
        return _json_error("Bitte mindestens ein Hotel auswählen.")
    req = {
        "von": (d.get("von") or "").strip(),
        "bis": (d.get("bis") or "").strip(),
        "personen": d.get("personen") or 2,
        "kinder": (d.get("kinder") or "").strip(),
        "extra": (d.get("extra") or "").strip(),
    }
    previews = []
    for hid in hotel_ids:
        row = db.query("SELECT * FROM hotels WHERE id=?", (hid,), one=True)
        if row:
            previews.append(emailer.build_email(db.hotel_to_dict(row), req))
    return jsonify({"request": req, "previews": previews})


@app.route("/api/requests/send", methods=["POST"])
def send_request():
    """Bestätigte Anfragen speichern und per SMTP versenden."""
    d = request.get_json(force=True, silent=True) or {}
    req = d.get("request") or {}
    emails = d.get("emails") or []
    if not emails:
        return _json_error("Keine E-Mails zum Versenden.")

    request_id = db.execute(
        """INSERT INTO requests (created_at, von, bis, personen, kinder, extra, status)
           VALUES (?,?,?,?,?,?,?)""",
        (
            db.now_iso(),
            (req.get("von") or "").strip(),
            (req.get("bis") or "").strip(),
            int(req.get("personen") or 2),
            (req.get("kinder") or "").strip(),
            (req.get("extra") or "").strip(),
            "gesendet",
        ),
    )

    results = []
    for m in emails:
        to_email = (m.get("to_email") or "").strip()
        subject = m.get("subject") or ""
        body = m.get("body") or ""
        status, error = "gesendet", ""
        try:
            emailer.send_email(to_email, subject, body)
        except Exception as exc:  # noqa: BLE001
            status, error = "fehler", str(exc)
        db.execute(
            """INSERT INTO emails (request_id, hotel_id, to_email, subject, body,
               status, sent_at, error) VALUES (?,?,?,?,?,?,?,?)""",
            (
                request_id,
                m.get("hotel_id"),
                to_email,
                subject,
                body,
                status,
                db.now_iso() if status == "gesendet" else None,
                error,
            ),
        )
        results.append(
            {"hotel_name": m.get("hotel_name"), "to_email": to_email,
             "status": status, "error": error}
        )

    return jsonify({"request_id": request_id, "results": results})


# ---------------- Angebote (KI-Auslesen) + Vergleich ----------------

@app.route("/api/offers/parse", methods=["POST"])
def parse_offers():
    """Aus einer Angebots-Mail (Text) Angebote extrahieren – noch nicht speichern."""
    d = request.get_json(force=True, silent=True) or {}
    text = (d.get("text") or "").strip()
    if not text:
        return _json_error("Bitte den Text der Angebots-Mail einfügen.")

    linked_pages = []
    if d.get("follow_links"):
        for url in scraper.extract_urls(text)[:3]:  # max. 3 Links, Kosten begrenzen
            try:
                page = scraper.fetch_page(url)
                linked_pages.append({"url": url, "text": page["text"]})
            except Exception:  # noqa: BLE001 – Link einfach überspringen
                continue

    try:
        offers = ai.extract_offers(text, linked_pages)
    except ai.AIError as exc:
        return _json_error(str(exc), 502)

    return jsonify({"offers": [_enrich_offer(o) for o in offers],
                    "links_followed": [p["url"] for p in linked_pages]})


@app.route("/api/offers", methods=["GET"])
def list_offers():
    rows = db.query(
        """SELECT o.*, h.name AS hotel_name, h.region AS hotel_region
           FROM offers o LEFT JOIN hotels h ON h.id = o.hotel_id
           ORDER BY o.created_at DESC"""
    )
    offers = [_enrich_offer(dict(r)) for r in rows]
    return jsonify(offers)


@app.route("/api/offers", methods=["POST"])
def save_offers():
    """Geprüfte Angebote speichern."""
    d = request.get_json(force=True, silent=True) or {}
    hotel_id = d.get("hotel_id")
    source_url = (d.get("source_url") or "").strip()
    offers = d.get("offers") or []
    saved = []
    for o in offers:
        oid = db.execute(
            """INSERT INTO offers (hotel_id, request_id, created_at, price, currency,
               von, bis, naechte, personen, zimmer, verpflegung, leistungen, storno,
               notes, source_url, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                hotel_id,
                o.get("request_id"),
                db.now_iso(),
                o.get("price"),
                o.get("currency") or "EUR",
                o.get("von") or "",
                o.get("bis") or "",
                o.get("naechte"),
                o.get("personen"),
                o.get("zimmer") or "",
                o.get("verpflegung") or "",
                o.get("leistungen") or "",
                o.get("storno") or "",
                o.get("notes") or "",
                source_url,
                json.dumps(o, ensure_ascii=False),
            ),
        )
        saved.append(oid)
    return jsonify({"saved_ids": saved}), 201


@app.route("/api/offers/<int:oid>", methods=["PUT"])
def update_offer(oid):
    d = request.get_json(force=True, silent=True) or {}
    exists = db.query("SELECT id FROM offers WHERE id=?", (oid,), one=True)
    if not exists:
        return _json_error("Angebot nicht gefunden.", 404)
    db.execute(
        """UPDATE offers SET hotel_id=?, price=?, currency=?, von=?, bis=?, naechte=?,
           personen=?, zimmer=?, verpflegung=?, leistungen=?, storno=?, notes=?
           WHERE id=?""",
        (
            d.get("hotel_id"),
            d.get("price"),
            d.get("currency") or "EUR",
            d.get("von") or "",
            d.get("bis") or "",
            d.get("naechte"),
            d.get("personen"),
            d.get("zimmer") or "",
            d.get("verpflegung") or "",
            d.get("leistungen") or "",
            d.get("storno") or "",
            d.get("notes") or "",
            oid,
        ),
    )
    row = db.query("SELECT * FROM offers WHERE id=?", (oid,), one=True)
    return jsonify(_enrich_offer(dict(row)))


@app.route("/api/offers/<int:oid>", methods=["DELETE"])
def delete_offer(oid):
    db.execute("DELETE FROM offers WHERE id=?", (oid,))
    return jsonify({"ok": True})


@app.route("/api/offers/summary-email", methods=["POST"])
def summary_email():
    """Optionale Zusammenfassungs-Mail an die eigene Adresse senden."""
    rows = db.query(
        """SELECT o.*, h.name AS hotel_name FROM offers o
           LEFT JOIN hotels h ON h.id = o.hotel_id ORDER BY o.price ASC"""
    )
    offers = [_enrich_offer(dict(r)) for r in rows]
    if not offers:
        return _json_error("Keine gespeicherten Angebote vorhanden.")

    priced = [o for o in offers if o.get("price")]
    lines = ["Zusammenfassung deiner Hotel-Angebote", "=" * 40, ""]
    if priced:
        cheapest = min(priced, key=lambda o: o["price"])
        lines.append(
            f"Günstigstes Angebot: {cheapest.get('hotel_name') or '—'} – "
            f"{cheapest['price']:.0f} {cheapest.get('currency', 'EUR')}"
        )
        lines.append("")
    for o in offers:
        price = f"{o['price']:.0f} {o.get('currency', 'EUR')}" if o.get("price") else "Preis offen"
        lines.append(f"- {o.get('hotel_name') or '—'}: {price}")
        detail = []
        if o.get("von") or o.get("bis"):
            detail.append(f"{o.get('von', '?')} bis {o.get('bis', '?')}")
        if o.get("zimmer"):
            detail.append(o["zimmer"])
        if o.get("verpflegung"):
            detail.append(o["verpflegung"])
        if o.get("price_per_night"):
            detail.append(f"{o['price_per_night']:.0f}/Nacht")
        if detail:
            lines.append("  " + " · ".join(detail))

    try:
        emailer.send_summary_to_self("Deine Hotel-Angebote im Überblick", "\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        return _json_error(str(exc), 502)
    return jsonify({"ok": True})


# ---------------- Einstellungen ----------------

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(config.public_config())


@app.route("/api/settings", methods=["POST"])
def save_settings():
    d = request.get_json(force=True, silent=True) or {}
    update = {}
    for key in ("model", "sender_name", "sender_contact", "self_email"):
        if key in d:
            update[key] = d[key]
    # API-Key nur überschreiben, wenn ein neuer (nicht-leerer) Wert kommt
    if d.get("anthropic_api_key"):
        update["anthropic_api_key"] = d["anthropic_api_key"]
    if isinstance(d.get("smtp"), dict):
        smtp = {k: v for k, v in d["smtp"].items() if k != "password" or v}
        update["smtp"] = smtp
    config.save_config(update)
    return jsonify(config.public_config())


if __name__ == "__main__":
    print("Hotel-Urlaubsplaner läuft auf http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
