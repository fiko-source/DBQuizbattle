"""Erzeugung, Validierung und Speicherung eindeutiger Server-UUIDs.

Jeder Server braucht eine stabile Identitaet fuer den logischen Ring und die
LCR-Leaderwahl. Diese Datei sorgt dafuer, dass ein Server beim ersten Start eine
UUID bekommt und beim naechsten Start dieselbe UUID wiederverwendet.
"""

import os
import uuid
from pathlib import Path


def normalize_uuid(value):
    """Pruefe einen UUID-Wert und gib seine kanonische Textform zurueck.

    Dadurch akzeptieren wir nur echte UUIDs. Ungueltige Werte wuerden sonst den
    Ringvergleich oder die Leaderwahl kaputtmachen.
    """
    return str(uuid.UUID(str(value)))


def uuid_order_key(value):
    """Wandle eine UUID fuer Ring-Sortierung und LCR-Vergleiche in eine Zahl um.

    LCR braucht eine eindeutige Ordnung der Server. Wir vergleichen deshalb den
    numerischen 128-Bit-Wert der UUID und nicht die Textdarstellung.
    """
    return uuid.UUID(normalize_uuid(value)).int


def load_or_create_uuid(identity_file):
    """Lade eine dauerhafte UUID oder erzeuge und speichere sie beim ersten Start.

    Die Identity-Datei macht die UUID persistent. Wenn ein Server abstuerzt und
    spaeter neu startet, tritt er mit derselben Identitaet wieder in den Ring
    ein.
    """
    path = Path(identity_file)
    if path.exists():
        # Existiert die Datei bereits, ist dies ein Neustart derselben
        # Serverinstanz. Dann wird keine neue UUID erzeugt.
        return normalize_uuid(path.read_text(encoding="utf-8").strip())

    path.parent.mkdir(parents=True, exist_ok=True)
    generated = str(uuid.uuid4())

    # O_EXCL verhindert, dass zwei gleichzeitig startende Prozesse dieselbe
    # Identitaetsdatei unbemerkt ueberschreiben. Ohne diesen Schutz koennten
    # zwei Prozesse glauben, sie haetten erfolgreich eine neue Identitaet
    # geschrieben.
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return normalize_uuid(path.read_text(encoding="utf-8").strip())

    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"{generated}\n")
    return generated
