"""Zuverlaessiger TCP-Kanal fuer Nachrichten zwischen QuizBattle-Servern."""

import asyncio
import uuid

from .protocol import read_frame, send_frame
from .settings import CONTROL_RETRIES, CONTROL_TIMEOUT


DEFERRED_MESSAGE_TYPES = {
    "ELECTION",
    "LEADER",
    "PEER_HELLO",
    "CONTROL_HEARTBEAT",
}


class ReliableControlChannel:
    """Sende bestaetigte, deduplizierte Kontrollnachrichten mit Wiederholungen."""

    def __init__(
        self,
        config,
        sender_address,
        peer_lookup,
        sender_seen,
        message_handler,
    ):
        """Verbinde den Kanal ueber Callbacks mit dem ClusterManager."""
        self.config = config
        self.sender_address = sender_address
        self.peer_lookup = peer_lookup
        self.sender_seen = sender_seen
        self.message_handler = message_handler
        self.server = None
        self.peer_locks = {}
        self.inbound_locks = {}
        self.responses = {}

    async def start(self):
        """Starte den TCP-Listener fuer eingehende Servernachrichten."""
        self.server = await asyncio.start_server(
            self.handle_connection,
            self.config.bind_host,
            self.config.control_port,
        )

    async def handle_connection(self, reader, writer):
        """Lese eine Anfrage, sende ihre Bestaetigung und schliesse die Verbindung."""
        try:
            message = await asyncio.wait_for(
                read_frame(reader), timeout=CONTROL_TIMEOUT
            )
            response = await self.receive(message)
            await send_frame(writer, response)
        except (
            asyncio.IncompleteReadError,
            asyncio.TimeoutError,
            ConnectionError,
            OSError,
            ValueError,
        ):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def receive(self, message):
        """Verarbeite eine Nachricht hoechstens einmal und erzeuge ein ACK."""
        message_id = message.get("message_id")
        # Wird dieselbe Nachricht wegen eines verlorenen ACK erneut gesendet,
        # liefern wir die alte Antwort, ohne die Aktion erneut auszufuehren.
        if message_id in self.responses:
            return self.responses[message_id]

        sender = message.get("sender")
        if sender and int(sender["server_id"]) != self.config.server_id:
            await self.sender_seen(sender)

        # Ringnachrichten muessen schnell bestaetigt werden. Ihre eigentliche
        # Bearbeitung wird danach geordnet im Hintergrund fortgesetzt, damit
        # sich die Server im Ring nicht gegenseitig blockieren.
        deferred = message.get("type") in DEFERRED_MESSAGE_TYPES
        result = None if deferred else await self.message_handler(message)
        response = {
            "type": "CONTROL_ACK",
            "message_id": message_id,
            **(result or {}),
        }
        if message_id:
            self.responses[message_id] = response
            if len(self.responses) > 2000:
                oldest = next(iter(self.responses))
                self.responses.pop(oldest)
        if deferred:
            asyncio.create_task(self.handle_deferred(message))
        return response

    async def handle_deferred(self, message):
        """Bearbeite aufgeschobene Nachrichten je Absender in Empfangsreihenfolge."""
        sender_id = int(message["sender"]["server_id"])
        lock = self.inbound_locks.setdefault(sender_id, asyncio.Lock())
        async with lock:
            await self.message_handler(message)

    async def send(self, message, server_id, retries=CONTROL_RETRIES):
        """Sende eine Nachricht bestaetigt an einen Server und wiederhole bei Fehlern."""
        if server_id == self.config.server_id:
            local = self.prepare_message(message)
            return await self.receive(local)

        peer = self.peer_lookup(server_id)
        if not peer:
            return None

        lock = self.peer_locks.setdefault(server_id, asyncio.Lock())
        # Pro Zielserver sendet nur ein Task gleichzeitig. So bleibt die
        # beobachtete Reihenfolge der Kontrollnachrichten stabil.
        async with lock:
            payload = self.prepare_message(message)
            for attempt in range(retries):
                response = await self.send_once(payload, peer)
                if (
                    response
                    and response.get("message_id") == payload["message_id"]
                ):
                    return response
                if attempt + 1 < retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
            return None

    def prepare_message(self, message):
        """Ergaenze eindeutige Nachrichten-ID und eigene Absenderadresse."""
        return {
            **message,
            "message_id": message.get("message_id") or uuid.uuid4().hex,
            "sender": self.sender_address(),
        }

    async def send_once(self, payload, peer):
        """Fuehre genau einen TCP-Sendeversuch mit Zeitlimit aus."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(peer["host"], peer["control_port"]),
                timeout=CONTROL_TIMEOUT,
            )
            try:
                await send_frame(writer, payload)
                return await asyncio.wait_for(
                    read_frame(reader), timeout=CONTROL_TIMEOUT
                )
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
        except (
            asyncio.IncompleteReadError,
            asyncio.TimeoutError,
            ConnectionError,
            OSError,
            ValueError,
        ):
            return None

    def forget_peer(self, server_id):
        """Entferne nicht mehr benoetigte Synchronisationsdaten eines Servers."""
        self.peer_locks.pop(server_id, None)

    async def stop(self):
        """Beende den TCP-Listener kontrolliert."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
