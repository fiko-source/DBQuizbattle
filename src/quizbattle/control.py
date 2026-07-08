"""Zuverlaessiger TCP-Kanal fuer Nachrichten zwischen QuizBattle-Servern.

TCP uebertraegt Bytes innerhalb einer Verbindung zuverlaessig. Trotzdem braucht
die Anwendung eigene ACKs: Der Sender muss wissen, ob eine Servernachricht
wirklich verarbeitet wurde. Darum haben Control-Nachrichten message_id,
CONTROL_ACK, Timeout, Retry und Deduplizierung.
"""

import asyncio
import uuid

from .identity import normalize_uuid
from .protocol import read_frame, send_frame
from .settings import CONTROL_RETRIES, CONTROL_TIMEOUT


DEFERRED_MESSAGE_TYPES = {
    "ELECTION",
    "LEADER",
    "PEER_HELLO",
    "CONTROL_HEARTBEAT",
}


class ReliableControlChannel:
    """Sende bestaetigte, deduplizierte Kontrollnachrichten mit Wiederholungen.

    Dieser Kanal wird nur zwischen Servern benutzt. Er ist die Basis fuer LCR,
    Heartbeats, Membership und Replikation. Clients verwenden stattdessen
    WebSockets.
    """

    def __init__(
        self,
        config,
        sender_address,
        peer_lookup,
        sender_seen,
        message_handler,
    ):
        """Verbinde den Kanal ueber Callbacks mit dem ClusterManager.

        Die Callbacks halten diese Klasse allgemein: Der Kanal weiss, wie man
        Nachrichten zuverlaessiger verschickt, aber der ClusterManager
        entscheidet, was eine Nachricht fachlich bedeutet.
        """
        self.config = config
        self.sender_address = sender_address
        self.peer_lookup = peer_lookup
        self.sender_seen = sender_seen
        self.message_handler = message_handler
        # TCP-Listener fuer eingehende Control-Verbindungen.
        self.server = None
        # Ein Lock pro Zielserver erhaelt die Reihenfolge ausgehender
        # Nachrichten. So wird nicht gleichzeitig mehrfach an denselben Peer
        # geschrieben.
        self.peer_locks = {}
        # Ein Lock pro Absender erhaelt die Reihenfolge aufgeschobener
        # eingehender Ringnachrichten.
        self.inbound_locks = {}
        # Bereits beantwortete message_id -> ACK. Das ist die Deduplizierung:
        # kommt dieselbe Nachricht erneut, wird die alte Antwort geliefert.
        self.responses = {}

    async def start(self):
        """Starte den TCP-Listener fuer eingehende Servernachrichten."""
        self.server = await asyncio.start_server(
            self.handle_connection,
            self.config.bind_host,
            self.config.control_port,
        )

    async def handle_connection(self, reader, writer):
        """Lese eine Anfrage, sende ihre Bestaetigung und schliesse die Verbindung.

        Jede Control-Nachricht nutzt eine kurze TCP-Verbindung: verbinden,
        Frame senden, ACK lesen, schließen. Das ist fuer dieses Projekt einfach
        und gut nachvollziehbar.
        """
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
        """Verarbeite eine Nachricht hoechstens einmal und erzeuge ein ACK.

        Wenn der Sender kein ACK bekommen hat, sendet er dieselbe message_id
        erneut. Diese Methode erkennt das und fuehrt die Aktion nicht doppelt
        aus.
        """
        message_id = message.get("message_id")
        # Wird dieselbe Nachricht wegen eines verlorenen ACK erneut gesendet,
        # liefern wir die alte Antwort, ohne die Aktion erneut auszufuehren.
        # Beispiel: B hat REPLICATE schon verarbeitet, aber A hat das ACK nicht
        # gesehen. A sendet erneut; B antwortet nur noch einmal.
        if message_id in self.responses:
            return self.responses[message_id]

        sender = message.get("sender")
        if (
            sender
            and normalize_uuid(sender["server_uuid"]) != self.config.server_uuid
        ):
            await self.sender_seen(sender)

        # Ringnachrichten muessen schnell bestaetigt werden. Ihre eigentliche
        # Bearbeitung wird danach geordnet im Hintergrund fortgesetzt, damit
        # sich die Server im Ring nicht gegenseitig blockieren. Ohne dieses
        # schnelle ACK koennte eine LCR-Nachricht auf einen kompletten
        # Folgeablauf warten und dadurch Timeouts ausloesen.
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
        sender_uuid = normalize_uuid(message["sender"]["server_uuid"])
        lock = self.inbound_locks.setdefault(sender_uuid, asyncio.Lock())
        async with lock:
            await self.message_handler(message)

    async def send(self, message, server_uuid, retries=CONTROL_RETRIES):
        """Sende eine Nachricht bestaetigt an einen Server und wiederhole bei Fehlern.

        Kein ACK bedeutet fuer den Sender: "Ich weiss nicht, ob die Nachricht
        verarbeitet wurde." Deshalb wird erneut gesendet. Doppelte Ausfuehrung
        verhindert der Empfaenger ueber message_id.
        """
        if server_uuid == self.config.server_uuid:
            # Sonderfall fuer Ein-Server-Ring oder lokale Tests: Nachrichten an
            # sich selbst laufen ohne echte Netzwerkverbindung durch receive().
            local = self.prepare_message(message)
            return await self.receive(local)

        peer = self.peer_lookup(server_uuid)
        if not peer:
            return None

        lock = self.peer_locks.setdefault(server_uuid, asyncio.Lock())
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
        """Ergaenze eindeutige Nachrichten-ID und eigene Absenderadresse.

        Die message_id ist die technische Identitaet genau dieser logischen
        Nachricht. Der sender hilft dem Empfaenger, seine Peer-Liste aktuell zu
        halten.
        """
        return {
            **message,
            "message_id": message.get("message_id") or uuid.uuid4().hex,
            "sender": self.sender_address(),
        }

    async def send_once(self, payload, peer):
        """Fuehre genau einen TCP-Sendeversuch mit Zeitlimit aus.

        Diese Methode macht absichtlich nur einen Versuch. Die Retry-Logik liegt
        darueber in send(), damit klar getrennt ist: ein Versuch vs.
        Wiederholungsstrategie.
        """
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

    def forget_peer(self, server_uuid):
        """Entferne nicht mehr benoetigte Synchronisationsdaten eines Servers."""
        self.peer_locks.pop(server_uuid, None)

    async def stop(self):
        """Beende den TCP-Listener kontrolliert."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
