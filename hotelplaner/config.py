"""Konfiguration laden/speichern.

Die Konfiguration liegt in ``config.json`` im Projektverzeichnis. Diese Datei
wird NICHT eingecheckt (siehe .gitignore), weil sie API-Key und SMTP-Passwort
enthalten kann. Der Anthropic-API-Key kann alternativ über die
Umgebungsvariable ANTHROPIC_API_KEY gesetzt werden – diese hat Vorrang.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "anthropic_api_key": "",
    "model": "claude-haiku-4-5",
    "sender_name": "",
    "sender_contact": "",
    "self_email": "",
    "smtp": {
        "host": "",
        "port": 587,
        "user": "",
        "password": "",
        "use_tls": True,
        "from_email": "",
    },
}


def load_config() -> dict:
    """Konfiguration aus config.json laden und mit Defaults zusammenführen."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # tiefe Kopie
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            stored = {}
        for key, value in stored.items():
            if key == "smtp" and isinstance(value, dict):
                cfg["smtp"].update(value)
            else:
                cfg[key] = value
    return cfg


def save_config(new_values: dict) -> dict:
    """Konfiguration aktualisieren und speichern. Gibt die neue Config zurück."""
    cfg = load_config()
    for key, value in new_values.items():
        if key == "smtp" and isinstance(value, dict):
            cfg["smtp"].update(value)
        else:
            cfg[key] = value
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return cfg


def get_api_key() -> str:
    """API-Key: Umgebungsvariable hat Vorrang vor config.json."""
    return os.environ.get("ANTHROPIC_API_KEY") or load_config().get(
        "anthropic_api_key", ""
    )


def get_model() -> str:
    return load_config().get("model") or "claude-haiku-4-5"


def public_config() -> dict:
    """Konfiguration für die Anzeige im UI – Geheimnisse werden maskiert."""
    cfg = load_config()
    cfg = json.loads(json.dumps(cfg))
    # Key aus Umgebung berücksichtigen, aber nie im Klartext ausliefern
    cfg["anthropic_api_key_set"] = bool(get_api_key())
    cfg["anthropic_api_key"] = ""
    cfg["smtp"]["password_set"] = bool(cfg["smtp"].get("password"))
    cfg["smtp"]["password"] = ""
    return cfg
