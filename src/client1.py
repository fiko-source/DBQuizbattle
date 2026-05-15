import sys
import json
import asyncio
import os
import threading

import websockets
from dotenv import load_dotenv

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt, QTimer


load_dotenv()

SERVER_IP = os.getenv("SERVER_IP")
SERVER_PORT = int(os.getenv("SERVER_PORT"))
SERVER_URI = f"ws://{SERVER_IP}:{SERVER_PORT}"


class WebSocketSignals(QObject):
    welcome_received = pyqtSignal(dict)
    question_received = pyqtSignal(dict)
    info_received = pyqtSignal(str)
    result_received = pyqtSignal(dict)
    game_over_received = pyqtSignal(dict)
    error_received = pyqtSignal(str)


class QuizClientGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.websocket = None
        self.loop = None

        self.player_id = None
        self.score = 0
        self.timer = 0

        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_timer)

        self.signals = WebSocketSignals()
        self.signals.welcome_received.connect(self.show_welcome)
        self.signals.question_received.connect(self.show_question)
        self.signals.info_received.connect(self.show_info)
        self.signals.result_received.connect(self.show_result)
        self.signals.game_over_received.connect(self.show_game_over)
        self.signals.error_received.connect(self.show_error)

        self.setup_ui()
        self.start_websocket_thread()

    def setup_ui(self):
        self.setWindowTitle("QuizBattle Client")
        self.setFixedSize(600, 350)

        self.score_label = QLabel("Score: 0")
        self.timer_label = QLabel("Timer: --")

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.score_label)
        top_layout.addStretch()
        top_layout.addWidget(self.timer_label)

        self.question_label = QLabel("Warte auf Spielstart...")
        self.question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.question_label.setWordWrap(True)

        self.answer_input = QLineEdit()
        self.answer_input.setPlaceholderText("Antwort eingeben...")
        self.answer_input.setDisabled(True)
        self.answer_input.returnPressed.connect(self.send_answer)

        self.send_button = QPushButton("Senden")
        self.send_button.clicked.connect(self.send_answer)
        self.send_button.setDisabled(True)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addStretch()
        main_layout.addWidget(self.question_label)
        main_layout.addWidget(self.answer_input)
        main_layout.addWidget(self.send_button)
        main_layout.addWidget(self.status_label)
        main_layout.addStretch()

        self.setLayout(main_layout)

    def start_websocket_thread(self):
        thread = threading.Thread(target=self.run_websocket_loop, daemon=True)
        thread.start()

    def run_websocket_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.websocket_client())

    async def websocket_client(self):
        try:
            async with websockets.connect(SERVER_URI) as websocket:
                self.websocket = websocket
                self.signals.info_received.emit(f"Verbunden mit {SERVER_URI}")

                async for message in websocket:
                    data = json.loads(message)
                    message_type = data.get("type")

                    if message_type == "welcome":
                        self.signals.welcome_received.emit(data)

                    elif message_type == "info":
                        self.signals.info_received.emit(data["message"])

                    elif message_type == "question":
                        self.signals.question_received.emit(data)

                    elif message_type == "result":
                        self.signals.result_received.emit(data)

                    elif message_type == "game_over":
                        self.signals.game_over_received.emit(data)

                    elif message_type == "error":
                        self.signals.error_received.emit(data["message"])

        except Exception as e:
            self.signals.error_received.emit(str(e))

    def send_answer(self):
        answer = self.answer_input.text().strip()

        if not answer:
            return

        if self.websocket is None or self.loop is None:
            self.status_label.setText("Keine Verbindung zum Server.")
            return

        asyncio.run_coroutine_threadsafe(
            self.websocket.send(answer),
            self.loop
        )

        self.status_label.setText("Antwort gesendet.")
        self.answer_input.clear()
        self.answer_input.setDisabled(True)
        self.send_button.setDisabled(True)

    def update_timer(self):
        self.timer -= 1
        self.timer_label.setText(f"Timer: {self.timer}s")

        if self.timer <= 0:
            self.countdown_timer.stop()
            self.answer_input.setDisabled(True)
            self.send_button.setDisabled(True)

    def show_welcome(self, data):
        self.player_id = data["player_id"]
        self.status_label.setText(data["message"])

    def show_question(self, data):
        self.timer = data["time"]
        self.timer_label.setText(f"Timer: {self.timer}s")
        self.countdown_timer.start(1000)

        self.question_label.setText(data["data"]["frage"])
        self.status_label.setText(f"Runde {data['round']}")

        self.answer_input.clear()
        self.answer_input.setDisabled(False)
        self.send_button.setDisabled(False)
        self.answer_input.setFocus()

    def show_info(self, message):
        self.status_label.setText(message)

    def show_result(self, data):
        self.countdown_timer.stop()

        correct_answer = data["correct_answer"]
        scores = data.get("scores", {})

        self.question_label.setText(f"Richtige Antwort: {correct_answer}")
        self.status_label.setText("Warte auf nächste Frage...")
        self.timer_label.setText("Timer: --")

        if self.player_id in scores:
            self.score = scores[self.player_id]
            self.score_label.setText(f"Score: {self.score}")

        self.answer_input.setDisabled(True)
        self.send_button.setDisabled(True)

    def show_game_over(self, data):
        self.countdown_timer.stop()

        scores = data.get("scores", {})

        self.question_label.setText("Spiel beendet.")
        self.status_label.setText("Finale Scores wurden empfangen.")
        self.timer_label.setText("Timer: --")

        if self.player_id in scores:
            self.score = scores[self.player_id]
            self.score_label.setText(f"Score: {self.score}")

        self.answer_input.setDisabled(True)
        self.send_button.setDisabled(True)

    def show_error(self, message):
        self.status_label.setText(f"Fehler: {message}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QuizClientGUI()
    window.show()
    sys.exit(app.exec())