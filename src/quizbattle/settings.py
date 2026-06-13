"""Gemeinsame Konstanten und Konfigurationsobjekte fuer QuizBattle."""

from dataclasses import dataclass
from pathlib import Path


# Der absolute Projektpfad sorgt dafuer, dass Dateien unabhaengig vom aktuellen
# Terminalordner gefunden werden.
PROJECT_DIR = Path(__file__).resolve().parents[2]

# Netzwerk- und Wiederholungszeiten in Sekunden.
DEFAULT_DISCOVERY_PORT = 5972
HEARTBEAT_INTERVAL = 1.0
HEARTBEAT_TIMEOUT = 4.0
CONTROL_TIMEOUT = 2.0
CONTROL_RETRIES = 3
CLIENT_RETRY_INTERVAL = 2.0

# Regeln fuer Spielstart und Rundendauer.
MIN_PLAYERS = 1
ROUND_TIME = 20
RESULT_TIME = 4


@dataclass
class ServerConfig:
    """Alle beim Start festgelegten Adressen und Ports eines Servers."""

    server_uuid: str
    host: str
    bind_host: str
    ws_port: int
    control_port: int
    discovery_port: int
    broadcast_ip: str


@dataclass
class ClientConfig:
    """Einstellungen, die ein Client fuer Discovery und Anzeige benoetigt."""

    name: str
    discovery_port: int
    broadcast_ip: str
