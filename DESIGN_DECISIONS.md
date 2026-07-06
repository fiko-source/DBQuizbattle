# QuizBattle - Designentscheidungen

Diese Datei erklärt die wichtigsten Designentscheidungen des Projekts
`DBQuizbattle`. Sie ist bewusst ausführlich geschrieben, damit auch Personen mit
wenig Erfahrung in verteilten Systemen nachvollziehen können, warum das Projekt
so aufgebaut ist.

## 1. Grundidee des Systems

QuizBattle ist ein verteiltes Multiplayer-Quiz im lokalen Netzwerk. Mehrere
Server können gleichzeitig laufen. Einer dieser Server ist der Leader. Nur der
Leader führt das Spiel aktiv aus, nimmt Client-Aktionen entgegen und entscheidet
über Fragen, Antworten, Punkte und Spielphasen. Die anderen Server sind Backups.
Sie halten eine Kopie des Spielzustands und können übernehmen, wenn der Leader
ausfällt.

Die wichtigste Designidee ist:

```text
Clients zeigen nur an und senden Eingaben.
Der Leader entscheidet.
Backups halten den Zustand bereit.
```

Dadurch bleibt das System verständlich. Es gibt nicht mehrere Server, die
gleichzeitig unterschiedliche Wahrheiten über den Spielstand erzeugen könnten.
Der Leader ist die zentrale Autorität für den Spielablauf, aber diese Autorität
ist nicht an einen einzelnen Rechner gebunden. Wenn der Leader abstürzt, kann ein
Backup durch Leaderwahl übernehmen.

## 2. Annahme: Alle Geräte befinden sich im selben LAN

Das Projekt ist für ein lokales Netzwerk entworfen. Server und Clients müssen im
gleichen Subnetz laufen, zum Beispiel:

```text
Mac:      192.168.178.50
Pi:       192.168.178.93
Windows:  192.168.178.164
Broadcast 192.168.178.255
```

Diese Annahme ist wichtig, weil das Projekt UDP-Broadcast verwendet. Broadcast
funktioniert normalerweise nur innerhalb eines lokalen Subnetzes. Das System ist
also bewusst kein Internet-System und keine Cloud-Anwendung.

Warum diese Entscheidung sinnvoll ist:

- Die Projektanforderung bezieht sich auf ein verteiltes System im lokalen Netz.
- Für eine Vorlesungsdemo ist ein LAN einfacher und kontrollierbarer.
- UDP-Broadcast ermöglicht Server- und Leader-Findung ohne zentrale Registry.
- Es müssen keine Server-IPs im Client hardcodiert werden.

Die Kehrseite:

- Hochschul-WLANs blockieren Broadcast oft.
- Handy-Hotspots oder VM-NAT können Probleme machen.
- Router, Firewalls oder falsche Subnetze verhindern Discovery.

Deshalb ist Bridged Networking bei Parallels wichtig: Die Windows-VM muss eine
IP im gleichen LAN bekommen, nicht eine interne Parallels-NAT-Adresse wie
`10.211.55.x`.

## 3. UDP-Broadcast für Discovery

Clients kennen beim Start nicht die IP-Adresse des Leaders. Sie senden deshalb
eine UDP-Broadcast-Nachricht:

```text
CLIENT_DISCOVER -> Broadcast-Adresse:5972
```

Alle Server im Subnetz empfangen diese Nachricht. Aber nur der aktuelle Leader
antwortet mit:

```text
LEADER_RESPONSE:
  host
  ws_port
  server_uuid
```

Danach kann der Client eine direkte WebSocket-Verbindung zum Leader aufbauen.

Diese Entscheidung löst ein konkretes Problem: Der Client muss nicht wissen,
welcher Rechner gerade Leader ist. Er muss auch nicht wissen, ob nach einem
Ausfall ein anderer Server übernommen hat. Er fragt einfach erneut per
Broadcast.

Warum UDP für Discovery gut passt:

- UDP ist leichtgewichtig.
- Broadcast ist mit UDP einfach möglich.
- Für Discovery ist zuverlässige Zustellung nicht zwingend nötig.
- Wenn eine Anfrage verloren geht, sendet der Client einfach erneut.

Warum UDP nicht für wichtige Spielnachrichten verwendet wird:

- UDP garantiert keine Zustellung.
- UDP garantiert keine Reihenfolge.
- UDP kann Nachrichten verlieren oder duplizieren.

Deshalb wird UDP nur für Discovery und einfache Sichtbarkeit verwendet. Für
kritische Kommunikation nutzt das System TCP beziehungsweise WebSockets.

## 4. Getrennte Kommunikationswege

Das Projekt verwendet bewusst drei Kommunikationsarten:

| Kommunikation | Technik | Zweck |
| --- | --- | --- |
| Client findet Leader | UDP-Broadcast | Discovery |
| Client spielt mit Leader | WebSocket/TCP | Spielereignisse und Eingaben |
| Server sprechen miteinander | eigener TCP-Control-Kanal | Wahl, Heartbeat, Replikation |

Diese Trennung ist eine wichtige Designentscheidung. Jede Kommunikationsart wird
dort eingesetzt, wo sie am besten passt.

UDP-Broadcast ist gut für "Wer ist da?". WebSocket ist gut für eine dauerhafte
Verbindung zwischen GUI-Client und Server. Der eigene TCP-Control-Kanal ist gut
für Server-Server-Kommunikation, weil dort Nachrichten bestätigt, wiederholt und
dedupliziert werden können.

## 5. Clients kennen keine feste Server-IP

Ein Client wird zum Beispiel so gestartet:

```powershell
python src\client.py --name "Omar" --broadcast 192.168.178.255
```

Der Client bekommt nur die Broadcast-Adresse. Er bekommt keine konkrete
Server-IP und keinen WebSocket-Port. Diese Informationen ermittelt er zur
Laufzeit über `CLIENT_DISCOVER`.

Warum das gut ist:

- Der Client ist unabhängig vom aktuellen Leader.
- Der Leader darf ausfallen und durch einen anderen Server ersetzt werden.
- Es gibt weniger manuelle Konfiguration.
- Die Demo zeigt echte dynamische Discovery.

Was trotzdem angegeben werden muss:

- Die Broadcast-Adresse des lokalen Netzes.

Diese Adresse ist nötig, weil das Betriebssystem nicht immer automatisch weiß,
über welches Interface der Broadcast für die Anwendung gemeint ist. Besonders
bei mehreren Netzwerkadaptern, VPN, Parallels oder Hochschulnetzwerken ist eine
explizite Broadcast-Adresse robuster.

## 6. Server haben feste, persistente UUIDs

Jeder Server besitzt eine UUID. Diese UUID wird beim ersten Start erzeugt und in
einer Identity-Datei gespeichert, zum Beispiel:

```text
.server_uuid_6001
.server_uuid_6002
```

Beim nächsten Start wird dieselbe Datei wieder gelesen. Dadurch behält der
Server seine Identität.

Warum keine einfachen IDs wie `1`, `2`, `3`?

- Der Professor wollte UUIDs statt einfachen IDs.
- UUIDs sind weltweit praktisch eindeutig.
- Verschiedene Rechner können unabhängig voneinander IDs erzeugen.
- Es gibt weniger Risiko, dass zwei Server dieselbe ID verwenden.

Warum die UUID persistent ist und nicht bei jedem Start neu erzeugt wird:

- Ein Server bleibt über Neustarts derselbe logische Prozess.
- Die Leaderwahl wird reproduzierbarer.
- Ein Server, der abstürzt und wiederkommt, tritt mit derselben Identität wieder
  in den Ring ein.

Wichtig: Die UUID hängt nicht magisch am Gerät. Sie hängt an der Identity-Datei.
Wenn man diese Datei löscht, erzeugt der Server beim nächsten Start eine neue
UUID. Wenn man die Datei kopiert, würde ein anderer Rechner dieselbe Identität
verwenden. Das darf im gleichen laufenden Cluster nicht passieren.

## 7. Logischer Ring der Server

Alle bekannten Server werden nach ihrer UUID sortiert. Aus dieser sortierten
Liste entsteht ein logischer Ring.

Beispiel:

```text
Server A UUID 100
Server B UUID 300
Server C UUID 700

Ring: A -> B -> C -> A
```

Dieser Ring ist nicht physisch gemeint. Die Server müssen nicht wirklich im
Netzwerk ringförmig verbunden sein. Es ist eine logische Reihenfolge, die aus
den UUIDs berechnet wird.

Warum ein Ring?

- Der LCR-Algorithmus aus der Vorlesung arbeitet auf einem Ring.
- Jeder Server muss nur seinen Nachfolger kennen.
- Wahl-Nachrichten können im Ring weitergereicht werden.
- Die Struktur ist leicht erklärbar und passt zur Vorlesung.

Wenn ein neuer Server entdeckt wird, wird die Ringliste neu sortiert. Dadurch
kann sich der Nachfolger eines Servers ändern.

## 8. LCR-Leaderwahl

Das Projekt verwendet eine LCR-Leaderwahl. LCR steht für Le Lann, Chang und
Roberts. Die Idee:

1. Server sind in einem logischen Ring angeordnet.
2. Ein Server startet eine Wahl und schickt seine UUID als Kandidat weiter.
3. Jeder Server vergleicht die Kandidaten-UUID mit der eigenen UUID.
4. Die größere UUID bleibt im Rennen.
5. Wenn eine UUID einmal um den Ring läuft und wieder beim Ursprung ankommt,
   ist dieser Server der Leader.

Im Projekt gewinnt also der Server mit der numerisch größten UUID.

Warum diese Entscheidung sinnvoll ist:

- LCR passt direkt zu den Vorlesungsinhalten.
- Der Algorithmus ist deterministisch.
- Alle Server kommen bei gleicher Ringansicht zum gleichen Ergebnis.
- Es wird kein externer Koordinator benötigt.

Konsequenz:

Wenn Server A Leader war, abstürzt, Server B übernimmt und Server A später
zurückkommt, kann Server A wieder Leader werden, falls seine UUID größer ist als
die von Server B. Das ist kein Fehler, sondern eine direkte Folge der
LCR-Regel: Die höchste UUID gewinnt.

## 9. Leader-only Client-Verbindungen

Nur der Leader akzeptiert Clients als aktive Spielsitzungen. Wenn ein Client
versehentlich mit einem Backup verbunden wird, bekommt er `NOT_LEADER` und
sucht erneut.

Warum?

- Nur ein Server soll Spielentscheidungen treffen.
- Backups sollen nicht gleichzeitig Fragen starten oder Punkte vergeben.
- Es gibt eine klare Quelle der Wahrheit.
- Clients müssen nicht selbst entscheiden, welcher Server richtig ist.

Das vereinfacht die Konsistenz stark. Ohne diese Entscheidung könnten Clients
auf verschiedenen Servern unterschiedliche Spielstände sehen.

## 10. Primary-Backup-Replikation

Der Leader ist der Primary. Die anderen Server sind Backups. Wenn der
Spielzustand geändert wird, repliziert der Leader den Zustand an die Backups.

Der replizierte Zustand enthält unter anderem:

- Spieler
- Punkte
- aktuelle Runde
- aktuelle Frage
- Kategorie
- Deadline
- Teamzuordnung
- Antworten
- verarbeitete Request-IDs
- Ereignishistorie
- Sequenznummer

Warum vollständiger Zustand statt nur einzelner Änderungen?

Für dieses Projekt ist vollständige Zustandsreplikation einfacher und robuster
zu verstehen. Ein Backup muss nicht jede einzelne Operation nachbauen, sondern
kann den aktuellen Zustand übernehmen.

Vorteile:

- Ein Backup hat schnell eine vollständige Kopie.
- Nach einem Leaderwechsel kann das Spiel weiterlaufen.
- Die Logik bleibt übersichtlich.
- Das ist für die Projektgröße angemessen.

Nachteile:

- Bei sehr großen Zuständen wäre das ineffizient.
- Für ein riesiges Produktivsystem würde man eher Logs, Snapshots oder
  inkrementelle Replikation verwenden.

Für QuizBattle ist der Zustand klein. Deshalb ist diese Lösung bewusst einfach
gehalten.

## 11. JSON-kompatibler Spielzustand

Der Spielzustand besteht nur aus JSON-kompatiblen Werten: Dictionaries, Listen,
Strings, Zahlen, Booleans und `None`.

Warum?

- JSON kann einfach über TCP verschickt werden.
- Der Zustand kann tief kopiert werden.
- Backups können ihn ohne komplexe Klassenrekonstruktion übernehmen.
- Das Protokoll bleibt lesbar und debugbar.

Diese Entscheidung hilft besonders in einer Präsentation: Man kann erklären,
dass der replizierte Zustand nicht aus komplizierten Python-Objekten besteht,
sondern aus einer klar serialisierbaren Datenstruktur.

## 12. TCP-Control-Kanal mit Längenheader

Zwischen Servern wird ein eigener TCP-Kanal verwendet. Jede Nachricht wird als
JSON kodiert und bekommt vorne einen 4-Byte-Längenheader.

Warum braucht man einen Längenheader?

TCP ist ein Byte-Stream. TCP weiß nicht, wo eine einzelne JSON-Nachricht endet.
Wenn man zwei JSON-Nachrichten sendet, kann der Empfänger sie in einem Stück
oder in mehreren Stücken bekommen. Der Längenheader sagt:

```text
Die nächste Nachricht ist genau N Bytes lang.
```

Dadurch kann der Empfänger exakt eine vollständige Nachricht lesen.

Diese Entscheidung vermeidet typische TCP-Probleme und macht das Protokoll
robuster.

## 13. ACKs, Message-IDs und Wiederholungen zwischen Servern

Server-Server-Nachrichten besitzen eine `message_id`. Der Empfänger sendet ein
`CONTROL_ACK` zurück. Falls der Sender kein ACK bekommt, versucht er die
Nachricht erneut zu senden.

Warum?

- TCP-Verbindungsversuche können fehlschlagen.
- Ein Server kann kurzzeitig nicht erreichbar sein.
- Ein ACK kann verloren gehen, obwohl die Aktion ausgeführt wurde.
- Wiederholungen dürfen keine Aktion doppelt ausführen.

Deshalb merkt sich der Empfänger bereits beantwortete `message_id`s. Wenn
dieselbe Nachricht erneut kommt, wird die alte Antwort zurückgegeben, ohne die
Aktion erneut auszuführen.

Das nennt man Deduplizierung. Es macht wiederholtes Senden sicherer.

## 14. FIFO pro Zielserver durch Locks

Im Control-Kanal gibt es pro Zielserver einen Lock. Dadurch sendet ein Server
nicht mehrere Kontrollnachrichten gleichzeitig an denselben Peer.

Warum?

- Reihenfolge ist bei Wahl, Heartbeat und Replikation wichtig.
- Gleichzeitige Sends könnten schwer verständliche Race Conditions erzeugen.
- Eine geordnete Kommunikation ist leichter zu debuggen.

Diese Entscheidung macht das System konservativer, aber verständlicher und
stabiler.

## 15. Heartbeats zwischen Servern

Server senden regelmäßig Heartbeats. Das Projekt verwendet:

```text
HEARTBEAT_INTERVAL = 1.0
HEARTBEAT_TIMEOUT = 4.0
HEARTBEAT_LOG_INTERVAL = 10.0
```

Bedeutung:

- Alle 1 Sekunde wird ein Heartbeat gesendet.
- Nach ungefähr 4 Sekunden ohne Lebenszeichen gilt ein Server als ausgefallen.
- Normale Heartbeat-Logs werden nur etwa alle 10 Sekunden angezeigt, damit das
  Terminal lesbar bleibt.

Warum Heartbeats?

- Ein Backup muss erkennen, wenn der Leader abgestürzt ist.
- Nach einem Ausfall muss eine neue Wahl gestartet werden.
- Server sollen auch erkennen, wenn Backups verschwinden.

Warum nicht 10 Sekunden Intervall und 15 Sekunden Timeout?

Das wäre ruhiger, aber Failover würde deutlich länger dauern. Für eine Demo ist
ein schneller Leaderwechsel besser sichtbar. Mit 1s/4s erkennt das System einen
Ausfall schnell genug, ohne extrem aggressiv zu sein.

Wichtig: Ein Timeout beweist in einem asynchronen Netzwerk nicht sicher, dass
ein Server abgestürzt ist. Er kann auch nur langsam oder kurz getrennt sein. Das
System behandelt also Fail-stop- beziehungsweise Crash-Fehler, keine perfekte
Fehlererkennung.

## 16. Kein eigener Client-Heartbeat

Zwischen Client und Server gibt es keinen zusätzlichen eigenen
QuizBattle-Heartbeat. Clients sind über WebSocket verbunden. Wenn die Verbindung
abbricht, erkennt der Netzwerkcode den Fehler und startet die Leadersuche neu.

Warum reicht das?

- Clients sind keine Ringteilnehmer.
- Ein Client-Ausfall erfordert keine Leaderwahl.
- Der wichtige verteilte Fehlerfall ist Serverausfall.
- WebSocket/TCP liefert bereits Verbindungsfehler.

Ein eigener Client-Heartbeat wäre möglich, aber für die Projektlogik nicht
notwendig. Er wäre eher eine Komfort- oder Monitoring-Funktion.

## 17. Server als autoritativer Zustandshalter

Alle wichtigen Informationen liegen auf dem Server beziehungsweise im
replizierten Serverzustand:

- Punkte
- Runden
- aktuelle Frage
- richtige Antwort
- Teamzuordnung
- Spielphase
- Kategorieauswahl
- Reihenfolge der Events

Der Client zeigt diese Informationen nur an und sendet Benutzeraktionen.

Warum?

- Clients könnten sonst unterschiedliche Spielstände erzeugen.
- Ein Client darf nicht selbst entscheiden, ob eine Antwort richtig ist.
- Nach einem Reconnect kann der Client seinen Zustand vom Server fortsetzen.
- Der Leader kann alle Clients konsistent versorgen.

Die UI zeigt zwar Punkte an, aber diese Punkte werden nicht im Client
entschieden. Der Client bekommt sie vom Server.

## 18. Leader als Sequencer

Jedes wichtige Spielereignis bekommt eine fortlaufende Sequenznummer:

```text
seq = 1, 2, 3, 4, ...
```

Der Leader ist der einzige Sequencer. Das heißt: Nur der Leader erhöht diese
globale Nummer und hängt Ereignisse an die Ereignishistorie an.

Warum?

- Alle Clients sollen Ereignisse in derselben Reihenfolge sehen.
- Ein Client soll nicht `RESULT` vor `QUESTION` verarbeiten.
- Nach Reconnect kann der Client fehlende Sequenzen nachfordern.
- Backups übernehmen auch die Sequenznummer und Ereignishistorie.

Diese Entscheidung ist zentral für Konsistenz auf Clientseite.

## 19. Client ACKs und Resend

Clients bestätigen verarbeitete Ereignisse mit:

```text
ACK seq
```

Das bedeutet:

```text
Ich habe alle Ereignisse bis einschließlich seq verarbeitet.
```

Wenn der Client eine Lücke erkennt, sendet er:

```text
RESEND_REQUEST from_seq to_seq
```

Warum?

- Bei Reconnect können Ereignisse fehlen.
- Nachrichten können doppelt ankommen.
- Der Client soll trotzdem eine lückenlose Reihenfolge anzeigen.

Der Client besitzt eine Hold-back-Queue. Wenn Ereignis 10 kommt, aber Ereignis 9
fehlt, wird 10 zurückgehalten. Erst wenn 9 da ist, werden beide in richtiger
Reihenfolge an die GUI weitergegeben.

## 20. Hold-back-Queue im Client

Die Hold-back-Queue verhindert, dass die GUI Ereignisse in falscher Reihenfolge
anzeigt.

Beispiel:

```text
Erwartet: seq 5
Empfangen: seq 6
```

Dann wird `seq 6` gespeichert, aber noch nicht angezeigt. Der Client fordert
`seq 5` erneut an. Sobald `seq 5` kommt, wird zuerst `5`, dann `6` angezeigt.

Warum ist das sinnvoll?

- Die GUI bleibt konsistent.
- Doppelte Nachrichten werden ignoriert.
- Reconnects zerstören den Ablauf nicht.

## 21. Client-Token für Reconnect

Wenn ein Client zum ersten Mal joint, bekommt er einen Token. Dieser Token
identifiziert die Spielsitzung.

Beim Reconnect sendet der Client:

```text
JOIN:
  name
  token
  last_seq
```

Warum?

- Der Spieler bekommt nicht versehentlich einen zweiten Eintrag.
- Punkte und Spieler-ID bleiben erhalten.
- Nach Leaderwechsel kann dieselbe Sitzung fortgesetzt werden.
- Der neue Leader weiß, welche Events dem Client noch fehlen.

Diese Entscheidung ist wichtig für die Failover-Demo. Ohne Token würde ein
Reconnect wie ein neuer Spieler aussehen.

## 22. Request-IDs für Client-Aktionen

Client-Aktionen wie Antworten, Teamchat oder Kategorieauswahl bekommen eine
`request_id`.

Warum?

Der Client wiederholt unbestätigte Aktionen nach einem Reconnect oder Timeout.
Ohne `request_id` könnte dieselbe Antwort oder Kategorieauswahl mehrfach
verarbeitet werden.

Mit `request_id` kann der Server sagen:

```text
Diese Aktion kenne ich schon.
Ich liefere nur nochmal das alte Ergebnis.
```

Das macht Client-Aktionen idempotent. Idempotent bedeutet: Mehrfaches Senden hat
denselben Effekt wie einmaliges Senden.

## 23. Spielstart ab einem Spieler

Im Projekt ist `MIN_PLAYERS = 1` gesetzt. Das Spiel startet also, sobald ein
Client verbunden ist.

Warum?

- Für Tests und Demo ist ein einzelner Client praktisch.
- Man kann das Spiel ohne drei echte Laptops ausprobieren.
- Das System bleibt trotzdem multiplayerfähig.

In einer echten Quizrunde könnte man den Wert wieder auf 2 oder 3 erhöhen. Für
die Projektvorführung ist 1 bewusst einfacher.

## 24. Kategorieauswahl alle fünf Fragen

Die Fragen sind in Kategorien eingeteilt:

- Fußball
- Politik
- Geschichte
- Erdkunde (Hauptstädte)
- Allgemeinwissen

Nach jeweils fünf Fragen wird eine neue Kategorie ausgewählt. Die Clients dürfen
abwechselnd entscheiden, welche Kategorie gespielt wird.

Warum?

- Das Spiel wird interaktiver.
- Nicht nur der Server entscheidet zufällig.
- Jeder Spieler bekommt irgendwann die Möglichkeit, eine Kategorie zu wählen.
- Die Regel ist einfach erklärbar: fünf Fragen pro Kategorieblock.

Wichtig ist: Die Auswahl wird trotzdem vom Server kontrolliert. Der Client
sendet nur den Wunsch. Der Server prüft:

- Ist gerade Kategorieauswahl?
- Ist dieser Spieler dran?
- Ist die Kategorie noch verfügbar?

Erst dann startet der nächste Fragenblock.

## 25. Fragen in TinyDB

Die Fragen liegen in `tinydb.json`. Jede Frage enthält:

```json
{
  "kategorie": "Fußball",
  "frage": "...",
  "antwort": "..."
}
```

Warum TinyDB?

- Die Daten sind lokal und einfach.
- Keine separate Datenbankinstallation nötig.
- JSON ist für die Demo leicht lesbar.
- Die Fragen können schnell erweitert werden.

Warum keine zentrale externe Datenbank?

- Das Projekt soll nicht unnötig kompliziert werden.
- Die zentrale Herausforderung ist Verteilung, Leaderwahl und Replikation, nicht
  Datenbankbetrieb.
- Eine externe DB wäre ein zusätzlicher Single Point of Failure oder müsste
  selbst repliziert werden.

Die TinyDB wird beim Serverstart geladen. Der Spielzustand selbst wird danach
zwischen den Servern repliziert.

## 26. Zufällige Frage-Reihenfolge pro Kategorie

Beim Start eines Spiels werden die Fragen pro Kategorie in Pools gesammelt und
gemischt. Danach wird aus dem aktuellen Kategoriepool jeweils die nächste Frage
genommen.

Warum?

- Fragen wiederholen sich nicht sofort.
- Die Reihenfolge ist nicht immer gleich.
- Kategorien bleiben trotzdem kontrollierbar.

Die gemischten Pools sind Teil des replizierten Zustands. Dadurch übernimmt ein
Backup bei Failover dieselbe verbleibende Fragenreihenfolge.

## 27. Teamrunde jede dritte Runde

Jede dritte Runde ist eine Teamrunde. Dann werden verbundene Spieler zufällig in
Zweierteams eingeteilt. Teammitglieder können chatten und eine gemeinsame
Antwort setzen.

Warum?

- Es erfüllt die Multiplayer-Anforderung stärker als reine Einzelantworten.
- Es zeigt zusätzliche Serverlogik: Teamzuordnung, Teamchat, Teamantwort.
- Die Clients bleiben trotzdem einfach, weil der Server Teams berechnet.

Bei ungerader Spielerzahl bleibt ein Spieler übrig und beantwortet die Runde
einzeln. Dadurch blockiert das Spiel nicht, wenn die Spielerzahl nicht perfekt
teilbar ist.

## 28. GUI und Netzwerk laufen getrennt

Der PyQt-Client hat eine GUI im Hauptthread. Das Netzwerk läuft in einem eigenen
Thread mit eigenem asyncio-Event-Loop.

Warum?

- PyQt erwartet GUI-Änderungen im Hauptthread.
- Netzwerkoperationen dürfen die Oberfläche nicht einfrieren.
- Der Client kann gleichzeitig anzeigen, senden, empfangen und Timer
  aktualisieren.

Die Kommunikation zwischen Netzwerkthread und GUI läuft über Qt-Signale. Das
ist sicherer als direkte GUI-Zugriffe aus dem Netzwerkthread.

## 29. Asyncio für Server und Netzwerk

Der Server verwendet `asyncio`, WebSockets und asynchrone TCP/UDP-Kommunikation.

Warum?

- Viele Netzwerkverbindungen können gleichzeitig bearbeitet werden.
- Es braucht nicht für jeden Client oder Peer einen eigenen schweren Prozess.
- Timeouts, Heartbeats und Hintergrundtasks passen gut zu async.
- Der Code bleibt in Python relativ kompakt.

Warum kein Multiprocessing?

Multiprocessing wäre für dieses Projekt nicht zwingend notwendig. Die
Verteilung entsteht durch mehrere Serverprozesse auf mehreren Rechnern, nicht
durch mehrere lokale Prozesse innerhalb eines Servers. Die Vorlesungsinhalte zu
verteilten Systemen werden durch Netzwerkkommunikation, Leaderwahl, Replikation
und Ausfallerkennung gezeigt.

## 30. Failover-Modell: Crash/Fail-stop, nicht Byzantine

Das Projekt behandelt Serverausfälle nach dem Fail-stop-Modell:

```text
Ein Server funktioniert oder er fällt aus.
```

Das System ist nicht gegen Byzantine Faults gebaut. Byzantine Fehler wären zum
Beispiel:

- Ein Server lügt absichtlich.
- Ein Server sendet widersprüchliche Zustände.
- Ein kompromittierter Server verteilt falsche Punkte.
- Ein Server gibt sich als anderer Server aus.

Warum kein Byzantine Fault Tolerance?

- Byzantine Algorithmen sind deutlich komplexer.
- Man bräuchte Quoren, Signaturen oder andere Vertrauensmechanismen.
- Das würde das Projekt stark verkomplizieren.
- Die Anforderungen des Projekts zielen eher auf Leaderwahl, Replikation und
  Crash-Failover.

Für die Präsentation kann man sagen:

```text
Unser System toleriert Crash-/Fail-stop-Ausfälle, aber keine byzantinischen
Fehler. Das ist eine bewusste Abgrenzung.
```

## 31. Keine Authentifizierung und keine Verschlüsselung

Das Projekt nutzt normales TCP/WebSocket im lokalen Netz. Es gibt keine
Benutzerkonten, keine TLS-Verschlüsselung und keine kryptographische
Authentifizierung.

Warum?

- Das Projekt ist eine LAN-Demo.
- Der Fokus liegt auf verteilten Mechanismen.
- Security würde zusätzliche Infrastruktur erfordern.

Konsequenz:

In einem echten Produktivsystem müsste man Authentifizierung, TLS,
Input-Validation, Rechte und Schutz vor fremden Paketen ergänzen.

## 32. Backups akzeptieren keine aktiven Clients

Backups kennen zwar den Spielzustand, aber sie bedienen keine aktiven
Client-Spielaktionen. Wenn ein Client mit einem Backup spricht, wird er
abgewiesen.

Warum?

- Sonst könnten mehrere Server gleichzeitig Aktionen annehmen.
- Das würde Konflikte erzeugen.
- Primary-Backup lebt davon, dass nur der Primary schreibt.

Nach einem Leaderwechsel wird ein Backup zum neuen Leader und akzeptiert dann
Clients.

## 33. Zustand wird vor Client-Auslieferung repliziert

Wenn der Leader ein neues Spielereignis erzeugt, wird der Zustand zuerst an die
Backups repliziert. Danach wird das Ereignis an Clients gesendet.

Warum?

- Backups sollen möglichst aktuell sein.
- Wenn der Leader direkt nach dem Senden an Clients abstürzt, soll ein Backup
  den Zustand schon kennen.
- Das reduziert verlorene Spielschritte beim Failover.

Das ist eine konservative Primary-Backup-Entscheidung. Sie macht die Auslieferung
etwas langsamer, aber erhöht die Konsistenz.

## 34. Ereignishistorie bleibt erhalten

Der Server speichert alle Spielereignisse in `events`. Das ist notwendig für:

- Client-Reconnect
- ACK/Resend
- Leaderwechsel
- Nachliefern fehlender Sequenzen

Auch nach `GAME_OVER` wird die Sequenz nicht einfach zurückgesetzt. Beim
Spielreset werden Runde, Punkte und Fragen zurückgesetzt, aber die
Event-Sequenz bleibt erhalten. Dadurch wird die ACK/Resend-Logik der Clients
nicht kaputtgemacht.

## 35. Game Reset nach Spielende

Nach `GAME_OVER` bleibt das System nicht dauerhaft im Endzustand. Der Leader
wartet kurz und setzt dann den Spielzustand für ein neues Spiel zurück.

Warum?

- Für Demos muss man nicht alle Server neu starten.
- Clients können verbunden bleiben.
- Ein neues Spiel kann beginnen.

Dabei werden Punkte, Antworten, Fragenpools und Kategorien zurückgesetzt.
Spieler und Event-Sequenz bleiben kontrolliert erhalten.

## 36. Startskripte statt langer Python-Befehle

Für Server gibt es `start-server.sh`. Es kapselt den langen Python-Befehl:

```bash
./start-server.sh 5001 6001 192.168.178.50 192.168.178.255
```

Warum?

- Weniger Tippfehler in der Demo.
- Ports, Host und Broadcast sind klar getrennt.
- Identity-Dateien werden automatisch passend zum Control-Port gewählt.

Die Clientseite kann ebenfalls über `start-client.sh` gestartet werden. Auf
Windows ist langfristig ein PowerShell-Skript sinnvoller, weil Windows `.sh`
nicht nativ nutzt.

## 37. Ports sind bewusst getrennt

Ein Server hat:

- WebSocket-Port für Clients
- Control-Port für andere Server
- gemeinsamen UDP-Discovery-Port

Warum?

- Client-Traffic und Server-Koordination sind getrennt.
- Fehler sind leichter zu debuggen.
- Man kann mehrere Server auf einem Gerät starten, indem WebSocket- und
  Control-Port unterschiedlich sind.

Beispiel auf einem Raspberry Pi:

```bash
./start-server.sh 5001 6001 192.168.178.93 192.168.178.255
./start-server.sh 5002 6002 192.168.178.93 192.168.178.255
./start-server.sh 5003 6003 192.168.178.93 192.168.178.255
```

## 38. Mehrere Server auf einem Rechner möglich

Für Tests kann man mehrere Serverprozesse auf demselben Rechner starten. Dafür
brauchen sie unterschiedliche WebSocket- und Control-Ports. Der UDP-Discovery-
Port kann gemeinsam verwendet werden, wenn das Betriebssystem `SO_REUSEADDR`
beziehungsweise `SO_REUSEPORT` unterstützt.

Warum ist das praktisch?

- Man kann den Ring ohne drei echte Geräte testen.
- Failover lässt sich schneller ausprobieren.
- Entwicklung ist einfacher.

Für die eigentliche verteilte Demo sind mehrere Geräte aber überzeugender.

## 39. Logs als Präsentationshilfe

Das System loggt wichtige Ereignisse:

- Server gestartet
- Leader gewählt
- `Ich bin der Leader`
- Server entdeckt
- Ring aktualisiert
- Heartbeat Ping/Pong
- Server ausgefallen
- Replikation bestätigt oder fehlgeschlagen
- Client verbunden/getrennt

Warum?

- Man kann die verteilten Abläufe live erklären.
- Der Prof sieht, dass Wahl und Failover wirklich passieren.
- Fehler im Netzwerk werden schneller sichtbar.

Normale Heartbeat-Logs werden gedrosselt, damit das Terminal nicht jede Sekunde
unlesbar wird.

## 40. Tests

Das Projekt enthält Unit-Tests für wichtige Teile:

- Identität/UUID
- Protokoll
- LCR/Clusterlogik
- Spielzustand
- Client-Ordering

Warum Tests?

- Leaderwahl und Sequenzlogik sind fehleranfällig.
- Kleine Änderungen können sonst Failover oder Reconnect beschädigen.
- Tests geben Sicherheit vor der Präsentation.

Die Tests ersetzen keine echte Netzwerklive-Demo, aber sie prüfen die wichtigsten
lokalen Logikbausteine.

## 41. Warum das System nicht zu kompliziert gebaut wurde

Eine wichtige Designentscheidung war, das Projekt nicht unnötig zu
verkomplizieren.

Bewusst nicht eingebaut:

- externe Datenbank
- Kubernetes oder Docker-Orchestrierung
- Byzantine Fault Tolerance
- TLS und Benutzerverwaltung
- komplexes Consensus-Protokoll wie Raft oder Paxos
- echtes Load Balancing zwischen mehreren aktiven Servern

Warum?

Das Projekt soll die Vorlesungsthemen zeigen:

- Discovery
- Serverring
- Leaderwahl
- Heartbeats
- Replikation
- Failover
- geordnete Nachrichten
- Reconnect

Ein komplexeres System wäre nicht automatisch besser. Es wäre schwerer zu
erklären und schwieriger stabil vorzuführen.

## 42. Wichtigste Trade-offs

### Einfachheit gegen Skalierbarkeit

Das System repliziert den vollständigen Zustand. Das ist einfach und robust für
ein kleines Quiz. Für ein sehr großes System wäre es ineffizient.

### Schneller Failover gegen False Positives

Ein kurzer Heartbeat-Timeout erkennt Ausfälle schnell. Dafür kann ein sehr
langsamer Server theoretisch zu früh als ausgefallen gelten.

### Leader-only gegen Lastverteilung

Ein einzelner Leader ist konsistent und einfach. Dafür verteilt das System die
Clientlast nicht aktiv auf mehrere Server.

### UDP-Broadcast gegen universelle Erreichbarkeit

UDP-Broadcast ist einfach im LAN. Dafür funktioniert es nicht zuverlässig über
Router, NAT oder blockierende Hochschul-WLANs.

### Persistente UUID gegen wechselnde Leader-Chancen

Persistente UUIDs machen Serveridentitäten stabil. Dadurch gewinnt bei gleicher
Servermenge immer derselbe Server mit der höchsten UUID. Das ist für LCR korrekt,
aber nicht zufällig fair.

## 43. Gute Kurzantworten für die Präsentation

### Warum gibt es einen Leader?

Damit es genau eine autoritative Stelle gibt, die Fragen, Punkte und
Spielphasen entscheidet. Ohne Leader könnten mehrere Server unterschiedliche
Spielstände erzeugen.

### Warum UDP und TCP?

UDP wird nur für Discovery genutzt, weil Broadcast damit einfach ist und
verlorene Discovery-Pakete erneut gesendet werden können. Kritische Nachrichten
laufen über TCP/WebSocket, weil dort Reihenfolge und zuverlässigere Übertragung
wichtiger sind.

### Warum LCR?

Weil die Server als logischer Ring organisiert sind und LCR ein passender
Leaderwahlalgorithmus aus der Vorlesung ist. Die höchste UUID gewinnt.

### Warum UUIDs?

UUIDs sind eindeutig, müssen nicht manuell vergeben werden und erfüllen die
Anforderung, keine einfachen IDs zu verwenden.

### Warum behält ein Server seine UUID?

Weil die UUID in einer Identity-Datei gespeichert wird. Ein Server bleibt über
Neustarts derselbe logische Server.

### Wo liegt der Spielstand?

Der Spielstand liegt auf dem Leader und wird an die Backups repliziert. Der
Client zeigt ihn nur an.

### Was passiert beim Leaderausfall?

Backups erkennen über Heartbeat-Timeout, dass der Leader nicht mehr antwortet.
Dann wird per LCR ein neuer Leader gewählt. Clients suchen per Discovery erneut
und verbinden sich mit dem neuen Leader.

### Ist das Byzantine Fault Tolerant?

Nein. Das System behandelt Crash-/Fail-stop-Fehler. Bösartige oder lügende
Server werden nicht abgesichert.

### Warum keine feste Server-IP im Client?

Weil der Client den aktuellen Leader per UDP-Broadcast findet. Dadurch kann der
Leader wechseln, ohne dass der Client-Befehl angepasst werden muss.

## 44. Gesamtbewertung der Architektur

Die Architektur ist für das Projekt passend, weil sie die zentralen Themen eines
verteilten Systems sichtbar macht, ohne unnötig groß zu werden. Das System hat
eine klare Rollenverteilung:

```text
Client:
  Anzeige, Eingabe, Reconnect, ACK/Resend

Leader:
  Spielzustand, Sequencer, Punkte, Kategorien, Clientkommunikation

Backups:
  replizierter Zustand, Heartbeat, Wahlteilnehmer, Failover-Reserve

UDP Discovery:
  dynamisches Finden des Leaders

TCP Control:
  zuverlässige Serverkoordination
```

Damit kann man in der Präsentation gut erklären, wie aus mehreren normalen
Programmen ein verteiltes System wird: Die Prozesse finden sich, wählen einen
Leader, replizieren Zustand, erkennen Ausfälle und setzen das Spiel nach einem
Leaderwechsel fort.
