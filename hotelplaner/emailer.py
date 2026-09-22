"""E-Mail: Anfrage-Texte erzeugen (Vorschau) und per SMTP versenden.

Die Anfrage-Texte werden per Vorlage (Template) erzeugt – das ist kostenlos und
deterministisch, es entstehen keine KI-Kosten. Personalisiert wird pro Hotel über
Name, Region und Merkmale.

Der Versand nutzt das eigene E-Mail-Konto des Nutzers per SMTP (z. B. Gmail mit
App-Passwort). Kostenlos, keine externen Dienste.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from . import config


def build_email(hotel: dict, req: dict) -> dict:
    """Erzeugt Betreff + Text einer personalisierten Anfrage für ein Hotel."""
    cfg = config.load_config()
    sender_name = cfg.get("sender_name") or "—"
    sender_contact = cfg.get("sender_contact") or ""

    name = hotel.get("name") or "Ihr Haus"
    region = hotel.get("region") or ""
    features = hotel.get("features") or []

    von = req.get("von") or "—"
    bis = req.get("bis") or "—"
    personen = req.get("personen") or "—"
    kinder = (req.get("kinder") or "").strip()
    extra = (req.get("extra") or "").strip()

    subject = f"Angebotsanfrage {von} – {bis} für {personen} Personen"

    region_part = f" in {region}" if region else ""
    lines = [
        f"Sehr geehrtes Team des {name},",
        "",
        f"wir interessieren uns für einen Aufenthalt in Ihrem Haus{region_part} "
        "und möchten gerne ein unverbindliches Angebot anfragen.",
        "",
        f"Reisezeitraum: {von} bis {bis}",
        f"Personen: {personen}",
    ]
    if kinder:
        lines.append(f"Kinder / Alter: {kinder}")
    if features:
        lines.append("")
        lines.append(
            "Besonders schätzen wir an Ihrem Haus: " + ", ".join(features) + "."
        )
    if extra:
        lines.append("")
        lines.append(extra)
    lines += [
        "",
        "Könnten Sie uns bitte Ihre Verfügbarkeit, passende Zimmerkategorien, "
        "Preise und die enthaltenen Leistungen (z. B. Verpflegung) mitteilen?",
        "",
        "Vielen Dank im Voraus – wir freuen uns auf Ihre Rückmeldung.",
        "",
        "Mit freundlichen Grüßen",
        sender_name,
    ]
    if sender_contact:
        lines.append(sender_contact)

    return {
        "hotel_id": hotel.get("id"),
        "hotel_name": name,
        "to_email": hotel.get("email") or "",
        "subject": subject,
        "body": "\n".join(lines),
    }


def send_email(to_email: str, subject: str, body: str) -> None:
    """Versendet eine E-Mail per SMTP. Wirft bei Fehler eine Exception."""
    cfg = config.load_config()
    smtp = cfg.get("smtp", {})
    host = smtp.get("host")
    port = int(smtp.get("port") or 587)
    user = smtp.get("user")
    password = smtp.get("password")
    from_email = smtp.get("from_email") or user
    use_tls = smtp.get("use_tls", True)

    if not host or not from_email:
        raise RuntimeError(
            "SMTP ist nicht konfiguriert. Bitte in den Einstellungen Host und "
            "Absender-Adresse hinterlegen."
        )
    if not to_email:
        raise RuntimeError("Keine Empfänger-Adresse vorhanden.")

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


def send_summary_to_self(subject: str, body: str) -> None:
    """Sendet eine Zusammenfassung an die eigene Adresse (self_email)."""
    cfg = config.load_config()
    self_email = cfg.get("self_email") or cfg.get("smtp", {}).get("from_email")
    if not self_email:
        raise RuntimeError(
            "Keine eigene E-Mail-Adresse (self_email) in den Einstellungen "
            "hinterlegt."
        )
    send_email(self_email, subject, body)
