"""Startpunkt eines QuizBattle-Servers.

Diese Datei ist absichtlich klein: Sie liest nur Startparameter, erzeugt die
ServerConfig und uebergibt danach an QuizServer. Die verteilte Logik liegt in
den Modulen unter quizbattle/.
"""

import argparse
import asyncio
import logging

from quizbattle.identity import load_or_create_uuid, normalize_uuid
from quizbattle.protocol import local_ip
from quizbattle.server_app import QuizServer
from quizbattle.settings import DEFAULT_DISCOVERY_PORT, PROJECT_DIR, ServerConfig


def parse_config():
    """Lese Serveridentitaet, LAN-Adresse und Ports aus der Kommandozeile.

    Der Server braucht beim Start zwei Portarten: WebSocket fuer Clients und
    Control-TCP fuer andere Server. Die UUID kommt entweder explizit oder aus
    einer persistenten Identity-Datei.
    """
    parser = argparse.ArgumentParser(description="Distributed QuizBattle server")
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument("--uuid", help="Explicit server UUID")
    identity.add_argument("--identity-file", help="File containing the persistent UUID")
    parser.add_argument("--host", help="LAN IP advertised to other computers")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--ws-port", type=int, default=5000)
    parser.add_argument("--control-port", type=int, default=6000)
    parser.add_argument("--discovery-port", type=int, default=DEFAULT_DISCOVERY_PORT)
    parser.add_argument("--broadcast", default="255.255.255.255")
    args = parser.parse_args()

    if args.uuid:
        # Explizite UUID ist praktisch fuer reproduzierbare Tests. Im normalen
        # Betrieb wird eher die Identity-Datei verwendet.
        server_uuid = normalize_uuid(args.uuid)
    else:
        # Standard: pro Control-Port eine eigene Identity-Datei. Dadurch koennen
        # mehrere Server auf demselben Testgeraet unterschiedliche UUIDs haben.
        identity_file = args.identity_file or (
            PROJECT_DIR / f".server_uuid_{args.control_port}"
        )
        server_uuid = load_or_create_uuid(identity_file)

    return ServerConfig(
        server_uuid=server_uuid,
        host=args.host or local_ip(),
        bind_host=args.bind,
        ws_port=args.ws_port,
        control_port=args.control_port,
        discovery_port=args.discovery_port,
        broadcast_ip=args.broadcast,
    )


async def main():
    """Konfiguriere Logging und betreibe den Server bis zum Programmende.

    server.start() laeuft dauerhaft. Bei Ctrl+C wird im finally-Block sauber
    gestoppt, damit SERVER_LEAVE gesendet und Listener geschlossen werden.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    server = QuizServer(parse_config())
    try:
        await server.start()
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        # asyncio.run erstellt und schliesst den zentralen Event-Loop.
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
