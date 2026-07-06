# QuizBattle - Dateiübersicht

Diese Datei erklärt, wofür jede wichtige Datei im Projekt `DBQuizbattle`
zuständig ist. Sie ist bewusst ausführlich geschrieben, damit man das Projekt
auch ohne viel Vorwissen nachvollziehen kann.

Nicht im Detail erklärt werden automatisch erzeugte Dateien und Ordner wie
`.git`, `.venv`, `__pycache__`, `.DS_Store` oder `.server_uuid_*`. Diese Dateien
entstehen durch Git, Python, macOS oder durch den Serverstart. Sie sind für das
Verständnis des Codes nicht der eigentliche Kern.

## 1. Gesamtüberblick

`DBQuizbattle` enthält das vollständige Projekt:

- Serverseite
- Clientseite
- Spielzustand und Spiellogik
- Server-Discovery
- Leaderwahl
- Replikation
- PyQt-GUI
- Tests
- Projektdokumente
- Frage-Datenbank

Die wichtigste Aufteilung ist:

```text
src/server.py
  startet einen Server

src/client.py
  startet einen grafischen Client

src/quizbattle/
  enthält die eigentliche Logik

tests/
  prüft wichtige Einzelteile ohne komplette Live-Demo
```

## 2. Start- und Einstiegspunkte

### `src/server.py`

**Zuständigkeit:**  
Diese Datei ist der Einstiegspunkt für einen QuizBattle-Server.

**Was macht sie im Detail?**

- Liest Kommandozeilenargumente ein.
- Entscheidet, welche Server-UUID verwendet wird.
- Lädt eine UUID aus einer Identity-Datei oder erzeugt eine neue.
- Bestimmt Host-IP, WebSocket-Port, Control-Port, Discovery-Port und Broadcast-IP.
- Baut ein `ServerConfig`-Objekt.
- Startet anschließend `QuizServer`.
- Richtet Logging ein, damit Serverereignisse im Terminal sichtbar sind.

**Warum ist sie wichtig?**

Ohne diese Datei weiß Python nicht, wie ein Serverprozess konfiguriert und
gestartet werden soll. Sie verbindet die Startparameter aus dem Terminal mit der
eigentlichen Serverlogik.

**Wichtig für Anfänger:**

Diese Datei enthält nicht die ganze Serverlogik. Sie ist eher die Eingangstür.
Die eigentliche Arbeit passiert in `server_app.py`, `cluster.py`, `game.py` und
weiteren Modulen.

### `src/client.py`

**Zuständigkeit:**  
Diese Datei ist der Einstiegspunkt für den grafischen Client.

**Was macht sie im Detail?**

- Liest den Spielernamen, den Discovery-Port und die Broadcast-Adresse.
- Baut ein `ClientConfig`-Objekt.
- Erstellt die PyQt-Anwendung.
- Öffnet das Hauptfenster `QuizWindow`.
- Startet den PyQt-Event-Loop.

**Warum ist sie wichtig?**

Der Client braucht einen GUI-Startpunkt. Diese Datei kümmert sich darum, dass
das Fenster überhaupt angezeigt wird und dass der Client weiß, mit welcher
Broadcast-Adresse er nach dem Leader suchen soll.

**Wichtig für Anfänger:**

PyQt läuft in einem eigenen GUI-Event-Loop. Deshalb sieht der Start anders aus
als bei einem normalen Konsolenprogramm.

## 3. Gemeinsame Konfiguration

### `src/quizbattle/settings.py`

**Zuständigkeit:**  
Diese Datei enthält zentrale Konstanten und Konfigurationsklassen.

**Was macht sie im Detail?**

- Definiert den Projektpfad `PROJECT_DIR`.
- Legt den Discovery-Port fest.
- Legt Heartbeat-Intervalle und Timeouts fest.
- Legt Spielparameter wie Rundendauer und Mindestspielerzahl fest.
- Definiert `ServerConfig` für Serverstarts.
- Definiert `ClientConfig` für Clientstarts.

**Warum ist sie wichtig?**

Viele Module brauchen dieselben Werte. Wenn solche Werte an vielen Stellen
hart im Code stehen würden, wäre das Projekt schwerer zu ändern. Mit
`settings.py` gibt es eine zentrale Stelle für wichtige Konstanten.

**Beispiele:**

- `DEFAULT_DISCOVERY_PORT = 5972`
- `HEARTBEAT_INTERVAL = 1.0`
- `HEARTBEAT_TIMEOUT = 4.0`
- `MIN_PLAYERS = 1`
- `ROUND_TIME = 20`

**Wichtig für Anfänger:**

Wenn man wissen will, warum das Spiel nach 20 Sekunden auswertet oder warum ein
Server nach ungefähr 4 Sekunden als ausgefallen gilt, schaut man hier.

### `src/quizbattle/__init__.py`

**Zuständigkeit:**  
Diese Datei markiert `quizbattle` als Python-Paket.

**Was macht sie im Detail?**

Sie enthält aktuell keine eigene Logik. Ihre Existenz sorgt aber dafür, dass
Python Dateien wie `quizbattle.game` oder `quizbattle.cluster` sauber importieren
kann.

**Warum ist sie wichtig?**

Ohne Paketstruktur wären Importe unübersichtlicher. Mit `quizbattle` sind die
Module logisch gruppiert.

## 4. Netzwerk-Grundlagen

### `src/quizbattle/protocol.py`

**Zuständigkeit:**  
Diese Datei enthält gemeinsame Hilfsfunktionen für Netzwerk-Nachrichten.

**Was macht sie im Detail?**

- Bestimmt eine lokale IPv4-Adresse mit `local_ip()`.
- Wandelt Python-Dictionaries in JSON-Bytes um.
- Baut TCP-Nachrichten mit 4-Byte-Längenheader.
- Liest solche laengengerahmten TCP-Nachrichten wieder ein.
- Enthält ein UDP-Datagramm-Protokoll, das empfangene JSON-Nachrichten an einen
  Callback weitergibt.

**Warum ist sie wichtig?**

TCP ist ein Datenstrom und kennt keine eingebauten Nachrichtengrenzen. Wenn man
JSON über TCP sendet, muss man selbst festlegen, wo eine Nachricht beginnt und
endet. Das macht der Längenheader.

**Wichtig für Anfänger:**

UDP-Pakete kommen als einzelne Datagramme an. TCP dagegen ist nur ein Strom von
Bytes. Darum braucht TCP hier ein eigenes Framing.

### `src/quizbattle/discovery.py`

**Zuständigkeit:**  
Diese Datei kapselt UDP-Broadcast für Discovery und Heartbeats.

**Was macht sie im Detail?**

- Öffnet einen UDP-Socket.
- Aktiviert Broadcast.
- Aktiviert nach Möglichkeit `SO_REUSEADDR` und `SO_REUSEPORT`.
- Sendet Nachrichten an eine Broadcast-Adresse oder direkt an einen Absender.
- Leitet empfangene UDP-Nachrichten an den `ClusterManager` weiter.

**Warum ist sie wichtig?**

Clients und Server sollen sich im LAN finden, ohne feste IP-Adressen zu kennen.
UDP-Broadcast ist dafür der einfache Mechanismus.

**Wichtig für Anfänger:**

Diese Datei entscheidet nicht, was eine Nachricht bedeutet. Sie ist nur der
Transport. Die Bedeutung von `CLIENT_DISCOVER`, `SERVER_JOIN` oder `HEARTBEAT`
wird in `cluster.py` verarbeitet.

## 5. Serveridentität

### `src/quizbattle/identity.py`

**Zuständigkeit:**  
Diese Datei erzeugt, prüft und speichert Server-UUIDs.

**Was macht sie im Detail?**

- Prüft, ob ein Text eine gültige UUID ist.
- Wandelt UUIDs in eine numerische Sortierreihenfolge um.
- Lädt eine UUID aus einer Identity-Datei.
- Erzeugt beim ersten Start eine neue UUID.
- Speichert die UUID sicher in einer Datei.

**Warum ist sie wichtig?**

Die Server brauchen eindeutige Identitäten für den Ring und die LCR-Leaderwahl.
Ohne stabile Identitäten könnte ein Server nach jedem Neustart als völlig neuer
Teilnehmer erscheinen.

**Wichtig für Anfänger:**

Die UUID ist nicht fest im Code eingetragen. Sie wird beim ersten Start erzeugt
und danach aus einer Datei wie `.server_uuid_6001` wiederverwendet.

## 6. Server-zu-Server-Kommunikation

### `src/quizbattle/control.py`

**Zuständigkeit:**  
Diese Datei implementiert den zuverlässigen TCP-Control-Kanal zwischen Servern.

**Was macht sie im Detail?**

- Startet einen TCP-Listener auf dem Control-Port.
- Sendet JSON-Nachrichten mit Längenheader.
- Vergibt Message-IDs.
- Wartet auf `CONTROL_ACK`.
- Wiederholt Nachrichten bei Timeout.
- Dedupliziert wiederholte Nachrichten.
- Sorgt mit Locks dafür, dass pro Zielserver nur eine Nachricht gleichzeitig
  gesendet wird.
- Bearbeitet bestimmte Ringnachrichten im Hintergrund, damit der Ring nicht
  blockiert.

**Warum ist sie wichtig?**

Leaderwahl, Replikation und Heartbeat zwischen Servern sind kritisch. Diese
Nachrichten dürfen nicht einfach unkontrolliert per UDP verschickt werden. Der
Control-Kanal macht diese Kommunikation robuster.

**Wichtig für Anfänger:**

Diese Datei ist wie ein kleiner zuverlässiger Nachrichtendienst zwischen
Servern. Sie ist nicht für Clients zuständig.

### `src/quizbattle/cluster.py`

**Zuständigkeit:**  
Diese Datei verwaltet das Servercluster.

**Was macht sie im Detail?**

- Startet Discovery und Control-Kanal.
- Speichert bekannte Server als Peers.
- Bildet den logischen Ring anhand der UUIDs.
- Bestimmt den Nachfolger im Ring.
- Verarbeitet `SERVER_DISCOVER`, `SERVER_JOIN`, `HEARTBEAT` und `SERVER_LEAVE`.
- Sendet Heartbeats.
- Erkennt ausgefallene Server über Timeout.
- Startet LCR-Leaderwahlen.
- Verarbeitet `ELECTION`- und `LEADER`-Nachrichten.
- Setzt den aktuellen Leader.
- Repliziert den Spielzustand an Backups.
- Synchronisiert neue oder zurückkehrende Server mit dem aktuellen Zustand.

**Warum ist sie wichtig?**

`cluster.py` ist das Herz der verteilten Serverlogik. Hier passieren die Themen,
die für die Vorlesung besonders wichtig sind: Ring, Leaderwahl, Heartbeats,
Failover und Replikation.

**Wichtig für Anfänger:**

Der Ring ist logisch, nicht physisch. Die Server sind nicht wirklich mit Kabeln
im Ring verbunden. Der Ring entsteht durch Sortierung der UUIDs.

## 7. Spielserver und WebSocket-Clients

### `src/quizbattle/server_app.py`

**Zuständigkeit:**  
Diese Datei verbindet Servercluster, Spiellogik und Client-WebSockets.

**Was macht sie im Detail?**

- Startet den WebSocket-Server.
- Startet den `ClusterManager`.
- Erstellt die `QuizGame`-Instanz.
- Nimmt Client-Verbindungen nur an, wenn dieser Server Leader ist.
- Sendet `NOT_LEADER`, wenn ein Client versehentlich ein Backup erreicht.
- Registriert neue Spieler oder setzt vorhandene Tokens fort.
- Sendet `WELCOME` an Clients.
- Liefert verpasste Events nach.
- Verarbeitet `ACK`, `RESEND_REQUEST` und Spieleraktionen.
- Erzeugt geordnete Events mit Sequenznummer.
- Repliziert Zustand vor dem Versand an Clients.
- Wiederholt nicht bestätigte Events.

**Warum ist sie wichtig?**

Diese Datei ist die Brücke zwischen der verteilten Serverwelt und der
Clientwelt. Ohne sie gäbe es zwar Spiel- und Clusterlogik, aber keine
WebSocket-Sitzungen für echte Spieler.

**Wichtig für Anfänger:**

Der Server ist autoritativ. Clients senden nur Wünsche wie "Antwort X" oder
"Kategorie Y". Der Server entscheidet, ob das erlaubt ist und was daraus wird.

## 8. Spiellogik

### `src/quizbattle/game.py`

**Zuständigkeit:**  
Diese Datei enthält die zentrale Quizlogik und den replizierbaren Spielzustand.

**Was macht sie im Detail?**

- Lädt Fragen aus `tinydb.json`.
- Erzeugt den initialen Spielzustand.
- Speichert Spieler, Punkte, Runde, Frage, Teams und Events.
- Verwaltet Kategorien und Kategorieauswahl.
- Startet alle fünf Fragen eine neue Kategorieauswahl.
- Bestimmt, welcher Spieler die nächste Kategorie wählen darf.
- Startet neue Runden.
- Unterscheidet Einzelrunde und Teamrunde.
- Bildet in jeder dritten Runde Teams.
- Speichert Antworten und Teamantworten.
- Verarbeitet Teamchat.
- Vergibt Punkte.
- Erzeugt Ergebnisereignisse.
- Setzt das Spiel nach `GAME_OVER` wieder zurück.
- Nutzt Request-IDs, damit wiederholte Clientaktionen nicht doppelt wirken.

**Warum ist sie wichtig?**

Hier liegt die eigentliche Spielregel-Logik. Wenn man wissen will, warum Punkte
vergeben werden, wann Teamrunden entstehen oder wie Kategorien gewechselt
werden, schaut man in diese Datei.

**Wichtig für Anfänger:**

Der Spielzustand besteht aus JSON-kompatiblen Daten. Dadurch kann er einfach an
Backups repliziert werden.

## 9. Client-Netzwerk im Hauptprojekt

### `src/quizbattle/client_network.py`

**Zuständigkeit:**  
Diese Datei enthält die Netzwerklogik des Clients.

**Was macht sie im Detail?**

- Läuft in einem eigenen Thread, damit die PyQt-GUI nicht einfriert.
- Sucht den Leader per UDP-Broadcast.
- Baut eine WebSocket-Verbindung zum Leader auf.
- Sendet `JOIN` mit Name, Token und letzter Sequenznummer.
- Empfängt Servernachrichten.
- Verarbeitet `WELCOME`, `NOT_LEADER` und `ACTION_STATUS`.
- Übergibt sequenzierte Events an den `OrderedEventBuffer`.
- Sendet `ACK` für verarbeitete Events.
- Fordert fehlende Events per `RESEND_REQUEST` an.
- Wiederholt unbestätigte Spieleraktionen.
- Vergibt Request-IDs für Aktionen wie Antwort, Teamchat und Kategorieauswahl.

**Warum ist sie wichtig?**

Ohne diese Datei könnte der Client weder den Leader finden noch robust nach
einem Leaderausfall wieder verbinden.

**Wichtig für Anfänger:**

Diese Datei zeichnet nichts auf den Bildschirm. Sie sendet Status und
Nachrichten über Qt-Signale an `client_ui.py`.

### `src/quizbattle/client_ordering.py`

**Zuständigkeit:**  
Diese Datei sortiert Serverevents anhand ihrer Sequenznummern.

**Was macht sie im Detail?**

- Speichert die zuletzt verarbeitete Sequenznummer.
- Ignoriert alte oder doppelte Events.
- Hält zu frühe Events in einer Hold-back-Queue zurück.
- Erkennt Lücken in der Sequenz.
- Meldet dem Netzwerkcode, welche Sequenzen fehlen.

**Warum ist sie wichtig?**

Clients sollen Events in der richtigen Reihenfolge anzeigen. Ein `RESULT` vor
der passenden `QUESTION` wäre falsch. Die Hold-back-Queue verhindert solche
Reihenfolgeprobleme.

**Wichtig für Anfänger:**

Diese Datei ist klein, aber sehr wichtig für Konsistenz auf Clientseite.

### `src/quizbattle/client_ui.py`

**Zuständigkeit:**  
Diese Datei enthält die grafische Oberfläche des Clients.

**Was macht sie im Detail?**

- Baut das PyQt-Fenster.
- Zeigt Punkte, Zeit, Frage, Status und Teamchat.
- Aktiviert/deaktiviert Eingabefelder passend zur Spielphase.
- Zeigt Kategoriebuttons.
- Erlaubt Kategorieauswahl nur beim aktuell berechtigten Spieler.
- Sendet Antworten an `client_network.py`.
- Sendet Teamnachrichten.
- Zeigt Ergebnisse und Rangliste.
- Reagiert auf `GAME_RESET`, damit ein neues Spiel sauber startet.

**Warum ist sie wichtig?**

Diese Datei ist das, was der Benutzer direkt sieht. Sie übersetzt technische
Serverevents in verständliche UI-Zustände.

**Wichtig für Anfänger:**

Die UI entscheidet nicht über Punkte oder richtige Antworten. Sie zeigt nur an,
was der Server entschieden hat.

## 10. Skripte

### `start-server.sh`

**Zuständigkeit:**  
Dieses Skript vereinfacht den Serverstart.

**Was macht es im Detail?**

- Erwartet WebSocket-Port und Control-Port.
- Optional können LAN-IP, Broadcast-IP und Identity-Datei angegeben werden.
- Erzeugt standardmäßig eine Identity-Datei wie `.server_uuid_6001`.
- Startet intern `python3 src/server.py` mit den passenden Argumenten.

**Warum ist es wichtig?**

Der eigentliche Python-Befehl wäre lang und fehleranfällig. Das Skript macht
den Start für Demo und Tests einfacher.

### `start-client.sh`

**Zuständigkeit:**  
Dieses Skript vereinfacht den Clientstart auf Unix/macOS/Linux.

**Was macht es im Detail?**

- Nimmt einen Spielernamen entgegen.
- Nimmt optional eine Broadcast-IP entgegen.
- Startet `src/client.py` mit `--name` und `--broadcast`.

**Warum ist es wichtig?**

Man muss sich den kompletten Python-Befehl nicht merken.

**Wichtig für Anfänger:**

Für Windows ist ein PowerShell-Skript langfristig passender, weil `.sh` dort
nicht nativ ausgeführt wird.

### `change_font_size.py`

**Zuständigkeit:**  
Dieses Hilfsskript verändert die Schriftgröße von Textfeldern in einem PDF.

**Was macht es im Detail?**

- Öffnet `DS_Project_Report_Form.pdf`.
- Sucht Textfeld-Annotationen.
- Setzt deren Darstellungsanweisung auf kleinere Helvetica-Schrift.
- Schreibt eine neue PDF-Datei mit angepasstem Namen.

**Warum ist es wichtig?**

Dieses Skript gehört nicht zur QuizBattle-Laufzeit. Es wurde für das
Projektformular verwendet, damit mehr Text lesbar in die PDF-Felder passt.

## 11. Daten und Dokumentation

### `tinydb.json`

**Zuständigkeit:**  
Diese Datei ist die lokale Frage-Datenbank.

**Was macht sie im Detail?**

- Enthält Quizfragen.
- Jede Frage hat eine Kategorie, einen Fragetext und eine Antwort.
- Kategorien sind zum Beispiel Fußball, Politik, Geschichte, Erdkunde und
  Allgemeinwissen.

**Warum ist sie wichtig?**

Ohne diese Datei hätte das Spiel keine Fragen. Sie ist bewusst einfach gehalten,
damit man Fragen leicht ändern oder erweitern kann.

### `README.md`

**Zuständigkeit:**  
Diese Datei erklärt Installation, Start und Grundverhalten des Projekts.

**Was macht sie im Detail?**

- Beschreibt die umgesetzten Anforderungen.
- Erklärt Netzwerkports.
- Zeigt Startbefehle für Server und Clients.
- Erklärt Discovery und Reconnect.
- Beschreibt Spielablauf und Zuverlässigkeitsmechanismen.
- Listet die Codeaufteilung.

**Warum ist sie wichtig?**

Die README ist die erste Datei, die jemand lesen sollte, um das Projekt zu
starten.

### `DESIGN_DECISIONS.md`

**Zuständigkeit:**  
Diese Datei erklärt die Architektur- und Designentscheidungen.

**Was macht sie im Detail?**

- Begründet Leader/Backup.
- Erklärt UDP, TCP und WebSocket.
- Beschreibt UUIDs, Ring, LCR, Replikation und Failover.
- Erklärt Client-ACKs, Resend, Hold-back-Queue und Request-IDs.
- Nennt Trade-offs und Präsentationsantworten.

**Warum ist sie wichtig?**

Für die Präsentation ist nicht nur wichtig, dass der Code funktioniert, sondern
auch warum er so gebaut wurde.

### `FILE_OVERVIEW.md`

**Zuständigkeit:**  
Diese Datei, die du gerade liest.

**Was macht sie im Detail?**

Sie erklärt die Aufgabe jeder wichtigen Datei im Projekt.

**Warum ist sie wichtig?**

Sie hilft beim Lernen, beim Präsentieren und beim schnellen Wiederfinden von
Code.

### `requirements.txt`

**Zuständigkeit:**  
Diese Datei listet externe Python-Abhängigkeiten.

**Was macht sie im Detail?**

Sie enthält:

- `PyQt6` für die grafische Oberfläche.
- `tinydb` für die lokale Frage-Datenbank.
- `websockets` für WebSocket-Kommunikation.

**Warum ist sie wichtig?**

Mit `pip install -r requirements.txt` kann ein Rechner die benötigten Pakete
installieren.

### PDF-Dateien

Im Projekt liegen mehrere PDF-Dateien:

- `DS_Preliminary_Updated_Project_Form.pdf`
- `DS_Project_Report_Form.pdf`
- `DS_Project_Report_Form_font_7.pdf`
- `DS_Project_Report_Form_13.pdf`

**Zuständigkeit:**  
Diese Dateien gehören zur Projektabgabe beziehungsweise zum Formular.

**Was machen sie im Detail?**

Sie enthalten keine Laufzeitlogik. Sie dokumentieren Anforderungen,
Projektangaben oder ausgefüllte Abgabeinformationen.

**Warum sind sie wichtig?**

Sie sind für Abgabe und Nachvollziehbarkeit relevant, aber nicht für den
Programmstart.

## 12. Tests

### `tests/test_cluster.py`

**Zuständigkeit:**  
Diese Datei testet zentrale Clusterregeln.

**Was macht sie im Detail?**

- Prüft Ring-Sortierung.
- Prüft den Nachfolger im Ring.
- Prüft, dass alte Gossip-Daten ausgefallene Server nicht wiederbeleben.
- Prüft LCR-Regeln.
- Prüft, dass eine zurückkehrende eigene UUID zur Leaderwahl führt.
- Prüft Replikations-ACKs mit Versionen.

**Warum ist sie wichtig?**

Clusterlogik ist schwer live zu debuggen. Tests geben Sicherheit, dass die
Grundregeln funktionieren.

### `tests/test_game.py`

**Zuständigkeit:**  
Diese Datei testet die Spiellogik.

**Was macht sie im Detail?**

- Prüft, dass Fragen unabhängig vom aktuellen Terminalpfad geladen werden.
- Prüft Request-ID-Deduplizierung.
- Prüft öffentliche Scores ohne geheime Tokens.
- Prüft Teambildung.
- Prüft Rundenereignisse.
- Prüft Kategorieauswahl.
- Prüft Game Reset nach Spielende.

**Warum ist sie wichtig?**

Die Spiellogik enthält viele Regeln. Tests verhindern, dass Änderungen
versehentlich Antworten, Kategorien oder Resets kaputtmachen.

### `tests/test_identity.py`

**Zuständigkeit:**  
Diese Datei testet die Server-UUID-Logik.

**Was macht sie im Detail?**

- Prüft, dass eine erzeugte UUID beim nächsten Laden wiederverwendet wird.
- Prüft, dass ungültige UUIDs abgelehnt werden.

**Warum ist sie wichtig?**

Stabile UUIDs sind für Ring und Leaderwahl entscheidend.

### `tests/test_ordering.py`

**Zuständigkeit:**  
Diese Datei testet die Client-Hold-back-Queue.

**Was macht sie im Detail?**

- Prüft, dass zu frühe Events zurückgehalten werden.
- Prüft, dass fehlende Sequenzen erkannt werden.
- Prüft, dass doppelte Events nicht erneut ausgeliefert werden.

**Warum ist sie wichtig?**

Die Clientanzeige muss Events in richtiger Reihenfolge sehen.

### `tests/test_protocol.py`

**Zuständigkeit:**  
Diese Datei testet das TCP-Framing.

**Was macht sie im Detail?**

- Baut eine laengengerahmte JSON-Nachricht.
- Liest sie wieder aus einem Stream.
- Prüft, dass auch UTF-8-Zeichen korrekt erhalten bleiben.

**Warum ist sie wichtig?**

Server-Server-Kommunikation basiert auf diesem Nachrichtenformat. Wenn das
Framing falsch wäre, könnten Wahl und Replikation unzuverlässig werden.

## 13. Automatisch erzeugte oder lokale Dateien

### `.server_uuid_*`

**Zuständigkeit:**  
Diese Dateien speichern persistente Server-UUIDs.

**Warum sind sie wichtig?**

Sie sorgen dafür, dass ein Server nach einem Neustart dieselbe Identität
behält.

**Wichtig:**

Diese Dateien dürfen nicht gleichzeitig von zwei laufenden Servern als gleiche
Identität verwendet werden.

### `.env`, `.python-version`, `.gitignore`

**Zuständigkeit:**  
Diese Dateien sind Entwicklungs- und Umgebungshilfen.

**Warum sind sie wichtig?**

Sie beeinflussen lokale Python-Versionen, ignorierte Dateien oder lokale
Konfiguration, sind aber nicht Teil der verteilten Laufzeitlogik.

## 14. Wie die Dateien zusammenspielen

Ein typischer Serverstart läuft so:

```text
start-server.sh
  -> src/server.py
    -> settings.py / identity.py
    -> server_app.py
      -> cluster.py
        -> discovery.py
        -> control.py
      -> game.py
```

Ein typischer Clientstart läuft so:

```text
start-client.sh
  -> src/client.py
    -> client_ui.py
      -> client_network.py
        -> client_ordering.py
```

Wenn ein Spieler antwortet:

```text
client_ui.py
  -> client_network.py
    -> WebSocket
      -> server_app.py
        -> game.py
          -> server_app.py erzeugt Event
            -> cluster.py repliziert Zustand
            -> server_app.py sendet Event an Clients
```

Wenn ein Leader ausfällt:

```text
cluster.py Heartbeat-Timeout
  -> Server aus Ring entfernen
  -> LCR-Wahl starten
  -> neuer Leader
  -> server_app.py startet Spiel-Loop
  -> Clients entdecken neuen Leader per client_network.py
```

## 15. Wichtigste Dateien für die Präsentation

Wenn man nicht jede Datei im Detail zeigen kann, sind diese Dateien am
wichtigsten:

| Datei | Warum zeigen? |
| --- | --- |
| `cluster.py` | Ring, Heartbeats, LCR, Replikation |
| `server_app.py` | Leader-only Clients, Sequenznummern, ACK/Resend |
| `game.py` | Spielzustand, Kategorien, Teams, Punkte |
| `client_network.py` | Discovery, Reconnect, Request-IDs |
| `client_ordering.py` | Hold-back-Queue und geordnete Events |
| `identity.py` | persistente UUIDs |
| `tinydb.json` | Fragen und Kategorien |

## 16. Referenz: Funktionen, Klassen und Konstanten

Dieser Abschnitt ist als Nachschlagewerk gedacht. Oben wurde erklärt, wofür die
Dateien insgesamt zuständig sind. Hier steht zusätzlich, welche wichtigen
Klassen, Funktionen, Konstanten und Variablen in den Dateien vorkommen.

### `src/server.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `parse_config()` | Funktion | Liest Serverargumente aus dem Terminal, lädt oder erzeugt die Server-UUID und baut daraus ein `ServerConfig`-Objekt. |
| `main()` | async Funktion | Richtet Logging ein, erzeugt `QuizServer`, startet ihn und sorgt beim Beenden für `server.stop()`. |
| `argparse.ArgumentParser` | lokale Variable/Objekt | Beschreibt, welche Startparameter der Server akzeptiert, zum Beispiel `--host`, `--ws-port`, `--control-port` und `--broadcast`. |
| `identity` | lokale Variable | Mutually-exclusive Argumentgruppe: Es darf entweder `--uuid` oder `--identity-file` verwendet werden, aber nicht beides gleichzeitig. |
| `server_uuid` | lokale Variable | Die endgültige UUID dieses Serverprozesses. Sie wird für Ring und Leaderwahl verwendet. |
| `identity_file` | lokale Variable | Pfad zur Datei, in der die persistente UUID gespeichert wird. |

### `src/client.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `parse_config()` | Funktion | Liest Clientargumente wie Name, Discovery-Port und Broadcast-IP und baut daraus ein `ClientConfig`-Objekt. |
| `app` | lokale Variable | Die PyQt-Anwendung. Sie verwaltet den GUI-Event-Loop. |
| `window` | lokale Variable | Das Hauptfenster des Clients, also eine Instanz von `QuizWindow`. |

### `src/quizbattle/settings.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `PROJECT_DIR` | Konstante | Absoluter Pfad zum Projektordner. Wichtig, damit `tinydb.json` unabhängig vom aktuellen Terminalordner gefunden wird. |
| `DEFAULT_DISCOVERY_PORT` | Konstante | UDP-Port für Discovery und UDP-Heartbeats. Server und Client müssen denselben Wert verwenden. |
| `HEARTBEAT_INTERVAL` | Konstante | Abstand in Sekunden, in dem Server Heartbeats senden. Aktuell schnell gewählt, damit Failover in der Demo sichtbar ist. |
| `HEARTBEAT_TIMEOUT` | Konstante | Zeit ohne Lebenszeichen, nach der ein Peer als ausgefallen gilt. |
| `HEARTBEAT_LOG_INTERVAL` | Konstante | Drosselt normale Heartbeat-Logs, damit das Terminal nicht jede Sekunde überläuft. |
| `CONTROL_TIMEOUT` | Konstante | Timeout für einzelne TCP-Control-Operationen zwischen Servern. |
| `CONTROL_RETRIES` | Konstante | Anzahl der Wiederholungen für Control-Nachrichten. |
| `CLIENT_RETRY_INTERVAL` | Konstante | Abstand, nach dem der Server unbestätigte Clientevents erneut sendet. |
| `MIN_PLAYERS` | Konstante | Mindestanzahl verbundener Clients, bevor das Spiel startet. |
| `ROUND_TIME` | Konstante | Dauer einer Fragerunde in Sekunden. |
| `RESULT_TIME` | Konstante | Dauer der Ergebnisphase in Sekunden. |
| `ServerConfig` | Datenklasse | Bündelt alle Startinformationen eines Servers: UUID, Host, Ports und Broadcast-IP. |
| `ClientConfig` | Datenklasse | Bündelt Name, Discovery-Port und Broadcast-IP eines Clients. |

### `src/quizbattle/identity.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `normalize_uuid(value)` | Funktion | Prüft, ob ein Wert eine gültige UUID ist, und gibt sie in kanonischer Schreibweise zurück. |
| `uuid_order_key(value)` | Funktion | Wandelt eine UUID in eine Zahl um. Diese Zahl wird für Ringsortierung und LCR-Vergleich verwendet. |
| `load_or_create_uuid(identity_file)` | Funktion | Lädt eine UUID aus einer Datei oder erzeugt beim ersten Start eine neue und speichert sie. |
| `generated` | lokale Variable | Neu erzeugte UUID, wenn noch keine Identity-Datei existiert. |
| `descriptor` | lokale Variable | Datei-Handle aus `os.open`; wird mit `O_EXCL` geöffnet, damit parallele Starts die Datei nicht überschreiben. |

### `src/quizbattle/protocol.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `MAX_FRAME_SIZE` | Konstante | Sicherheitsgrenze für TCP-Control-Nachrichten. Zu große Frames werden abgelehnt. |
| `local_ip()` | Funktion | Fragt beim Betriebssystem ab, welche lokale IPv4-Adresse wahrscheinlich für LAN-Kommunikation genutzt wird. |
| `json_bytes(message)` | Funktion | Kodiert ein Python-Dictionary als kompakte UTF-8-JSON-Bytes. |
| `frame_message(message)` | Funktion | Setzt vor eine JSON-Nachricht einen 4-Byte-Längenheader für TCP. |
| `read_frame(reader)` | async Funktion | Liest aus einem TCP-Stream genau eine vollständige laengengerahmte JSON-Nachricht. |
| `send_frame(writer, message)` | async Funktion | Sendet eine gerahmte Nachricht über TCP und leert den Schreibpuffer. |
| `DatagramProtocol` | Klasse | Kleiner Adapter für asyncio-UDP: dekodiert UDP-Daten und ruft ein Callback auf. |
| `DatagramProtocol.callback` | Instanzvariable | Funktion, die gültige UDP-Nachrichten verarbeitet. |
| `datagram_received(data, address)` | Methode | Wird von asyncio aufgerufen, sobald ein UDP-Paket empfangen wurde. |

### `src/quizbattle/discovery.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `BroadcastEndpoint` | Klasse | Kapselt UDP-Broadcast für Discovery und Heartbeats. |
| `bind_host` | Instanzvariable | Lokale Adresse, auf der der UDP-Socket lauscht, meist `0.0.0.0`. |
| `port` | Instanzvariable | UDP-Port für Discovery. |
| `broadcast_ip` | Instanzvariable | Zieladresse für Broadcasts, zum Beispiel `192.168.178.255`. |
| `callback` | Instanzvariable | Funktion, an die empfangene Nachrichten weitergereicht werden. |
| `transport` | Instanzvariable | asyncio-Transportobjekt für den UDP-Socket. |
| `start()` | async Methode | Öffnet den UDP-Socket und aktiviert Broadcast sowie Port-Wiederverwendung. |
| `send(message, target=None)` | Methode | Sendet eine JSON-Nachricht entweder an ein konkretes Ziel oder als Broadcast. |
| `close()` | Methode | Schließt den UDP-Endpunkt. |

### `src/quizbattle/control.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `DEFERRED_MESSAGE_TYPES` | Konstante | Nachrichtentypen, die schnell bestätigt und danach im Hintergrund verarbeitet werden. |
| `ReliableControlChannel` | Klasse | Zuständig für bestätigte TCP-Nachrichten zwischen Servern. |
| `config` | Instanzvariable | Serverkonfiguration mit Host, Ports und UUID. |
| `sender_address` | Callback | Liefert die eigene Serveradresse für ausgehende Nachrichten. |
| `peer_lookup` | Callback | Findet Verbindungsdaten eines Zielservers anhand seiner UUID. |
| `sender_seen` | Callback | Meldet dem Cluster, dass ein Sender direkt gesehen wurde. |
| `message_handler` | Callback | Verarbeitet den Inhalt einer empfangenen Control-Nachricht. |
| `server` | Instanzvariable | asyncio-TCP-Server für eingehende Control-Verbindungen. |
| `peer_locks` | Instanzvariable | Locks pro Zielserver, damit Nachrichten pro Peer geordnet gesendet werden. |
| `inbound_locks` | Instanzvariable | Locks pro Absender, damit aufgeschobene Nachrichten in Reihenfolge verarbeitet werden. |
| `responses` | Instanzvariable | Cache alter ACKs, damit wiederholte Nachrichten nicht doppelt ausgeführt werden. |
| `start()` | async Methode | Startet den TCP-Listener. |
| `handle_connection(reader, writer)` | async Methode | Liest eine Anfrage, verarbeitet sie und sendet ein ACK zurück. |
| `receive(message)` | async Methode | Dedupliziert und verarbeitet eine eingehende Nachricht. |
| `handle_deferred(message)` | async Methode | Verarbeitet aufgeschobene Nachrichten im Hintergrund. |
| `send(message, server_uuid, retries=...)` | async Methode | Sendet eine Control-Nachricht mit Wiederholungen an einen Peer. |
| `prepare_message(message)` | Methode | Ergänzt `message_id` und Absenderdaten. |
| `send_once(payload, peer)` | async Methode | Führt genau einen TCP-Sendeversuch aus. |
| `forget_peer(server_uuid)` | Methode | Entfernt Locks eines nicht mehr bekannten Peers. |
| `stop()` | async Methode | Beendet den TCP-Listener. |

### `src/quizbattle/cluster.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `ClusterManager` | Klasse | Verwalter des Serverclusters: Membership, Ring, Leaderwahl, Heartbeat und Replikation. |
| `peers` | Instanzvariable | Dictionary aller bekannten anderen Server. |
| `dead_peers` | Instanzvariable | Server, die als ausgefallen markiert wurden. |
| `leader_uuid` | Instanzvariable | UUID des aktuell bekannten Leaders. |
| `participant` | Instanzvariable | Merkt, ob dieser Server gerade an einer LCR-Wahl teilnimmt. |
| `last_heartbeat_log` | Instanzvariable | Zeitpunkt des letzten normalen Heartbeat-Logs. |
| `election_lock` | Instanzvariable | Verhindert parallele Wahlstarts im selben Prozess. |
| `discovery` | Instanzvariable | UDP-Broadcast-Endpunkt. |
| `control` | Instanzvariable | Zuverlässiger TCP-Control-Kanal. |
| `is_leader` | Property | Gibt `True` zurück, wenn die eigene UUID die aktuelle Leader-UUID ist. |
| `ring()` | Methode | Gibt alle bekannten Server-UUIDs sortiert als logischen Ring zurück. |
| `successor()` | Methode | Bestimmt den nächsten Server im Ring. |
| `start()` | async Methode | Startet Discovery, Control-Kanal, Heartbeats und initiale Leaderwahl. |
| `server_address()` | Methode | Erstellt die eigene Netzwerkadresse als Dictionary. |
| `server_message(message_type)` | Methode | Erzeugt eine Servermeldung mit Typ und eigener Adresse. |
| `send_discovery(message, target=None)` | async Methode | Sendet eine UDP-Discovery-Nachricht. |
| `broadcast_announcement(message_type)` | async Methode | Sendet eine Servermeldung per Broadcast. |
| `should_log_heartbeat()` | Methode | Entscheidet, ob ein normaler Heartbeat-Log gerade ausgegeben werden soll. |
| `handle_discovery(message, address)` | async Methode | Verarbeitet UDP-Discovery, Server-Joins, Heartbeats und Client-Suchen. |
| `register_peer(message, directly_seen=True)` | Methode | Fügt einen Server zur lokalen Peer-Liste hinzu oder aktualisiert ihn. |
| `remove_peer(server_uuid)` | Methode | Entfernt einen Server und markiert ihn als ausgefallen. |
| `heartbeat_loop()` | async Methode | Sendet regelmäßig UDP- und TCP-Heartbeats. |
| `peer_monitor_loop()` | async Methode | Erkennt Peers, deren Heartbeat-Timeout überschritten wurde. |
| `control_sender_seen(sender)` | async Methode | Aktualisiert Peers, wenn sie über TCP direkt gesehen wurden. |
| `send_control(message, server_uuid, retries=...)` | async Methode | Delegiert Control-Nachrichten an `ReliableControlChannel`. |
| `handle_control(message)` | async Methode | Verteilt eingehende TCP-Control-Nachrichten auf Wahl, Replikation und Heartbeat. |
| `start_election(force=False)` | async Methode | Startet eine LCR-Wahl mit der eigenen UUID als Kandidat. |
| `handle_election(message)` | async Methode | Vergleicht Kandidaten-UUIDs und leitet LCR-Nachrichten weiter. |
| `become_leader()` | async Methode | Setzt diesen Server als Leader und informiert den Ring. |
| `handle_leader(message)` | async Methode | Übernimmt eine Leader-Bekanntgabe aus dem Ring. |
| `replicate_state()` | async Methode | Repliziert den aktuellen Spielzustand an alle Backups. |
| `replicate_to_peer(server_uuid)` | async Methode | Repliziert den Zustand an genau einen Server. |
| `synchronize_from_leader()` | async Methode | Holt als Backup den Zustand vom Leader. |
| `stop()` | async Methode | Beendet Cluster-Hintergrundaufgaben und Netzwerkendpunkte. |

### `src/quizbattle/game.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `CATEGORY_BLOCK_SIZE` | Konstante | Anzahl Fragen, die nach einer Kategorieauswahl gespielt werden. |
| `DEFAULT_CATEGORIES` | Konstante | Bevorzugte Reihenfolge der bekannten Kategorien. |
| `load_questions()` | Funktion | Lädt alle Fragen aus `tinydb.json`. |
| `initial_state()` | Funktion | Erzeugt den vollständigen, replizierbaren Anfangszustand des Spiels. |
| `QuizGame` | Klasse | Enthält Spieler, Fragen, Kategorien, Runden, Antworten, Teams und Punkte. |
| `connected_tokens` | Callback | Liefert aktuell verbundene Spieler-Tokens. |
| `emit_event` | Callback | Erzeugt ein geordnetes Event über `server_app.py`. |
| `replicate_state` | Callback | Löst Replikation des Zustands an Backups aus. |
| `questions` | Instanzvariable | Liste aller geladenen Fragen. |
| `state` | Instanzvariable | Der komplette Spielzustand, der an Backups repliziert wird. |
| `replace_state(state)` | Methode | Ersetzt den lokalen Zustand durch eine Kopie vom Leader. |
| `mark_changed()` | Methode | Erhöht die Zustandsversion nach Änderungen. |
| `categories()` | Methode | Gibt verfügbare Kategorien in stabiler Reihenfolge zurück. |
| `ensure_category_questions()` | Methode | Erstellt gemischte Fragepools pro Kategorie. |
| `available_categories()` | Methode | Gibt Kategorien zurück, in denen noch Fragen übrig sind. |
| `ordered_player_tokens(connected_only=False)` | Methode | Sortiert Spieler stabil nach Spieler-ID. |
| `category_chooser()` | Methode | Bestimmt, welcher Spieler als nächstes eine Kategorie wählen darf. |
| `add_or_resume_player(requested_token, name)` | async Methode | Registriert einen neuen Spieler oder setzt eine bekannte Sitzung fort. |
| `handle_action(token, message)` | async Methode | Verarbeitet Antwort, Teamantwort, Teamchat oder Kategorieauswahl. |
| `handle_category_choice(token, message)` | async Methode | Prüft und übernimmt eine Kategorieauswahl. |
| `remember_request(request_id, status, replicate=True)` | async Methode | Speichert Ergebnis einer Clientaktion zur Deduplizierung. |
| `team_for(token)` | Methode | Findet das Team eines Spielers. |
| `run(is_leader)` | async Methode | Führt den Spielzustandsautomaten aus, solange dieser Server Leader ist. |
| `reset_for_new_game()` | async Methode | Setzt Runden, Punkte und Fragen nach Spielende zurück. |
| `start_category_selection()` | async Methode | Erzeugt ein Event zur Kategorieauswahl. |
| `next_question_index()` | Methode | Nimmt die nächste Frage aus dem aktuellen Kategoriepool. |
| `start_next_round()` | async Methode | Startet die nächste Frage oder eine neue Kategorieauswahl. |
| `create_teams()` | Methode | Mischt verbundene Spieler und bildet Zweierteams. |
| `public_teams()` | Methode | Wandelt interne Tokens in öffentliche Teamdaten um. |
| `public_scores()` | Methode | Erzeugt eine Rangliste ohne geheime Tokens. |
| `evaluate_round()` | async Methode | Vergleicht Antworten, vergibt Punkte und sendet ein Ergebnisevent. |

### `src/quizbattle/server_app.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `QuizServer` | Klasse | Verbindet WebSocket-Clients, `QuizGame` und `ClusterManager`. |
| `connections` | Instanzvariable | Aktive WebSocket-Verbindungen pro Spieler-Token. |
| `client_acks` | Instanzvariable | Letzte bestätigte Sequenznummer pro Client. |
| `client_last_send` | Instanzvariable | Zeitpunkt des letzten Event-Versands pro Client. |
| `game_task` | Instanzvariable | Hintergrundtask für den Spielzustandsautomaten des Leaders. |
| `retry_task` | Instanzvariable | Hintergrundtask für erneutes Senden unbestätigter Events. |
| `ws_server` | Instanzvariable | WebSocket-Serverobjekt. |
| `game` | Instanzvariable | Instanz der Spiellogik `QuizGame`. |
| `cluster` | Instanzvariable | Instanz des `ClusterManager`. |
| `start()` | async Methode | Startet WebSocket-Server und Cluster. |
| `on_became_leader()` | async Methode | Startet den Spiel-Loop, sobald dieser Server Leader wird. |
| `replicate_state()` | async Methode | Delegiert Zustandsreplikation an den Cluster. |
| `emit_event(event_type, **data)` | async Methode | Erzeugt ein sequenziertes Event, repliziert Zustand und sendet an Clients. |
| `broadcast_clients(event)` | async Methode | Sendet ein Event an alle verbundenen Clients. |
| `client_retry_loop()` | async Methode | Sendet fehlende/unbestätigte Events erneut. |
| `event_by_sequence(sequence)` | Methode | Sucht ein Event anhand seiner Sequenznummer. |
| `send_event_range(websocket, start, end=None)` | async Methode | Sendet alte Events in einem Sequenzbereich erneut. |
| `handle_client(websocket)` | async Methode | Nimmt eine WebSocket-Sitzung an, prüft Leaderrolle und registriert Spieler. |
| `handle_client_message(token, websocket, message)` | async Methode | Verarbeitet ACK, RESEND_REQUEST und Spieleraktionen. |
| `remove_connection(token)` | Methode | Entfernt eine getrennte WebSocket-Verbindung, behält aber den Spielerzustand. |
| `stop()` | async Methode | Beendet Tasks, WebSocket-Server und Cluster. |

### `src/quizbattle/client_network.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `NetworkClient` | Klasse | Netzwerkseite des Clients: Discovery, WebSocket, Reconnect und ACK/Resend. |
| `name` | Instanzvariable | Sichtbarer Spielername. |
| `discovery_port` | Instanzvariable | UDP-Port für Leader-Discovery. |
| `broadcast_ip` | Instanzvariable | Broadcast-Adresse des lokalen Netzes. |
| `signals` | Instanzvariable | Qt-Signale zur sicheren Kommunikation mit der GUI. |
| `token` | Instanzvariable | Spieler-Sitzungstoken für Reconnect. |
| `player_id` | Instanzvariable | Sichtbare Spieler-ID wie `P1`. |
| `websocket` | Instanzvariable | Aktuelle WebSocket-Verbindung zum Leader. |
| `loop` | Instanzvariable | asyncio-Event-Loop im Netzwerkthread. |
| `outbox` | Instanzvariable | Queue für Aktionen aus der GUI. |
| `stopped` | Instanzvariable | Schalter zum Beenden des Netzwerkloops. |
| `ordering` | Instanzvariable | `OrderedEventBuffer` für sequenzierte Events. |
| `pending_actions` | Instanzvariable | Noch nicht bestätigte Clientaktionen nach `request_id`. |
| `last_seq` | Property | Letzte vollständig verarbeitete Eventsequenz. |
| `start()` | Methode | Startet den Netzwerkthread. |
| `run()` | Methode | Erstellt den asyncio-Event-Loop im Netzwerkthread. |
| `send(message)` | Methode | Übergibt GUI-Aktionen threadsicher an den Netzwerkloop. |
| `discover_leader()` | async Methode | Sucht den Leader per UDP-Broadcast. |
| `connection_loop()` | async Methode | Verbindet sich dauerhaft mit dem jeweils aktuellen Leader. |
| `receive_loop(websocket)` | async Methode | Empfängt Serverevents, sortiert sie und sendet ACKs. |
| `send_loop(websocket)` | async Methode | Sendet neue und noch unbestätigte Aktionen an den Leader. |

### `src/quizbattle/client_ordering.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `OrderedEventBuffer` | Klasse | Hold-back-Queue für sequenzierte Serverevents. |
| `last_sequence` | Instanzvariable | Letzte lückenlos verarbeitete Sequenznummer. |
| `holdback` | Instanzvariable | Zwischenspeicher für zu früh empfangene Events. |
| `receive(event)` | Methode | Speichert ein Event, liefert lückenlose Events aus und meldet fehlende Sequenzen. |

### `src/quizbattle/client_ui.py`

| Name | Art | Bedeutung |
| --- | --- | --- |
| `Signals` | Klasse | Qt-Signalträger zwischen Netzwerkthread und GUI-Hauptthread. |
| `Signals.message` | Signal | Transportiert empfangene Servernachrichten zur GUI. |
| `Signals.status` | Signal | Transportiert Statusmeldungen zur GUI. |
| `QuizWindow` | Klasse | Hauptfenster des grafischen Clients. |
| `player_id` | Instanzvariable | Eigene sichtbare Spieler-ID, vom Server vergeben. |
| `team_round` | Instanzvariable | Gibt an, ob die aktuelle Runde für diesen Client eine Teamrunde ist. |
| `team_name` | Instanzvariable | Name des eigenen Teams in einer Teamrunde. |
| `deadline` | Instanzvariable | Serverzeitpunkt, bis wann geantwortet werden darf. |
| `category_buttons` | Instanzvariable | Liste der aktuell sichtbaren Kategoriebuttons. |
| `network` | Instanzvariable | Instanz von `NetworkClient`. |
| `build_ui(name)` | Methode | Erstellt alle sichtbaren Widgets. |
| `set_status(text)` | Methode | Schreibt eine Statusmeldung in die Oberfläche. |
| `set_inputs(enabled)` | Methode | Aktiviert oder deaktiviert Antwort- und Chatfelder. |
| `update_timer()` | Methode | Aktualisiert den Countdown anhand der Serverdeadline. |
| `send_answer()` | Methode | Sendet Einzel- oder Teamantwort an den Netzwerkclient. |
| `send_chat()` | Methode | Sendet Teamchat an den Netzwerkclient. |
| `send_category_choice(category)` | Methode | Sendet eine Kategorieauswahl. |
| `handle_message(message)` | Methode | Verteilt empfangene Servernachrichten auf passende UI-Aktionen. |
| `show_question(message)` | Methode | Zeigt Frage, Kategorie und Teamzuordnung. |
| `show_category_selection(message)` | Methode | Zeigt Kategoriebuttons und aktiviert sie nur für den berechtigten Spieler. |
| `show_category_selected(message)` | Methode | Zeigt an, welche Kategorie gewählt wurde. |
| `build_category_buttons(categories, enabled)` | Methode | Erstellt Kategoriebuttons dynamisch. |
| `set_category_buttons_enabled(enabled)` | Methode | Aktiviert/deaktiviert alle Kategoriebuttons. |
| `clear_category_buttons()` | Methode | Entfernt alte Kategoriebuttons aus der Oberfläche. |
| `show_result(message)` | Methode | Zeigt richtige Antwort, eigene Antwort und Punkte. |
| `show_game_over(message)` | Methode | Zeigt die Rangliste am Spielende. |
| `show_game_reset(message)` | Methode | Setzt die Anzeige für ein neues Spiel zurück. |

### Testdateien

| Datei | Name | Art | Bedeutung |
| --- | --- | --- | --- |
| `tests/test_cluster.py` | `ClusterTests` | Testklasse | Prüft Ring, LCR und Replikation ohne echte Netzwerkprozesse. |
| `tests/test_cluster.py` | `config()` | Hilfsfunktion | Erstellt eine Test-ServerConfig. |
| `tests/test_cluster.py` | `cluster()` | Hilfsfunktion | Erstellt einen isolierten `ClusterManager` für Tests. |
| `tests/test_game.py` | `GameTests` | Testklasse | Prüft Spiellogik, Kategorieauswahl, Request-IDs und Reset. |
| `tests/test_identity.py` | `IdentityTests` | Testklasse | Prüft UUID-Erzeugung und UUID-Validierung. |
| `tests/test_ordering.py` | `OrderedEventBufferTests` | Testklasse | Prüft Hold-back-Queue und Deduplizierung im Client. |
| `tests/test_protocol.py` | `ProtocolTests` | Testklasse | Prüft TCP-Framing und UTF-8-Erhaltung. |

### Sonstige Dateien

| Datei | Name | Art | Bedeutung |
| --- | --- | --- | --- |
| `change_font_size.py` | `PDF_PATH` | Konstante | Eingabe-PDF, dessen Formularfelder angepasst werden. |
| `change_font_size.py` | `FONT_SIZE` | Konstante | Ziel-Schriftgröße für Formularfelder. |
| `change_font_size.py` | `change_text_field_font_size(pdf_path, font_size)` | Funktion | Ändert die Darstellungsanweisung von PDF-Textfeldern und schreibt eine neue PDF. |
| `tinydb.json` | `kategorie` | Datenfeld | Kategorie einer Frage. |
| `tinydb.json` | `frage` | Datenfeld | Fragetext, der dem Client angezeigt wird. |
| `tinydb.json` | `antwort` | Datenfeld | Korrekte Antwort, die der Server zur Auswertung nutzt. |
