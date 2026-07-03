"""Grafische PyQt-Oberflaeche des QuizBattle-Clients."""

import time

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .client_network import NetworkClient


class Signals(QObject):
    """Transportiere Daten sicher vom Netzwerkthread in den PyQt-Hauptthread."""

    message = pyqtSignal(dict)
    status = pyqtSignal(str)


class QuizWindow(QWidget):
    """Zeige Fragen, Eingaben, Teamchat, Ergebnisse und Verbindungsstatus."""

    def __init__(self, config):
        """Erzeuge Fensterzustand, Signale und den Netzwerkclient."""
        super().__init__()
        self.player_id = None
        self.team_round = False
        self.team_name = None
        self.deadline = 0
        self.category_buttons = []

        # Qt-Signale verhindern, dass der Netzwerkthread GUI-Elemente direkt
        # veraendert. Direkte Zugriffe aus fremden Threads waeren unsicher.
        self.signals = Signals()
        self.signals.message.connect(self.handle_message)
        self.signals.status.connect(self.set_status)
        self.network = NetworkClient(
            config.name,
            config.discovery_port,
            config.broadcast_ip,
            self.signals,
        )
        self.build_ui(config.name)
        self.network.start()

    def build_ui(self, name):
        """Erzeuge und verbinde alle sichtbaren Bedienelemente."""
        self.setWindowTitle(f"QuizBattle - {name}")
        self.resize(700, 520)
        self.score_label = QLabel("Punkte: 0")
        self.timer_label = QLabel("Zeit: --")
        top = QHBoxLayout()
        top.addWidget(self.score_label)
        top.addStretch()
        top.addWidget(self.timer_label)

        self.question_label = QLabel("Warte auf Spielstart...")
        self.question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.question_label.setWordWrap(True)
        self.answer_input = QLineEdit()
        self.answer_input.setPlaceholderText("Antwort eingeben")
        self.answer_input.returnPressed.connect(self.send_answer)
        self.answer_button = QPushButton("Antwort senden")
        self.answer_button.clicked.connect(self.send_answer)
        self.category_label = QLabel("")
        self.category_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.category_layout = QHBoxLayout()

        self.team_label = QLabel("Einzelrunde")
        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Teamnachricht")
        self.chat_input.returnPressed.connect(self.send_chat)
        self.chat_button = QPushButton("Teamnachricht senden")
        self.chat_button.clicked.connect(self.send_chat)

        self.status_label = QLabel("")
        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.question_label)
        layout.addWidget(self.category_label)
        layout.addLayout(self.category_layout)
        layout.addWidget(self.answer_input)
        layout.addWidget(self.answer_button)
        layout.addWidget(self.team_label)
        layout.addWidget(self.chat_view)
        layout.addWidget(self.chat_input)
        layout.addWidget(self.chat_button)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(250)
        self.set_inputs(False)
        self.clear_category_buttons()

    def set_status(self, text):
        """Zeige eine kurze Statusmeldung am unteren Fensterrand."""
        self.status_label.setText(text)

    def set_inputs(self, enabled):
        """Aktiviere Eingaben nur waehrend der erlaubten Antwortphase."""
        self.answer_input.setEnabled(enabled)
        self.answer_button.setEnabled(enabled)
        self.chat_input.setEnabled(enabled and self.team_round)
        self.chat_button.setEnabled(enabled and self.team_round)

    def update_timer(self):
        """Berechne aus dem Server-Zeitstempel die verbleibenden Sekunden."""
        if not self.deadline:
            self.timer_label.setText("Zeit: --")
            return
        remaining = max(0, int(self.deadline - time.time() + 0.99))
        self.timer_label.setText(f"Zeit: {remaining}s")
        if remaining == 0:
            self.set_inputs(False)

    def send_answer(self):
        """Sende die eingegebene Einzel- oder Teamantwort an den Leader."""
        answer = self.answer_input.text().strip()
        if not answer:
            return
        message_type = "TEAM_ANSWER" if self.team_round else "ANSWER"
        self.network.send({"type": message_type, "answer": answer})
        self.answer_input.clear()
        self.answer_input.setEnabled(False)
        self.answer_button.setEnabled(False)

    def send_chat(self):
        """Sende eine Chatnachricht, wenn der Client in einer Teamrunde ist."""
        text = self.chat_input.text().strip()
        if text:
            self.network.send({"type": "TEAM_CHAT", "message": text})
            self.chat_input.clear()

    def send_category_choice(self, category):
        """Sende die ausgewaehlte Kategorie an den Leader."""
        self.network.send({"type": "CATEGORY_CHOICE", "category": category})
        self.set_category_buttons_enabled(False)
        self.set_status(f"Kategorie gewählt: {category}")

    def handle_message(self, message):
        """Ordne jede empfangene Nachrichtenart der passenden Anzeigeaktion zu."""
        message_type = message.get("type")
        if message_type == "WELCOME":
            self.player_id = message["player_id"]
            self.score_label.setText(f"Punkte: {message.get('score', 0)}")
        elif message_type in {"ACTION_STATUS", "PLAYER_COUNT"}:
            text = message.get("message")
            if not text:
                text = (
                    f"Spieler verbunden: {message['count']}/"
                    f"{message['minimum']}"
                )
            self.set_status(text)
        elif message_type == "QUESTION":
            self.show_question(message)
        elif message_type == "CATEGORY_SELECTION":
            self.show_category_selection(message)
        elif message_type == "CATEGORY_SELECTED":
            self.show_category_selected(message)
        elif message_type == "ANSWER_PHASE_START":
            self.deadline = message["deadline"]
            self.set_inputs(True)
            self.answer_input.setFocus()
        elif message_type in {"NEXT_ROUND", "ROUND_START"}:
            self.set_status(f"Runde {message['round']} startet.")
        elif message_type == "TEAM_MESSAGE":
            if message.get("team") == self.team_name:
                self.chat_view.append(
                    f"{message['player']}: {message['message']}"
                )
        elif message_type == "TEAM_ANSWERED":
            if message.get("team") == self.team_name:
                self.set_status(
                    f"{message['player']} hat die Teamantwort gesetzt."
                )
        elif message_type == "RESULT":
            self.show_result(message)
        elif message_type == "GAME_RESET":
            self.show_game_reset(message)
        elif message_type == "GAME_OVER":
            self.show_game_over(message)

    def show_question(self, message):
        """Zeige eine neue Frage und ermittle eine moegliche Teamzuordnung."""
        self.clear_category_buttons()
        self.team_round = False
        self.deadline = message["deadline"]
        self.question_label.setText(
            f"Runde {message['round']} - {message.get('category', '')}\n\n"
            f"{message['question']}"
        )
        self.chat_view.clear()
        self.team_name = None
        if message["team_round"]:
            # Der Server sendet alle Teams. Die GUI sucht darin anhand der
            # eigenen Spieler-ID das Team dieses Clients.
            for team, members in message["teams"].items():
                if any(
                    member["player_id"] == self.player_id for member in members
                ):
                    self.team_round = True
                    self.team_name = team
                    names = [member["name"] for member in members]
                    self.team_label.setText(f"{team}: {', '.join(names)}")
                    break
        if not self.team_round:
            self.team_label.setText("Einzelrunde")
        self.set_inputs(False)

    def show_category_selection(self, message):
        """Zeige Kategorieauswahl und aktiviere sie nur fuer den gewaehlten Spieler."""
        self.deadline = 0
        self.set_inputs(False)
        self.answer_input.clear()
        chooser_id = message["chooser_id"]
        chooser_name = message["chooser_name"]
        block_size = message.get("block_size", 5)
        self.question_label.setText(
            f"Nächste Kategorie wählen\n\n"
            f"{chooser_name} ist dran. Danach kommen {block_size} Fragen."
        )
        self.category_label.setText("Kategorieauswahl")
        can_choose = chooser_id == self.player_id
        self.build_category_buttons(message["categories"], can_choose)
        if can_choose:
            self.set_status("Du bist dran: Wähle eine Kategorie.")
        else:
            self.set_status(f"Warte auf Kategorieauswahl von {chooser_name}.")

    def show_category_selected(self, message):
        """Zeige die vom Spieler gewaehlte Kategorie."""
        self.clear_category_buttons()
        self.set_status(
            f"{message['chooser']} hat {message['category']} gewählt."
        )

    def build_category_buttons(self, categories, enabled):
        """Erzeuge die Buttons fuer die aktuelle Kategorieauswahl neu."""
        self.clear_category_buttons()
        for category in categories:
            button = QPushButton(category)
            button.clicked.connect(
                lambda checked=False, selected=category: self.send_category_choice(
                    selected
                )
            )
            button.setEnabled(enabled)
            self.category_layout.addWidget(button)
            self.category_buttons.append(button)

    def set_category_buttons_enabled(self, enabled):
        """Aktiviere oder deaktiviere alle sichtbaren Kategoriebuttons."""
        for button in self.category_buttons:
            button.setEnabled(enabled)

    def clear_category_buttons(self):
        """Entferne alle Kategoriebuttons aus der Oberflaeche."""
        self.category_label.setText("")
        while self.category_buttons:
            button = self.category_buttons.pop()
            self.category_layout.removeWidget(button)
            button.deleteLater()

    def show_result(self, message):
        """Zeige Auswertung, richtige Antwort und aktuellen Punktestand."""
        self.deadline = 0
        self.set_inputs(False)
        result = message["results"].get(self.player_id, {})
        score = message["scores"].get(self.player_id, 0)
        self.score_label.setText(f"Punkte: {score}")
        answer = result.get("answer") or "Keine Antwort"
        verdict = "Richtig" if result.get("correct") else "Falsch"
        self.question_label.setText(
            f"{verdict}\nDeine Antwort: {answer}\n"
            f"Richtige Antwort: {message['correct_answer']}"
        )

    def show_game_over(self, message):
        """Sortiere die Endpunktestaende und zeige die Rangliste."""
        ranking = sorted(
            message["scores"].items(),
            key=lambda item: item[1],
            reverse=True,
        )
        text = "\n".join(
            f"{index}. {name}: {score}"
            for index, (name, score) in enumerate(ranking, 1)
        )
        self.question_label.setText(f"Spiel beendet\n\n{text}")
        self.set_inputs(False)

    def show_game_reset(self, message):
        """Bereite die Anzeige nach einem abgeschlossenen Spiel neu vor."""
        self.deadline = 0
        self.team_round = False
        self.team_name = None
        self.clear_category_buttons()
        self.score_label.setText("Punkte: 0")
        self.team_label.setText("Einzelrunde")
        self.chat_view.clear()
        self.question_label.setText("Warte auf Spielstart...")
        self.set_status(message.get("message", "Neues Spiel startet."))
        self.set_inputs(False)
