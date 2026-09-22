"""IMAP: Angebots-Antworten direkt aus dem eigenen Postfach abrufen.

Nutzt das eigene Postfach des Nutzers (z. B. Gmail mit App-Passwort) per IMAP –
kostenlos, keine externen Dienste. Es werden nur E-Mails gelesen; nichts wird
gelöscht oder verschickt.
"""

from __future__ import annotations

import email
import imaplib
from email.header import decode_header, make_header
from email.utils import parseaddr

from bs4 import BeautifulSoup

from . import config

MAX_BODY_CHARS = 12000


class IMAPError(RuntimeError):
    """Fehler beim IMAP-Zugriff (z. B. fehlende Konfiguration, Login)."""


def _decode(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return str(value)


def _body_text(msg: email.message.Message) -> str:
    """Extrahiert den Textkörper – bevorzugt text/plain, sonst text/html bereinigt."""
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:  # noqa: BLE001
                continue
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                decoded = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain" and not plain:
                plain = decoded
            elif ctype == "text/html" and not html:
                html = decoded
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        if payload:
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html = text
            else:
                plain = text

    if plain.strip():
        body = plain
    elif html.strip():
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        body = soup.get_text(separator="\n")
    else:
        body = ""

    lines = [ln.strip() for ln in body.splitlines()]
    body = "\n".join(ln for ln in lines if ln)
    return body[:MAX_BODY_CHARS]


def fetch_recent(limit: int = 15, unseen_only: bool = False) -> list[dict]:
    """Liest die letzten E-Mails aus dem konfigurierten Postfach.

    Gibt eine Liste von Dicts mit uid, from_email, from_name, subject, date, body.
    Markierungen (gelesen/ungelesen) werden nicht verändert (BODY.PEEK).
    """
    cfg = config.load_config().get("imap", {})
    host = cfg.get("host")
    user = cfg.get("user")
    password = cfg.get("password")
    port = int(cfg.get("port") or 993)
    folder = cfg.get("folder") or "INBOX"
    use_ssl = cfg.get("use_ssl", True)

    if not host or not user or not password:
        raise IMAPError(
            "IMAP ist nicht vollständig konfiguriert. Bitte Host, Benutzer und "
            "Passwort in den Einstellungen hinterlegen."
        )

    try:
        conn = (
            imaplib.IMAP4_SSL(host, port)
            if use_ssl
            else imaplib.IMAP4(host, port)
        )
    except Exception as exc:  # noqa: BLE001
        raise IMAPError(f"Verbindung zum IMAP-Server fehlgeschlagen: {exc}") from exc

    try:
        try:
            conn.login(user, password)
        except imaplib.IMAP4.error as exc:
            raise IMAPError(f"IMAP-Login fehlgeschlagen: {exc}") from exc

        conn.select(folder, readonly=True)
        criterion = "UNSEEN" if unseen_only else "ALL"
        typ, data = conn.uid("search", None, criterion)
        if typ != "OK":
            raise IMAPError("IMAP-Suche fehlgeschlagen.")

        uids = data[0].split()
        uids = uids[-limit:][::-1]  # neueste zuerst

        results = []
        for uid in uids:
            typ, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            from_name, from_email = parseaddr(_decode(msg.get("From")))
            results.append(
                {
                    "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "from_email": (from_email or "").lower(),
                    "from_name": from_name or "",
                    "subject": _decode(msg.get("Subject")),
                    "date": _decode(msg.get("Date")),
                    "body": _body_text(msg),
                }
            )
        return results
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
