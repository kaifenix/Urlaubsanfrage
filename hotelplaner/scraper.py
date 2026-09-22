"""Web-Scraping: Hotel-Webseite holen und in sauberen Text umwandeln.

Standardweg: requests + BeautifulSoup (kostenlos, sehr schnell).

Fallback für JavaScript-lastige Seiten: Playwright (kostenlos, lokal). Wird nur
genutzt, wenn Playwright installiert ist und der Render-Modus es erlaubt. Ist
Playwright nicht vorhanden, funktioniert alles weiter – nur ohne Rendering.

Render-Modus (in den Einstellungen):
  "auto"   – statisch laden, bei zu wenig Text zusätzlich rendern (Standard)
  "always" – immer rendern (falls Playwright installiert)
  "never"  – nie rendern
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from . import config

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\"')]+")

MAX_TEXT_CHARS = 8000
# Unter dieser Textmenge gilt eine Seite im Modus "auto" als vermutlich
# JavaScript-gerendert und wird zusätzlich mit Playwright geladen.
RENDER_THRESHOLD = 400


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _static_html(url: str, timeout: int = 20) -> str:
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.8"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def _rendered_html(url: str, timeout: int = 30) -> str:
    """Lädt die Seite mit einem echten Browser (Playwright) und gibt HTML zurück."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            html = page.content()
        finally:
            browser.close()
    return html


def _parse_html(html: str, base_soup_emails: bool = True) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    emails = set()
    if base_soup_emails:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().startswith("mailto:"):
                addr = href[7:].split("?")[0].strip()
                if addr:
                    emails.add(addr)

    title = soup.title.get_text(strip=True) if soup.title else ""

    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = re.sub(r"\n{3,}", "\n\n", text)

    emails.update(EMAIL_RE.findall(text))

    return {"title": title, "text": text, "emails": sorted(emails)}


def fetch_page(url: str, timeout: int = 20) -> dict:
    """Lädt eine Seite und gibt title, text und gefundene E-Mails zurück.

    Nutzt je nach Render-Modus und Textmenge Playwright als Fallback.
    Wirft requests.RequestException bei Netzwerkfehlern des statischen Ladens.
    """
    mode = config.load_config().get("render_mode", "auto")
    can_render = playwright_available() and mode != "never"

    result = {"title": "", "text": "", "emails": [], "rendered": False}

    if mode == "always" and can_render:
        try:
            parsed = _parse_html(_rendered_html(url, timeout))
            result.update(parsed, rendered=True)
        except Exception:  # noqa: BLE001 – auf statisch zurückfallen
            result.update(_parse_html(_static_html(url, timeout)))
    else:
        result.update(_parse_html(_static_html(url, timeout)))
        # Fallback: zu wenig Text -> mit Playwright rendern
        if mode == "auto" and can_render and len(result["text"]) < RENDER_THRESHOLD:
            try:
                parsed = _parse_html(_rendered_html(url, timeout))
                if len(parsed["text"]) > len(result["text"]):
                    result.update(parsed, rendered=True)
            except Exception:  # noqa: BLE001 – statisches Ergebnis behalten
                pass

    result["truncated"] = len(result["text"]) > MAX_TEXT_CHARS
    result["text"] = result["text"][:MAX_TEXT_CHARS]
    return result


def extract_urls(text: str) -> list[str]:
    """Alle http(s)-Links aus einem Text ziehen (für Angebots-Mails mit Links)."""
    seen: list[str] = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".,);]")
        if u not in seen:
            seen.append(u)
    return seen
