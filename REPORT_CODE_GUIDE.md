# QuizBattle - Project Report zu Code-Stellen

Diese Datei hilft bei der Präsentation. Die Idee ist: Nicht den ganzen Code
zeigen, sondern genau die Stellen, die zu den Punkten aus dem Project Report
passen.

Die Präsentation wirkt dadurch viel sauberer:

```text
Report sagt: Wir haben Dynamic Discovery.
Code zeigt: Hier ist UDP-Broadcast und hier wird CLIENT_DISCOVER verarbeitet.
```

So kann man jede technische Aussage aus dem Report direkt mit Code belegen.

## 1. Grundstrategie für die Präsentation

Nicht nach Dateien präsentieren, sondern nach Anforderungen beziehungsweise
Report-Kapiteln.

Schlechte Reihenfolge:

```text
Wir gehen jetzt Datei für Datei durch.
```

Bessere Reihenfolge:

```text
1. Dynamic Discovery
2. Leader Election
3. Failure Detection
4. Replication
5. Reliable Ordered Delivery
6. Client-Server Architecture
7. Game Logic
```

Dann zeigt man pro Punkt nur wenige Codeausschnitte.

## 2. Minimaler Code-Pfad für eine gute Demo

Wenn die Zeit knapp ist, reichen diese Dateien:

| Thema | Datei |
| --- | --- |
| Discovery | `discovery.py`, `cluster.py`, `client_network.py` |
| Ring und LCR | `identity.py`, `cluster.py` |
| Failure Detection | `cluster.py` |
| Replikation | `server_app.py`, `cluster.py`, `game.py` |
| Ordered Events | `server_app.py`, `client_ordering.py`, `client_network.py` |
| Client-Verbindung | `server_app.py`, `client_network.py` |
| Spielzustand | `game.py` |

Die wichtigsten vier Dateien insgesamt:

```text
src/quizbattle/cluster.py
src/quizbattle/server_app.py
src/quizbattle/game.py
src/quizbattle/client_network.py
```

Wenn man nur sehr wenig Zeit hat:

```text
cluster.py
server_app.py
game.py
client_network.py
```

Wenn man zusätzlich den Discovery-Beweis zeigen will:

```text
discovery.py
```

## 3. Dynamic Discovery of Hosts

Report-Punkt:

```text
Client discovers server
Server discovers servers
```

Das ist im Report wichtig, weil unser System keine festen Server-IPs im Client
braucht. Clients und Server finden sich dynamisch im lokalen Netzwerk.

### 3.1 Technischer UDP-Broadcast

Datei:

```text
src/quizbattle/discovery.py
```

Zeigen:

```python
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind((self.bind_host, self.port))
self.transport.sendto(json_bytes(message), destination)
```

Was dazu sagen:

> Diese Datei ist die technische UDP-Schicht. Hier sieht man, dass Broadcast
> aktiviert wird und Nachrichten an die Broadcast-Adresse gesendet werden.

Warum wichtig:

- Beweist, dass Discovery wirklich über UDP-Broadcast läuft.
- Zeigt, dass Discovery unabhängig von WebSocket und TCP-Control ist.

Nicht zu lange erklären:

`discovery.py` kennt die Bedeutung der Nachrichten nicht. Es transportiert nur.
Die fachliche Logik kommt in `cluster.py`.

### 3.2 Client findet den Leader

Datei:

```text
src/quizbattle/client_network.py
```

Funktion:

```text
discover_leader()
```

Zeigen:

```python
request = json.dumps({"type": "CLIENT_DISCOVER"}).encode()
await loop.sock_sendto(
    sock, request, (self.broadcast_ip, self.discovery_port)
)
...
if response.get("type") == "LEADER_RESPONSE":
    return response["host"], int(response["ws_port"])
```

Was dazu sagen:

> Der Client kennt beim Start keine Server-IP. Er sendet CLIENT_DISCOVER per
> UDP-Broadcast. Nur der aktuelle Leader antwortet mit Host und WebSocket-Port.

Warum wichtig:

- Belegt `Client discovers server`.
- Belegt, dass der Client nicht hardcoded weiß, wo der Server läuft.

Gute Formulierung:

> Der Server findet den Client nicht aktiv. Der Client sucht den Leader. Der
> Server macht sich nur auffindbar.

### 3.3 Leader antwortet auf Client-Discovery

Datei:

```text
src/quizbattle/cluster.py
```

Funktion:

```text
handle_discovery()
```

Zeigen:

```python
if message_type == "CLIENT_DISCOVER":
    if self.is_leader:
        await self.send_discovery(
            {
                "type": "LEADER_RESPONSE",
                "server_uuid": self.config.server_uuid,
                "host": self.config.host,
                "ws_port": self.config.ws_port,
            },
            address,
        )
```

Was dazu sagen:

> Alle Server empfangen die Anfrage, aber nur der Leader antwortet. Dadurch
> verbindet sich der Client immer mit dem aktuellen Leader.

Warum wichtig:

- Verhindert, dass Clients zufällig mit Backups spielen.
- Passt zur Architektur: Nur der Leader ist autoritativ.

### 3.4 Server finden andere Server

Datei:

```text
src/quizbattle/cluster.py
```

Funktion:

```text
handle_discovery()
```

Zeigen:

```python
if message_type == "SERVER_DISCOVER":
    await self.send_discovery(self.server_message("SERVER_JOIN"), address)
```

und:

```python
if message_type not in {"SERVER_JOIN", "HEARTBEAT", "SERVER_LEAVE"}:
    return
...
is_new = self.register_peer(message, directly_seen=True)
```

Was dazu sagen:

> Server finden sich ebenfalls über UDP-Broadcast. Sie senden SERVER_DISCOVER,
> SERVER_JOIN oder HEARTBEAT und speichern die Kontaktdaten anderer Server in
> ihrer Peer-Liste.

Warum wichtig:

- Belegt `Server discovers servers`.
- Erklärt, woher Leader und Backup gegenseitig IP und Control-Port kennen.

Gute Kurzform:

```text
UDP = finden
TCP-Control = danach direkt sprechen
```

## 4. Client-Server Architecture

Report-Punkt:

```text
Client communicates with current leader via WebSocket/TCP.
```

### 4.1 Client verbindet sich mit Leader

Datei:

```text
src/quizbattle/client_network.py
```

Funktion:

```text
connection_loop()
```

Zeigen:

```python
uri = f"ws://{leader[0]}:{leader[1]}"
async with websockets.connect(uri) as websocket:
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
```

Was dazu sagen:

> Nach der Discovery wechselt der Client auf WebSocket/TCP. Beim JOIN sendet er
> Name, Token und letzte Sequenznummer.

Warum wichtig:

- `token` ermöglicht Reconnect als derselbe Spieler.
- `last_seq` ermöglicht Nachliefern verpasster Events.

### 4.2 Nur der Leader akzeptiert Clients

Datei:

```text
src/quizbattle/server_app.py
```

Funktion:

```text
handle_client()
```

Zeigen:

```python
if not self.cluster.is_leader:
    await websocket.send(json.dumps({"type": "NOT_LEADER"}))
    await websocket.close()
    return
```

Was dazu sagen:

> Backups akzeptieren keine aktiven Spielsitzungen. Falls ein Client doch bei
> einem Backup landet, wird er abgewiesen und sucht erneut per Discovery.

Warum wichtig:

- Es gibt genau eine autoritative Stelle.
- Verhindert unterschiedliche Spielstände auf verschiedenen Servern.

## 5. Server-to-Server Communication

Report-Punkt:

```text
Servers coordinate via TCP control messages.
```

### 5.1 Server kennen IP und Control-Port anderer Server

Datei:

```text
src/quizbattle/cluster.py
```

Funktion:

```text
register_peer()
```

Zeigen:

```python
self.peers[server_uuid] = {
    "host": message["host"],
    "ws_port": int(message["ws_port"]),
    "control_port": int(message["control_port"]),
    "last_seen": last_seen,
}
```

Was dazu sagen:

> Durch UDP-Discovery tauschen Server ihre UUID, Host-IP, WebSocket-Port und
> Control-Port aus. Danach kann jeder Server direkt per TCP-Control mit anderen
> Servern sprechen.

### 5.2 Zuverlässiger Control-Kanal

Datei:

```text
src/quizbattle/control.py
```

Funktionen:

```text
send()
receive()
prepare_message()
```

Zeigen:

```python
"message_id": message.get("message_id") or uuid.uuid4().hex
```

und:

```python
if message_id in self.responses:
    return self.responses[message_id]
```

und:

```python
response = {
    "type": "CONTROL_ACK",
    "message_id": message_id,
    **(result or {}),
}
```

Was dazu sagen:

> Server-Control-Nachrichten haben message_id und CONTROL_ACK. Wenn ein ACK
> fehlt, wird die Nachricht erneut gesendet. Durch message_id erkennt der
> Empfänger doppelte Nachrichten und führt sie nicht doppelt aus.

Warum wichtig:

- Behandelt Omission Faults bei Control-Nachrichten.
- Macht Wiederholungen sicher.

Gute Erklärung:

> TCP sorgt für geordnete Bytes innerhalb einer Verbindung. Unser ACK bestätigt
> zusätzlich auf Anwendungsebene, dass die Nachricht verarbeitet wurde.

## 6. Ring Formation and Leader Election

Report-Punkt:

```text
Logical ring, UUIDs, LCR leader election.
```

### 6.1 Persistente UUIDs

Datei:

```text
src/quizbattle/identity.py
```

Funktionen:

```text
load_or_create_uuid()
uuid_order_key()
```

Zeigen:

```python
generated = str(uuid.uuid4())
```

und:

```python
return uuid.UUID(normalize_uuid(value)).int
```

Was dazu sagen:

> Jeder Server bekommt beim ersten Start eine UUID und speichert sie in einer
> Identity-Datei. Diese UUID wird für Ring-Sortierung und LCR verwendet.

Warum wichtig:

- Keine manuell vergebenen IDs.
- UUID bleibt über Neustarts stabil.

### 6.2 Ring und Nachfolger

Datei:

```text
src/quizbattle/cluster.py
```

Funktionen:

```text
ring()
successor()
```

Zeigen:

```python
return sorted(
    [self.config.server_uuid, *self.peers],
    key=uuid_order_key,
)
```

und:

```python
return ring[(index + 1) % len(ring)]
```

Was dazu sagen:

> Der Ring ist logisch. Er entsteht durch Sortieren der UUIDs. Jeder Server
> bestimmt daraus seinen Nachfolger.

Warum wichtig:

- LCR arbeitet auf einem Ring.
- Der Ring muss nicht physisch sein.

### 6.3 LCR-Wahl

Datei:

```text
src/quizbattle/cluster.py
```

Funktionen:

```text
start_election()
handle_election()
become_leader()
handle_leader()
```

Zeigen:

```python
message = {
    "type": "ELECTION",
    "candidate": self.config.server_uuid,
}
```

und:

```python
if uuid_order_key(candidate) > uuid_order_key(self.config.server_uuid):
    forwarded = {"type": "ELECTION", "candidate": candidate}
elif not self.participant:
    forwarded = {
        "type": "ELECTION",
        "candidate": self.config.server_uuid,
    }
```

und:

```python
if candidate == self.config.server_uuid:
    await self.become_leader()
```

Was dazu sagen:

> Jeder Server vergleicht die Kandidaten-UUID mit seiner eigenen UUID. Die
> höchste UUID läuft einmal um den Ring und wird Leader.

Warum wichtig:

- Belegt die Leaderwahl.
- Passt zu LCR aus der Vorlesung.

## 7. Failure Detection and New Election

Report-Punkt:

```text
Heartbeats, timeout, leader failure, new election.
```

### 7.1 Heartbeats

Datei:

```text
src/quizbattle/cluster.py
```

Funktion:

```text
heartbeat_loop()
```

Zeigen:

```python
await self.broadcast_announcement("HEARTBEAT")
```

und:

```python
heartbeat = {
    "type": "CONTROL_HEARTBEAT",
    "leader_uuid": self.leader_uuid,
    "members": [...]
}
```

Was dazu sagen:

> Es gibt UDP-Heartbeats für Sichtbarkeit im LAN und TCP-Control-Heartbeats mit
> ACK als stärkeren Erreichbarkeitstest.

### 7.2 Timeout und Peer entfernen

Datei:

```text
src/quizbattle/cluster.py
```

Funktion:

```text
peer_monitor_loop()
```

Zeigen:

```python
expired = [
    server_uuid
    for server_uuid, peer in self.peers.items()
    if now - peer["last_seen"] > HEARTBEAT_TIMEOUT
]
```

und:

```python
self.remove_peer(server_uuid)
```

Was dazu sagen:

> Jeder Server entscheidet lokal anhand von Heartbeat-Timeouts, ob ein Peer aus
> seiner Ringansicht entfernt wird.

Wichtig formulieren:

> B und C stimmen nicht gemeinsam ab, dass A raus ist. Jeder erkennt den Ausfall
> lokal. Dadurch entsteht praktisch eine gemeinsame Sicht ohne A.

### 7.3 Leaderausfall startet neue Wahl

Datei:

```text
src/quizbattle/cluster.py
```

Funktion:

```text
peer_monitor_loop()
```

Zeigen:

```python
leader_failed = self.leader_uuid in expired
...
if expired and (leader_failed or self.leader_uuid not in self.ring()):
    await self.start_election(force=True)
```

Was dazu sagen:

> Wenn der entfernte Server der Leader war, startet der verbleibende Server eine
> neue LCR-Wahl.

Beispiel erklären:

```text
A ist Leader.
A fällt aus.
B erkennt Timeout.
B entfernt A aus peers.
B startet Election.
B und C wählen neuen Leader.
```

## 8. Replication

Report-Punkt:

```text
Primary-backup replication of game state.
```

### 8.1 Replizierbarer Spielzustand

Datei:

```text
src/quizbattle/game.py
```

Funktion:

```text
initial_state()
```

Zeigen:

```python
return {
    "version": 0,
    "phase": "waiting",
    "round": 0,
    ...
    "scores": {},
    "processed_requests": {},
    "sequence": 0,
    "events": [],
}
```

Was dazu sagen:

> Der komplette Spielzustand ist ein JSON-kompatibles Dictionary. Dadurch kann
> der Leader ihn einfach an Backups schicken.

Warum wichtig:

- Backups können übernehmen.
- Spielstand, Fragen, Punkte und Events liegen serverseitig.

### 8.2 Event erzeugen und vorher replizieren

Datei:

```text
src/quizbattle/server_app.py
```

Funktion:

```text
emit_event()
```

Zeigen:

```python
self.game.state["sequence"] += 1
...
self.game.state["events"].append(event)
await self.replicate_state()
await self.broadcast_clients(event)
```

Was dazu sagen:

> Der Leader erzeugt ein Event mit globaler Sequenznummer, speichert es in der
> Event-Historie, repliziert den Zustand und sendet es danach an Clients.

Warum wichtig:

- Backups sind möglichst aktuell, bevor Clients das Event sehen.
- Sequenznummern sind Grundlage für geordnete Zustellung.

### 8.3 Zustand an Backups senden

Datei:

```text
src/quizbattle/cluster.py
```

Funktion:

```text
replicate_state()
```

Zeigen:

```python
state = copy.deepcopy(self.get_state())
version = state.get("version", 0)
...
self.send_control(
    {"type": "REPLICATE", "state": state}, server_uuid
)
```

und:

```python
response.get("state_version") == version
```

Was dazu sagen:

> Der Leader sendet eine Kopie des Zustands an alle Backups. Ein Backup
> bestätigt mit der Version, die es übernommen hat.

Warum wichtig:

- Belegt Primary-Backup-Replikation.
- Version verhindert, dass alte Zustände als aktuell gelten.

## 9. Reliable Ordered Delivery to Clients

Report-Punkt:

```text
Ordered game events, ACK, resend, hold-back queue.
```

### 9.1 Sequenznummern beim Leader

Datei:

```text
src/quizbattle/server_app.py
```

Funktion:

```text
emit_event()
```

Zeigen:

```python
"seq": self.game.state["sequence"],
```

Was dazu sagen:

> Der Leader ist der Sequencer. Alle wichtigen Spielereignisse bekommen eine
> fortlaufende Sequenznummer.

### 9.2 Client ACKs

Datei:

```text
src/quizbattle/server_app.py
```

Funktion:

```text
handle_client_message()
```

Zeigen:

```python
if message_type == "ACK":
    self.client_acks[token] = max(
        int(message.get("seq", 0)), self.client_acks.get(token, 0)
    )
```

Was dazu sagen:

> ACK n bedeutet: Der Client hat alle Events bis einschließlich n verarbeitet.

### 9.3 Server wiederholt nicht bestätigte Events

Datei:

```text
src/quizbattle/server_app.py
```

Funktion:

```text
client_retry_loop()
```

Zeigen:

```python
next_seq = self.client_acks.get(token, 0) + 1
event = self.event_by_sequence(next_seq)
```

Was dazu sagen:

> Wenn ein Client kein ACK sendet, versucht der Server das nächste fehlende
> Event erneut zu senden.

### 9.4 Client erkennt Sequenzlücken

Datei:

```text
src/quizbattle/client_ordering.py
```

Funktion:

```text
OrderedEventBuffer.receive()
```

Zeigen:

```python
if not delivered and sequence > self.last_sequence + 1:
    return delivered, (self.last_sequence + 1, sequence - 1)
```

Was dazu sagen:

> Wenn der Client Event 7 bekommt, aber Event 6 fehlt, hält er 7 zurück und
> fordert 6 erneut an.

### 9.5 Client fordert fehlende Events an

Datei:

```text
src/quizbattle/client_network.py
```

Funktion:

```text
receive_loop()
```

Zeigen:

```python
if missing:
    await websocket.send(
        json.dumps(
            {
                "type": "RESEND_REQUEST",
                "from_seq": missing[0],
                "to_seq": missing[1],
            }
        )
    )
```

Was dazu sagen:

> Der Client fordert nur den fehlenden Bereich an, nicht die ganze Sitzung.

## 10. Client Action Reliability

Report-Punkt:

```text
Request IDs prevent duplicate client actions.
```

### 10.1 Client vergibt Request-ID

Datei:

```text
src/quizbattle/client_network.py
```

Funktion:

```text
send()
```

Zeigen:

```python
request_id = message.setdefault("request_id", uuid.uuid4().hex)
self.pending_actions[request_id] = message
```

Was dazu sagen:

> Aktionen wie Antwort, Teamchat oder Kategorieauswahl bekommen eine request_id.
> Falls die Aktion erneut gesendet wird, erkennt der Server sie wieder.

### 10.2 Server dedupliziert Clientaktionen

Datei:

```text
src/quizbattle/game.py
```

Funktion:

```text
handle_action()
remember_request()
```

Zeigen:

```python
if request_id and request_id in processed:
    return processed[request_id]
```

und:

```python
self.state["processed_requests"][request_id] = status
```

Was dazu sagen:

> Wird dieselbe Aktion erneut gesendet, gibt der Server nur den alten Status
> zurück und führt die Aktion nicht nochmal aus.

Warum wichtig:

- Schützt vor doppelten Antworten nach Reconnect.
- Macht Clientaktionen idempotent.

## 11. Game Logic and Authoritative State

Report-Punkt:

```text
Quiz game state is maintained by the server.
```

### 11.1 Server verarbeitet Aktionen

Datei:

```text
src/quizbattle/game.py
```

Funktion:

```text
handle_action()
```

Zeigen:

```python
if self.state["phase"] != "question":
    status = "Aktuell läuft keine Frage."
```

und:

```python
self.state["answers"][token] = answer
```

Was dazu sagen:

> Der Server prüft, ob gerade eine Frage läuft. Der Client kann nicht selbst
> entscheiden, ob eine Antwort zählt.

### 11.2 Server wertet Antworten aus

Datei:

```text
src/quizbattle/game.py
```

Funktion:

```text
evaluate_round()
```

Zeigen:

```python
correct = self.state["question"]["antwort"].strip().casefold()
...
if is_correct:
    self.state["scores"][token] = (
        self.state["scores"].get(token, 0) + 1
    )
```

Was dazu sagen:

> Punkte werden zentral auf dem Server vergeben. Die UI zeigt den Punktestand
> nur an.

### 11.3 Kategorieauswahl wird serverseitig geprüft

Datei:

```text
src/quizbattle/game.py
```

Funktion:

```text
handle_category_choice()
```

Zeigen:

```python
if token != self.state.get("category_chooser_token"):
    status = "Du bist aktuell nicht mit der Kategorieauswahl dran."
```

Was dazu sagen:

> Auch wenn die GUI Buttons deaktiviert, vertraut der Server dem Client nicht
> blind. Nur der berechtigte Spieler darf die Kategorie setzen.

## 12. Questions and Categories

Report-Punkt:

```text
Questions are stored in TinyDB and grouped by categories.
```

Dateien:

```text
tinydb.json
src/quizbattle/game.py
```

Zeigen in `tinydb.json`:

```json
{
  "kategorie": "Fußball",
  "frage": "...",
  "antwort": "..."
}
```

Zeigen in `game.py`:

```python
CATEGORY_BLOCK_SIZE = 5
DEFAULT_CATEGORIES = [...]
```

und:

```python
def ensure_category_questions(self):
```

Was dazu sagen:

> Fragen liegen lokal in TinyDB. Der Server sortiert sie nach Kategorien, mischt
> die Pools und wechselt nach fünf Fragen zur nächsten Kategorieauswahl.

## 13. Team Rounds

Report-Punkt:

```text
Team rounds and team communication.
```

Datei:

```text
src/quizbattle/game.py
```

Funktionen:

```text
start_next_round()
create_teams()
handle_action()
evaluate_round()
```

Zeigen:

```python
team_round = round_number % 3 == 0
```

und:

```python
return {
    f"Team {index // 2 + 1}": players[index : index + 2]
    for index in range(0, len(players) - 1, 2)
}
```

Was dazu sagen:

> Jede dritte Runde ist eine Teamrunde. Teams werden serverseitig gebildet. Die
> gemeinsame Antwort wird ebenfalls auf dem Server gespeichert.

## 14. Fault Model

Report-Punkt:

```text
Crash / Fail-stop faults, not Byzantine faults.
```

Code-Belege:

```text
cluster.py -> peer_monitor_loop()
cluster.py -> heartbeat_loop()
control.py -> ACK/Retry/Deduplizierung
server_app.py -> reconnect and resend
```

Was dazu sagen:

> Unser System behandelt Ausfälle, bei denen ein Server nicht mehr antwortet.
> Das wird über Heartbeat-Timeouts erkannt. Wir behandeln keine byzantinischen
> Fehler, also keine bösartigen oder lügenden Server.

Gute Formulierung:

```text
We tolerate omission/crash-style failures with timeout, ACK, retry and resend.
We do not implement Byzantine fault tolerance.
```

## 15. Code-Stellen, die man eher nicht lange zeigen muss

Diese Dateien sind wichtig, aber in der Präsentation meist nur kurz erwähnen:

| Datei | Warum nur kurz? |
| --- | --- |
| `settings.py` | Enthält Konstanten, aber wenig Architekturverhalten. |
| `protocol.py` | Wichtig für TCP-Framing, aber nur zeigen, wenn jemand nach TCP Details fragt. |
| `control.py` | Wichtig, aber komplex. Nur ACK/message_id/retry zeigen. |
| `client_ui.py` | Viel GUI-Code, aber wenig verteilte Systemlogik. |
| `start-server.sh` | Gut für Startparameter, aber nicht für Algorithmik. |

Ausnahme:

Wenn gefragt wird, was der Startbefehl bedeutet, kurz `start-server.sh` zeigen:

```text
./start-server.sh WS_PORT CONTROL_PORT LAN_IP BROADCAST_IP
```

Erklärung:

```text
WS_PORT       -> Client-WebSocket
CONTROL_PORT  -> Server-Server-TCP
LAN_IP        -> veröffentlichte Adresse dieses Servers
BROADCAST_IP  -> UDP-Discovery im lokalen Netz
```

## 16. Empfohlene Präsentationsreihenfolge

### Variante A: 10 Minuten

1. **Dynamic Discovery**
   - `client_network.py -> discover_leader()`
   - `cluster.py -> handle_discovery()`
   - kurz `discovery.py`

2. **Server Ring + Leader Election**
   - `identity.py -> uuid_order_key()`
   - `cluster.py -> ring()`, `successor()`
   - `cluster.py -> start_election()`, `handle_election()`

3. **Failure Detection**
   - `cluster.py -> heartbeat_loop()`
   - `cluster.py -> peer_monitor_loop()`

4. **Replication**
   - `game.py -> initial_state()`
   - `server_app.py -> emit_event()`
   - `cluster.py -> replicate_state()`

5. **Reliable Ordered Delivery**
   - `server_app.py -> ACK / retry`
   - `client_ordering.py -> receive()`

### Variante B: 5 Minuten

1. `client_network.py -> discover_leader()`
2. `cluster.py -> handle_discovery()`
3. `cluster.py -> ring() / handle_election()`
4. `cluster.py -> peer_monitor_loop()`
5. `server_app.py -> emit_event()`
6. `game.py -> evaluate_round()`

### Variante C: Wenn der Prof nur technische Fragen stellt

| Frage | Code zeigen |
| --- | --- |
| Wie findet der Client den Server? | `client_network.py -> discover_leader()` |
| Wie finden Server andere Server? | `cluster.py -> handle_discovery()`, `register_peer()` |
| Wie wird Leader gewählt? | `cluster.py -> start_election()`, `handle_election()` |
| Was passiert bei Leaderausfall? | `cluster.py -> peer_monitor_loop()` |
| Wo liegt der Spielstand? | `game.py -> initial_state()` |
| Wie wird repliziert? | `cluster.py -> replicate_state()` |
| Wie bekommen Clients geordnete Events? | `server_app.py -> emit_event()`, `client_ordering.py -> receive()` |
| Wie verhindert ihr doppelte Antworten? | `game.py -> processed_requests`, `client_network.py -> request_id` |

## 17. Kurze Sprechtexte pro Report-Punkt

### Dynamic Discovery

> Der Client kennt keine feste Server-IP. Er sendet CLIENT_DISCOVER per
> UDP-Broadcast. Nur der Leader antwortet mit Host und WebSocket-Port. Server
> entdecken sich ebenfalls per UDP-Broadcast und speichern Host und Control-Port
> anderer Server in ihrer Peer-Liste.

### Leader Election

> Jeder Server besitzt eine persistente UUID. Aus allen bekannten UUIDs wird ein
> logischer Ring gebildet. Die LCR-Wahl schickt Kandidaten-UUIDs durch den Ring.
> Die höchste UUID gewinnt und wird Leader.

### Failure Detection

> Jeder Server überwacht andere Server über Heartbeats. Wenn für länger als das
> Timeout kein Lebenszeichen kommt, entfernt der Server den Peer aus seiner
> lokalen Ringansicht. Wenn der entfernte Peer der Leader war, startet eine neue
> Election.

### Replication

> Der Leader hält den autoritativen Spielzustand. Bei Änderungen repliziert er
> den vollständigen Zustand an Backups. Backups bestätigen die Zustandsversion.
> Dadurch kann ein Backup nach Leaderausfall übernehmen.

### Reliable Ordered Delivery

> Der Leader nummeriert jedes Spielereignis mit einer Sequenznummer. Clients
> bestätigen verarbeitete Events mit ACK. Fehlende Sequenzen werden nachgefordert
> und zu früh eingetroffene Events bleiben in einer Hold-back-Queue.

### Game Logic

> Der Client zeigt nur an und sendet Eingaben. Antworten, Punkte, Kategorien,
> Teams und Spielphasen werden serverseitig geprüft und entschieden.

## 18. Was man vermeiden sollte

Nicht sagen:

```text
Der Server findet den Client.
```

Besser:

```text
Der Client findet den aktuellen Leader per UDP-Broadcast.
```

Nicht sagen:

```text
Server senden per Multicast an Clients.
```

Besser:

```text
Der Leader sendet dasselbe Event per WebSocket einzeln an alle verbundenen
Clients. Das ist Anwendungsebene-Broadcast, kein IP-Multicast.
```

Nicht sagen:

```text
B entscheidet für alle, dass A raus ist.
```

Besser:

```text
Jeder Server erkennt Ausfälle lokal über Heartbeat-Timeouts. Dadurch entfernen
B und C A jeweils aus ihrer lokalen Ringansicht.
```

Nicht sagen:

```text
TCP allein garantiert, dass die Servernachricht verarbeitet wurde.
```

Besser:

```text
TCP überträgt Bytes zuverlässig innerhalb einer Verbindung. Unsere
Anwendungs-ACKs bestätigen zusätzlich, dass die Nachricht verarbeitet wurde.
```

## 19. Finale Kurzliste für die Code-Demo

Diese Stellen reichen für eine starke Code-Demo:

```text
1. discovery.py
   BroadcastEndpoint.start()
   BroadcastEndpoint.send()

2. client_network.py
   discover_leader()
   connection_loop()

3. cluster.py
   handle_discovery()
   register_peer()
   ring()
   successor()
   heartbeat_loop()
   peer_monitor_loop()
   start_election()
   handle_election()
   replicate_state()

4. server_app.py
   handle_client()
   emit_event()
   client_retry_loop()
   handle_client_message()

5. game.py
   initial_state()
   handle_action()
   handle_category_choice()
   evaluate_round()

6. client_ordering.py
   OrderedEventBuffer.receive()

7. identity.py
   load_or_create_uuid()
   uuid_order_key()
```

Wenn man diese Stellen sicher erklären kann, ist man für die meisten Fragen zum
Project Report gut vorbereitet.
