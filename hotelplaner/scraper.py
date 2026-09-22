"""Web-Scraping: Hotel-Webseite holen und in sauberen Text umwandeln.

Nur Standard-HTTP (requests) + BeautifulSoup. Kostenlos, keine externen Dienste.
Der extrahierte Text wird an die KI übergeben, deshalb wird er auf eine sinnvolle
Länge gekürzt, um Token-Kosten gering zu halten.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\"')]+")

MAX_TEXT_CHARS = 8000


def fetch_page(url: str, timeout: int = 20) -> dict:
    """Lädt eine Seite und gibt title, text und gefundene E-Mails zurück.

    Wirft requests.RequestException bei Netzwerkfehlern.
    """
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.8"},
        timeout=timeout,
    )
    resp.raise_for_status()
    html = resp.text

    soup = BeautifulSoup(html, "html.parser")

    # E-Mails auch aus mailto-Links gewinnen (zuverlässiger als reiner Text)
    emails = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip()
            if addr:
                emails.add(addr)

    title = soup.title.get_text(strip=True) if soup.title else ""

    # Störende Elemente entfernen
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # Whitespace normalisieren
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = re.sub(r"\n{3,}", "\n\n", text)

    emails.update(EMAIL_RE.findall(text))

    return {
        "title": title,
        "text": text[:MAX_TEXT_CHARS],
        "emails": sorted(emails),
        "truncated": len(text) > MAX_TEXT_CHARS,
    }


def extract_urls(text: str) -> list[str]:
    """Alle http(s)-Links aus einem Text ziehen (für Angebots-Mails mit Links)."""
    seen: list[str] = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".,);]")
        if u not in seen:
            seen.append(u)
    return seen
