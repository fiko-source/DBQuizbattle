"""Gemeinsame Konstanten und Konfigurationsobjekte fuer QuizBattle.

Dieses Modul ist die zentrale Sammelstelle fuer Werte, die von mehreren
anderen Dateien gebraucht werden. Dadurch stehen Ports, Timeouts und Spielregeln
nicht verstreut im Code. Wenn zum Beispiel der Heartbeat schneller oder die
Rundendauer laenger werden soll, muss man nicht in mehreren Modulen suchen.
"""

from dataclasses import dataclass
from pathlib import Path


# Der absolute Projektpfad sorgt dafuer, dass Dateien unabhaengig vom aktuellen
# Terminalordner gefunden werden. Das ist wichtig fuer tinydb.json und
# Identity-Dateien, weil das Programm von unterschiedlichen Ordnern gestartet
# werden kann.
PROJECT_DIR = Path(__file__).resolve().parents[2]

# Netzwerk- und Wiederholungszeiten in Sekunden. Diese Werte beeinflussen, wie
# schnell sich Server finden, wie schnell ein Ausfall erkannt wird und wie oft
# Nachrichten erneut gesendet werden.
DEFAULT_DISCOVERY_PORT = 5972
HEARTBEAT_INTERVAL = 1.0
HEARTBEAT_TIMEOUT = 4.0
HEARTBEAT_LOG_INTERVAL = 10.0
CONTROL_TIMEOUT = 2.0
CONTROL_RETRIES = 3
CLIENT_RETRY_INTERVAL = 2.0

# Regeln fuer Spielstart und Rundendauer. Diese Konstanten beschreiben die
# fachlichen Spielregeln, nicht die Netzwerktechnik.
MIN_PLAYERS = 1
ROUND_TIME = 20
RESULT_TIME = 4


@dataclass
class ServerConfig:
    """Alle beim Start festgelegten Adressen und Ports eines Servers.

    Die ServerConfig wird einmal beim Start gebaut und dann an die
    Serverkomponenten weitergereicht. So benutzen WebSocket, Discovery,
    Control-Kanal und Clusterlogik dieselbe Sicht auf Host, Ports und UUID.
    """

    server_uuid: str
    host: str
    bind_host: str
    ws_port: int
    control_port: int
    discovery_port: int
    broadcast_ip: str


@dataclass
class ClientConfig:
    """Einstellungen, die ein Client fuer Discovery und Anzeige benoetigt.

    Der Client kennt beim Start keinen konkreten Server. Er braucht nur seinen
    Namen, den gemeinsamen Discovery-Port und die Broadcast-Adresse des LANs.
    """

    name: str
    discovery_port: int
    broadcast_ip: str
