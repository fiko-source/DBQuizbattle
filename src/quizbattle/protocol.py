"""Gemeinsame Kodierung fuer UDP-Datagramme und gerahmte TCP-Nachrichten.

In diesem Projekt werden alle Netzwerkdaten als JSON verschickt. UDP liefert
einzelne Datagramme, TCP dagegen nur einen Byte-Strom. Deshalb kapselt dieses
Modul die Unterschiede: JSON-Kodierung, TCP-Laengenheader und UDP-Callback.
"""

import asyncio
import json
import socket
import struct


# Schutzgrenze fuer eingehende TCP-Control-Nachrichten. Ein kaputtes oder
# falsches Paket soll nicht dazu fuehren, dass der Server beliebig viel Speicher
# fuer eine angebliche Nachricht reserviert.
MAX_FRAME_SIZE = 10 * 1024 * 1024


def local_ip():
    """Bestimme die vom Betriebssystem verwendete lokale IPv4-Adresse.

    Diese Funktion ist ein Komfort-Fallback. Fuer echte Demos ist es oft besser,
    die LAN-IP explizit beim Start anzugeben, weil Rechner mehrere Interfaces
    haben koennen, zum Beispiel WLAN, VPN oder Parallels.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Es werden keine Daten gesendet. connect laesst das Betriebssystem nur
        # entscheiden, ueber welche lokale Adresse dieses Ziel erreichbar waere.
        sock.connect(("10.255.255.255", 1))
        ip = sock.getsockname()[0]
        return ip if ip and not ip.startswith("127.") else "127.0.0.1"
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def json_bytes(message):
    """Kodiere ein Dictionary platzsparend als UTF-8-JSON.

    ensure_ascii=False ist wichtig, damit deutsche Texte wie Kategorien oder
    Fragen lesbar und korrekt als UTF-8 verschickt werden.
    """
    return json.dumps(
        message, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def frame_message(message):
    """Setze vor eine TCP-Nachricht ihre Laenge als vier Byte."""
    payload = json_bytes(message)
    # TCP kennt keine Nachrichtengrenzen. Der Laengenkopf sagt dem Empfaenger,
    # wie viele Bytes zu genau einer JSON-Nachricht gehoeren.
    return struct.pack("!I", len(payload)) + payload


async def read_frame(reader):
    """Lese genau eine laengengerahmte JSON-Nachricht aus einem TCP-Stream.

    Erst werden vier Bytes Laenge gelesen, danach exakt so viele Nutzdaten. So
    kann eine einzelne JSON-Nachricht aus dem TCP-Byte-Strom rekonstruiert
    werden.
    """
    header = await reader.readexactly(4)
    length = struct.unpack("!I", header)[0]
    if length > MAX_FRAME_SIZE:
        raise ValueError("Control message is too large")
    payload = await reader.readexactly(length)
    return json.loads(payload.decode("utf-8"))


async def send_frame(writer, message):
    """Sende eine vollstaendige gerahmte Nachricht und leere den Schreibpuffer."""
    writer.write(frame_message(message))
    await writer.drain()


class DatagramProtocol(asyncio.DatagramProtocol):
    """Uebersetze eingehende UDP-Daten in asynchrone Callback-Aufrufe.

    asyncio ruft datagram_received synchron auf. Die eigentliche Verarbeitung
    darf aber async sein, deshalb wird unten ein Task im Event-Loop erstellt.
    """

    def __init__(self, callback):
        """Speichere die Funktion, die gueltige Datagramme verarbeitet."""
        self.callback = callback

    def datagram_received(self, data, address):
        """Dekodiere ein Datagramm und ignoriere ungueltige Fremdpakete."""
        try:
            message = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        # Das Protokoll-Callback selbst ist synchron. Die eigentliche
        # Verarbeitung darf trotzdem asynchron im Event-Loop laufen.
        asyncio.create_task(self.callback(message, address))
