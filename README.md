# QuizBattle

QuizBattle ist ein verteiltes Multiplayer-Quiz für ein lokales Netzwerk. Mehrere
identische Server laufen parallel. Einer ist Leader und führt das Spiel aus, die
anderen halten als Backups eine replizierte Kopie des Spielzustands.

## Umgesetzte Anforderungen

- UDP-Broadcast zur dynamischen Erkennung von Servern und Leader durch Clients
- logischer Ring, sortiert nach automatisch erzeugten, dauerhaften Server-UUIDs
- LCR-Leaderwahl über bestätigte, gerahmte TCP-Nachrichten
- Heartbeats, Ausfallerkennung und automatische Neuwahl
- bestätigte Primary-Backup-Replikation des vollständigen Spielzustands
- Client-Reconnect nach Leader-Ausfall
- total geordnete Spielereignisse mit Sequenznummer, ACK und Wiederholung
- Hold-back-Queue und Nachforderung bei erkannten Sequenzlücken
- eindeutige Request-IDs gegen doppelte Antworten nach Reconnect
- Einzelrunden und jede dritte Runde als Teamrunde
- Teamchat über den Server und eine gemeinsame Teamantwort

Das Architektur-Bild im Projektformular wurde nicht als technische Vorgabe
verwendet. Maßgeblich sind die textlichen Anforderungen.

## Netzwerk

Alle Geräte müssen sich im selben LAN befinden und UDP-Broadcast erlauben.

| Port | Protokoll | Verwendung |
| --- | --- | --- |
| 5972 | UDP | Discovery und Heartbeats |
| frei wählbar | TCP | LCR, Membership und Replikation |
| frei wählbar | TCP | WebSocket-Verbindung der Clients |

Auf verschiedenen Rechnern dürfen WebSocket- und Control-Ports gleich sein.
Jeder Server erzeugt beim ersten Start automatisch eine weltweit eindeutige
UUID und verwendet sie bei späteren Starts erneut.

Bei Netzen, die `255.255.255.255` nicht weiterleiten, muss die konkrete
Broadcast-Adresse verwendet werden, zum Beispiel `192.168.1.255`.

## Installation

Auf jedem beteiligten Rechner:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Unter Windows wird die Umgebung mit `.venv\Scripts\activate` aktiviert.

## Server auf mehreren Rechnern starten

Ein einzelner Server wird beispielsweise so gestartet:

```bash
./start-server.sh 5001 6001 192.168.2.176 192.168.2.255
```

Die vier Argumente haben folgende Bedeutung:

| Argument | Beispiel | Bedeutung |
| --- | --- | --- |
| WebSocket-Port | `5001` | TCP-Port, über den sich Clients mit diesem Server verbinden |
| Control-Port | `6001` | TCP-Port für Wahl, Heartbeats und Replikation zwischen Servern |
| Server-IP | `192.168.2.176` | Aktuelle LAN- oder WLAN-Adresse dieses Server-Rechners |
| Broadcast-IP | `192.168.2.255` | Adresse, über die alle Geräte im lokalen Subnetz erreicht werden |

Beim ersten Start erzeugt der Server mit `uuid.uuid4()` eine eigene UUID. Das
Startskript speichert sie standardmäßig in `.server_uuid_6001`, wobei `6001`
der Control-Port ist. Beim nächsten Start mit demselben Control-Port wird diese
Datei wieder geladen. Die Identität bleibt dadurch über Neustarts erhalten.

Die UUID wird nicht von Hand eingegeben. Sie dient als eindeutige Identität,
zur Sortierung des logischen Rings und als Kandidat in der LCR-Leaderwahl.
Verglichen wird der vollständige numerische 128-Bit-Wert der UUID.

Der Discovery-Port `5972/UDP` muss nicht im Befehl angegeben werden. Er wird
standardmäßig von Server und Client verwendet.

Der Befehl bedeutet konkret: Der Server lädt oder erzeugt seine UUID und ist
unter `192.168.2.176` erreichbar. Clients verbinden sich über Port `5001`,
andere Server verwenden Port `6001` und Discovery-Nachrichten werden an das
Netz `192.168.2.255` gesendet.

Beispiel mit drei Rechnern im Netz `192.168.1.0/24`:

Rechner A:

```bash
./start-server.sh 5000 6000 192.168.1.10 192.168.1.255
```

Rechner B:

```bash
./start-server.sh 5000 6000 192.168.1.20 192.168.1.255
```

Rechner C:

```bash
./start-server.sh 5000 6000 192.168.1.30 192.168.1.255
```

Jeder Rechner besitzt seine eigene UUID-Datei. Der Server mit der numerisch
größten UUID wird Leader. Fällt er aus, wählen die verbleibenden Server über
LCR automatisch einen neuen Leader.

Mehrere Server auf demselben Raspberry Pi benötigen unterschiedliche Ports:

```bash
./start-server.sh 5001 6001 192.168.2.176 192.168.2.255
./start-server.sh 5002 6002 192.168.2.176 192.168.2.255
./start-server.sh 5003 6003 192.168.2.176 192.168.2.255
```

Dabei entstehen automatisch `.server_uuid_6001`, `.server_uuid_6002` und
`.server_uuid_6003`. Jeder Serverprozess besitzt deshalb eine andere,
dauerhafte UUID.

Optional kann als fünftes Argument eine eigene Identitätsdatei angegeben
werden:

```bash
./start-server.sh 5001 6001 192.168.2.176 192.168.2.255 pi-server.uuid
```

Wird diese Datei auf einen anderen Rechner kopiert, würde dort dieselbe
Serveridentität verwendet. Innerhalb eines laufenden Clusters darf deshalb
niemals dieselbe Identitätsdatei für zwei Server gleichzeitig benutzt werden.

Alternativ kann direkt gestartet werden:

```bash
python3 src/server.py \
  --identity-file .server_uuid_pi \
  --host 192.168.1.10 \
  --ws-port 5000 \
  --control-port 6000 \
  --broadcast 192.168.1.255
```

Für reproduzierbare Tests kann stattdessen eine gültige UUID ausdrücklich
übergeben werden:

```bash
python3 src/server.py \
  --uuid 550e8400-e29b-41d4-a716-446655440000 \
  --host 192.168.1.10 \
  --ws-port 5000 \
  --control-port 6000 \
  --broadcast 192.168.1.255
```

`--uuid` und `--identity-file` dürfen nicht gleichzeitig verwendet werden.

## Clients starten

```bash
./start-client.sh "Taufik" 192.168.2.255
./start-client.sh "Musab" 192.168.2.255
./start-client.sh "Omar" 192.168.2.255
```

Der erste Wert ist der sichtbare Spielername. Der zweite Wert ist die
Broadcast-Adresse des lokalen Netzwerks. Der Client benötigt weder die feste
IP-Adresse des Servers noch dessen WebSocket-Port.

### So finden sich Client und Server

1. Der Server lauscht auf UDP-Port `5972` auf Discovery-Anfragen.
2. Der Client sendet `CLIENT_DISCOVER` an die angegebene Broadcast-Adresse,
   beispielsweise `192.168.2.255:5972`.
3. Alle QuizBattle-Server im Subnetz empfangen die Anfrage. Nur der aktuelle
   Leader antwortet.
4. Die Antwort `LEADER_RESPONSE` enthält die Server-IP und den WebSocket-Port,
   beispielsweise `192.168.2.176` und `5001`.
5. Der Client baut automatisch die direkte WebSocket-Verbindung
   `ws://192.168.2.176:5001` auf.

Nach einem Leader-Ausfall führt der Client diese Suche erneut durch und
verbindet sich mit dem neu gewählten Leader. Sein Token und die letzte
Sequenznummer bleiben dabei erhalten.

Server-IP und Broadcast-Adresse können sich nach einem Netzwerkwechsel ändern.
Bei einem `/24`-Netz haben beide Geräte beispielsweise Adressen
`192.168.2.x`; die zugehörige Broadcast-Adresse ist dann `192.168.2.255`.

## Spielablauf

Das Spiel beginnt, sobald mindestens ein Client verbunden ist. Jede Frage läuft
20 Sekunden.
Jede dritte Runde ist eine Teamrunde. Teams bestehen aus genau zwei Spielern.
Bei einer ungeraden Spielerzahl beantwortet der verbleibende Spieler die Runde
individuell. Teammitglieder können Nachrichten austauschen; die zuletzt
gesendete Teamantwort ist die gemeinsame Antwort. Nach allen Fragen zeigt der
Client die Rangliste.

Die sequenzierten Ereignisse umfassen unter anderem `NEXT_ROUND`,
`ROUND_START`, `QUESTION`, `ANSWER_PHASE_START`, `TEAM_MESSAGE`, `RESULT` und
`GAME_OVER`.

## Zuverlässigkeit

UDP wird nur für Discovery und Heartbeats verwendet. UDP-Broadcast ist bewusst
auf das lokale Subnetz begrenzt und darf Nachrichten verlieren.

Die Serverkommunikation für LCR und Replikation verwendet TCP-Nachrichten mit
4-Byte-Längenheader. Jede Nachricht besitzt eine ID, wird bestätigt und bei
einem Timeout erneut gesendet. Pro Ziel ist nur eine Nachricht gleichzeitig
offen, wodurch die FIFO-Reihenfolge des Ringkanals erhalten bleibt.

Der Leader repliziert einen neuen Zustand vor der Auslieferung eines
Spielereignisses an die Clients. Backups übernehmen den Zustand und bestätigen
die zugehörige Versionsnummer. Ein neu beitretender Server erhält den aktuellen
Zustand, bevor eine durch seinen Beitritt ausgelöste Wahl abgeschlossen wird.

Der Leader ist der Sequencer der Spielereignisse. Clients liefern nur die
nächste erwartete Sequenznummer an die GUI aus. Spätere Nachrichten werden in
einer Hold-back-Queue gehalten und fehlende Nummern beim Leader angefordert.
Nicht bestätigte Ereignisse werden erneut gesendet. Nach einem Reconnect sendet
der Leader alle Ereignisse nach der letzten bestätigten Sequenznummer erneut.

Das System behandelt Crash- beziehungsweise Fail-stop-Fehler. Ein Timeout kann
in einem asynchronen Netzwerk einen langsamen Server nicht sicher von einem
abgestürzten Server unterscheiden.

## Einfacher Failover-Test

1. Drei Server und mindestens einen Client auf verschiedenen Rechnern starten.
2. In den Server-Logs prüfen, dass der Server mit der größten UUID Leader ist.
3. Den Leader während einer Runde mit `Ctrl+C` beenden.
4. Nach ungefähr vier Sekunden wird der Ausfall erkannt und LCR erneut gestartet.
5. Die Clients suchen den neuen Leader und setzen das replizierte Spiel fort.

## Codeaufteilung

| Datei | Aufgabe |
| --- | --- |
| `src/server.py` | Server-Einstieg und Argumente |
| `src/client.py` | Client-Einstieg und Argumente |
| `src/quizbattle/discovery.py` | UDP-Broadcast |
| `src/quizbattle/identity.py` | Erzeugung und Speicherung der Server-UUID |
| `src/quizbattle/control.py` | zuverlässiger gerahmter TCP-Kanal |
| `src/quizbattle/cluster.py` | Membership, Ring, LCR und Replikation |
| `src/quizbattle/game.py` | Quiz-, Team- und Punkte-Logik |
| `src/quizbattle/server_app.py` | WebSocket-Sitzungen und Event-Auslieferung |
| `src/quizbattle/client_ordering.py` | Hold-back- und Sequenzlogik |
| `src/quizbattle/client_network.py` | Discovery, Reconnect und Client-ACKs |
| `src/quizbattle/client_ui.py` | PyQt-Oberfläche |

## Tests

```bash
python3 -m unittest discover -s tests -v
```
