from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]

DEFAULT_DISCOVERY_PORT = 5972
HEARTBEAT_INTERVAL = 1.0
HEARTBEAT_TIMEOUT = 4.0
CONTROL_TIMEOUT = 2.0
CONTROL_RETRIES = 3
CLIENT_RETRY_INTERVAL = 2.0

MIN_PLAYERS = 3
ROUND_TIME = 20
RESULT_TIME = 4


@dataclass
class ServerConfig:
    server_id: int
    host: str
    bind_host: str
    ws_port: int
    control_port: int
    discovery_port: int
    broadcast_ip: str


@dataclass
class ClientConfig:
    name: str
    discovery_port: int
    broadcast_ip: str
