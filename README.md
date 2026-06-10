# QuizBattle

QuizBattle ist ein verteiltes Multiplayer-Quiz für ein lokales Netzwerk. Mehrere
identische Server laufen parallel. Einer ist Leader und führt das Spiel aus, die
anderen halten als Backups eine replizierte Kopie des Spielzustands.

## Umgesetzte Anforderungen

- UDP-Broadcast zur dynamischen Erkennung von Servern und Leader durch Clients
- logischer Ring, sortiert nach eindeutiger numerischer Server-ID
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
Jeder Server braucht lediglich eine weltweit im Quiz-Cluster eindeutige ID.

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

Beispiel mit drei Rechnern im Netz `192.168.1.0/24`:

Rechner A:

```bash
./start-server.sh 10 5000 6000 192.168.1.10 192.168.1.255
```

Rechner B:

```bash
./start-server.sh 20 5000 6000 192.168.1.20 192.168.1.255
```

Rechner C:

```bash
./start-server.sh 30 5000 6000 192.168.1.30 192.168.1.255
```

Server 30 wird Leader, weil 30 die höchste ID ist. Fällt er aus, wählen die
verbleibenden Server automatisch Server 20.

Alternativ kann direkt gestartet werden:

```bash
python3 src/server.py \
  --id 10 \
  --host 192.168.1.10 \
  --ws-port 5000 \
  --control-port 6000 \
  --broadcast 192.168.1.255
```

## Clients starten

```bash
./start-client.sh "Taufik" 192.168.1.255
./start-client.sh "Musab" 192.168.1.255
./start-client.sh "Omar" 192.168.1.255
```

Der Client benötigt keine feste Server-IP. Er fragt per Broadcast nach dem
aktuellen Leader. Nach einem Ausfall sucht er erneut und verbindet sich mit dem
neu gewählten Leader. Sein Token und die letzte Sequenznummer bleiben dabei
erhalten.

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
2. In den Server-Logs prüfen, dass der Server mit der höchsten ID Leader ist.
3. Den Leader während einer Runde mit `Ctrl+C` beenden.
4. Nach ungefähr vier Sekunden wird der Ausfall erkannt und LCR erneut gestartet.
5. Die Clients suchen den neuen Leader und setzen das replizierte Spiel fort.

## Codeaufteilung

| Datei | Aufgabe |
| --- | --- |
| `src/server.py` | Server-Einstieg und Argumente |
| `src/client.py` | Client-Einstieg und Argumente |
| `src/quizbattle/discovery.py` | UDP-Broadcast |
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
