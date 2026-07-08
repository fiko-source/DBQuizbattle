"""Startpunkt fuer den grafischen QuizBattle-Client.

Der Client kennt beim Start keine Server-IP. Er bekommt nur Name,
Discovery-Port und Broadcast-Adresse. Die eigentliche Leadersuche passiert in
client_network.py.
"""

import argparse
import socket
import sys

from PyQt6.QtWidgets import QApplication

from quizbattle.client_ui import QuizWindow
from quizbattle.settings import ClientConfig, DEFAULT_DISCOVERY_PORT


def parse_config():
    """Lese die Kommandozeilenargumente und baue die Client-Konfiguration.

    --broadcast ist fuer die Discovery entscheidend: dorthin sendet der Client
    sein CLIENT_DISCOVER, damit der aktuelle Leader antworten kann.
    """
    parser = argparse.ArgumentParser(description="QuizBattle GUI client")
    parser.add_argument("--name", default=socket.gethostname())
    parser.add_argument("--discovery-port", type=int, default=DEFAULT_DISCOVERY_PORT)
    parser.add_argument("--broadcast", default="255.255.255.255")
    args = parser.parse_args()
    return ClientConfig(
        name=args.name,
        discovery_port=args.discovery_port,
        broadcast_ip=args.broadcast,
    )


if __name__ == "__main__":
    # PyQt verwaltet die grafische Oberflaeche in seinem eigenen Event-Loop.
    app = QApplication(sys.argv)
    window = QuizWindow(parse_config())
    window.show()
    sys.exit(app.exec())
