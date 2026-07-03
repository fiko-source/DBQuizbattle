"""Netzwerkseite des Clients: Discovery, WebSocket und Nachrichtenordnung."""

import asyncio
import json
import socket
import threading
import uuid

import websockets

from .client_ordering import OrderedEventBuffer


class NetworkClient:
    """Verbinde die PyQt-Oberflaeche mit dem jeweils aktiven Quiz-Leader."""

    def __init__(self, name, discovery_port, broadcast_ip, signals):
        """Speichere Einstellungen und bereite den Verbindungszustand vor."""
        self.name = name
        self.discovery_port = discovery_port
        self.broadcast_ip = broadcast_ip
        self.signals = signals
        self.token = None
        self.player_id = None
        self.websocket = None
        self.loop = None
        self.outbox = None
        self.stopped = False
        self.ordering = OrderedEventBuffer()
        self.pending_actions = {}

    @property
    def last_seq(self):
        """Gib die letzte vollstaendig verarbeitete Ereignisnummer zurueck."""
        return self.ordering.last_sequence

    def start(self):
        """Starte das asynchrone Netzwerk in einem Hintergrundthread."""
        # PyQt muss im Hauptthread bleiben. Daher erhaelt asyncio einen eigenen
        # Thread, damit GUI und Netzwerk gleichzeitig reagieren koennen.
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        """Erzeuge den asyncio-Event-Loop des Netzwerkthreads."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.outbox = asyncio.Queue()
        self.loop.run_until_complete(self.connection_loop())

    def send(self, message):
        """Uebergib eine GUI-Aktion threadsicher an den Netzwerk-Event-Loop."""
        if self.loop and self.outbox:
            # Benutzeraktionen erhalten eine UUID. Bleibt eine Bestaetigung aus,
            # kann exakt dieselbe Aktion erneut gesendet werden, ohne sie auf
            # dem Server doppelt anzuwenden.
            if message.get("type") in {
                "ANSWER",
                "TEAM_ANSWER",
                "TEAM_CHAT",
                "CATEGORY_CHOICE",
            }:
                request_id = message.setdefault("request_id", uuid.uuid4().hex)
                self.pending_actions[request_id] = message
            asyncio.run_coroutine_threadsafe(self.outbox.put(message), self.loop)

    async def discover_leader(self):
        """Suche den aktuellen Leader per UDP-Broadcast im lokalen Netzwerk."""
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        # Port 0 laesst das Betriebssystem einen freien Absenderport waehlen.
        sock.bind(("0.0.0.0", 0))
        request = json.dumps({"type": "CLIENT_DISCOVER"}).encode()
        deadline = loop.time() + 4
        try:
            while loop.time() < deadline:
                # Nur der Leader beantwortet CLIENT_DISCOVER. Seine Antwort
                # enthaelt die LAN-IP und den WebSocket-Port.
                await loop.sock_sendto(
                    sock, request, (self.broadcast_ip, self.discovery_port)
                )
                try:
                    data, _ = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 4096), 1
                    )
                    response = json.loads(data.decode())
                    if response.get("type") == "LEADER_RESPONSE":
                        return response["host"], int(response["ws_port"])
                except asyncio.TimeoutError:
                    continue
        finally:
            sock.close()
        return None

    async def connection_loop(self):
        """Suche dauerhaft einen Leader und stelle verlorene Verbindungen wieder her."""
        while not self.stopped:
            self.signals.status.emit("Suche Leader im Netzwerk...")
            leader = await self.discover_leader()
            if not leader:
                self.signals.status.emit("Kein Leader gefunden. Neuer Versuch...")
                await asyncio.sleep(2)
                continue

            uri = f"ws://{leader[0]}:{leader[1]}"
            try:
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    # Token und Sequenznummer ermoeglichen nach einem
                    # Leaderwechsel die Fortsetzung derselben Sitzung.
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "JOIN",
                                "name": self.name,
                                "token": self.token,
                                "last_seq": self.last_seq,
                            }
                        )
                    )
                    self.signals.status.emit(f"Mit Leader {uri} verbunden.")
                    receiver = asyncio.create_task(self.receive_loop(websocket))
                    sender = asyncio.create_task(self.send_loop(websocket))
                    # Endet Senden oder Empfangen, ist die gemeinsame
                    # Verbindung nicht mehr nutzbar. Der andere Task wird dann
                    # beendet und die Leadersuche startet erneut.
                    done, pending = await asyncio.wait(
                        [receiver, sender],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    for task in done:
                        task.result()
            except (
                OSError,
                websockets.ConnectionClosed,
                websockets.InvalidHandshake,
            ):
                self.signals.status.emit(
                    "Verbindung verloren. Suche neuen Leader..."
                )
                await asyncio.sleep(1)
            finally:
                self.websocket = None

    async def receive_loop(self, websocket):
        """Empfange Servernachrichten und liefere sie geordnet an die GUI."""
        async for raw in websocket:
            message = json.loads(raw)
            message_type = message.get("type")
            if message_type == "NOT_LEADER":
                return
            if message_type == "WELCOME":
                self.token = message["token"]
                self.player_id = message["player_id"]
                self.signals.message.emit(message)
                continue
            if message_type == "ACTION_STATUS":
                self.pending_actions.pop(message.get("request_id"), None)
                self.signals.message.emit(message)
                continue

            sequence = message.get("seq")
            # Verwaltungsnachrichten ohne Sequenznummer koennen direkt an die
            # Oberflaeche weitergegeben werden.
            if not isinstance(sequence, int):
                self.signals.message.emit(message)
                continue

            delivered, missing = self.ordering.receive(message)
            if missing:
                # Bei einer Sequenzluecke fragt der Client nur den fehlenden
                # Bereich erneut an, statt die ganze Sitzung neu zu laden.
                await websocket.send(
                    json.dumps(
                        {
                            "type": "RESEND_REQUEST",
                            "from_seq": missing[0],
                            "to_seq": missing[1],
                        }
                    )
                )
            for event in delivered:
                self.signals.message.emit(event)
            await websocket.send(
                json.dumps({"type": "ACK", "seq": self.last_seq})
            )

    async def send_loop(self, websocket):
        """Sende neue und noch nicht bestaetigte Clientaktionen an den Leader."""
        # Nach einem Reconnect werden unbestaetigte Aktionen zuerst wiederholt.
        for message in list(self.pending_actions.values()):
            await websocket.send(json.dumps(message, ensure_ascii=False))
        while True:
            try:
                message = await asyncio.wait_for(self.outbox.get(), timeout=1)
                request_id = message.get("request_id")
                if request_id is None or request_id in self.pending_actions:
                    await websocket.send(
                        json.dumps(message, ensure_ascii=False)
                    )
            except asyncio.TimeoutError:
                # Die Wiederholung macht den Versand zuverlaessiger. Der
                # request_id-Schutz verhindert eine doppelte Ausfuehrung.
                for message in list(self.pending_actions.values()):
                    await websocket.send(
                        json.dumps(message, ensure_ascii=False)
                    )
