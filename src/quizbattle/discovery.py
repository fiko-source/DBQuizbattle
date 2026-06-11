"""Wiederverwendbarer UDP-Endpunkt fuer Discovery und Heartbeats."""

import asyncio
import socket

from .protocol import DatagramProtocol, json_bytes


class BroadcastEndpoint:
    """Sende Broadcasts und leite empfangene JSON-Nachrichten weiter."""

    def __init__(self, bind_host, port, broadcast_ip, callback):
        """Speichere Bind-Adresse, Ziel-Broadcast und Empfangsfunktion."""
        self.bind_host = bind_host
        self.port = port
        self.broadcast_ip = broadcast_ip
        self.callback = callback
        self.transport = None

    async def start(self):
        """Oeffne den gemeinsam genutzten UDP-Discovery-Port."""
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Mehrere Server auf demselben Testrechner duerfen denselben
        # Discovery-Port verwenden, sofern das Betriebssystem dies unterstuetzt.
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((self.bind_host, self.port))
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: DatagramProtocol(self.callback), sock=sock
        )

    def send(self, message, target=None):
        """Sende an ein konkretes Ziel oder standardmaessig als Broadcast."""
        if not self.transport:
            return
        destination = target or (self.broadcast_ip, self.port)
        self.transport.sendto(json_bytes(message), destination)

    def close(self):
        """Schliesse den UDP-Endpunkt, falls er gestartet wurde."""
        if self.transport:
            self.transport.close()
