"""Erzeugung, Validierung und Speicherung eindeutiger Server-UUIDs."""

import os
import uuid
from pathlib import Path


def normalize_uuid(value):
    """Pruefe einen UUID-Wert und gib seine kanonische Textform zurueck."""
    return str(uuid.UUID(str(value)))


def uuid_order_key(value):
    """Wandle eine UUID fuer Ring-Sortierung und LCR-Vergleiche in eine Zahl um."""
    return uuid.UUID(normalize_uuid(value)).int


def load_or_create_uuid(identity_file):
    """Lade eine dauerhafte UUID oder erzeuge und speichere sie beim ersten Start."""
    path = Path(identity_file)
    if path.exists():
        return normalize_uuid(path.read_text(encoding="utf-8").strip())

    path.parent.mkdir(parents=True, exist_ok=True)
    generated = str(uuid.uuid4())

    # O_EXCL verhindert, dass zwei gleichzeitig startende Prozesse dieselbe
    # Identitaetsdatei unbemerkt ueberschreiben.
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return normalize_uuid(path.read_text(encoding="utf-8").strip())

    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"{generated}\n")
    return generated
