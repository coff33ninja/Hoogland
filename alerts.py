# alerts.py
import threading
import time
import random
import logging
from pygame import mixer
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QLineEdit,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from config import load_config
from utils import resource_path, send_email


class AlertDialog(QDialog):
    def __init__(
        self, config, message="Security Alert", play_sound=True, solution=None
    ):
        super().__init__()
        self.config = config
        self.message = message
        self.play_sound = play_sound
        self.solution = solution
        self.start_time = time.time()
        self.pressed = False
        self.sound_thread = None
        self.stop_sound_event = threading.Event()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Security Alert")
        self.setGeometry(300, 300, 300, 200)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout()
        label = QLabel(self.message, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        if self.solution is not None:
            self.answer_input = QLineEdit(self)
            self.answer_input.setPlaceholderText("Enter your answer")
            layout.addWidget(self.answer_input)

        button = QPushButton("Submit", self)
        button.clicked.connect(self.on_button_press)
        layout.addWidget(button)

        self.setLayout(layout)

        if self.play_sound:
            self.start_sound()

    def on_button_press(self):
        if self.solution is not None:
            try:
                user_answer = int(self.answer_input.text())
                if user_answer == self.solution:
                    QMessageBox.information(
                        self, "Correct!", "Great job! You solved it correctly."
                    )
                    self.accept()
                else:
                    QMessageBox.warning(
                        self, "Incorrect", "That's not correct. Try another one."
                    )
                    self.generate_new_problem()
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Input", "Please enter a valid number."
                )
        else:
            self.pressed = True
            self.accept()

    def generate_new_problem(self):
        num1 = random.randint(1, 100)
        num2 = random.randint(1, 100)
        operation = random.choice(["+", "-"])
        self.solution = eval(f"{num1} {operation} {num2}")
        self.message = f"Solve this: {num1} {operation} {num2}"
        self.init_ui()

    def start_sound(self):
        def play_sound_loop():
            try:
                sound_path = resource_path("alert_sound.mp3")
                if self.config.get("use_custom_sounds", False) and self.config.get(
                    "custom_sounds"
                ):
                    available_sounds = [
                        s["filename"]
                        for s in self.config["custom_sounds"]
                        if s["active"]
                        and os.path.exists(
                            os.path.join(
                                os.path.dirname(config_path), "sounds", s["filename"]
                            )
                        )
                    ]
                    if available_sounds:
                        sound_file = random.choice(available_sounds)
                        sound_path = os.path.join(
                            os.path.dirname(config_path), "sounds", sound_file
                        )
                logging.info(f"Loading sound from: {sound_path}")
                mixer.music.load(sound_path)
                mixer.music.play(-1)
                while not self.stop_sound_event.is_set():
                    time.sleep(0.1)
                mixer.music.stop()
            except Exception as e:
                logging.error(f"Sound playback failed: {str(e)}")
                send_email(
                    self.config, "Sound Error", f"Failed to play sound: {str(e)}"
                )

        if self.play_sound and not self.sound_thread:
            self.stop_sound_event.clear()
            self.sound_thread = threading.Thread(target=play_sound_loop, daemon=True)
            self.sound_thread.start()

    def stop_sound(self):
        if self.sound_thread:
            self.stop_sound_event.set()
            self.sound_thread.join()
            self.sound_thread = None

    def send_email_not_pressed(self):
        if not self.pressed:
            elapsed = (time.time() - self.start_time) / 60
            message = f"The alert was not acknowledged after {elapsed:.2f} minutes."
            send_email(self.config, "Alert Not Acknowledged", message)

    def closeEvent(self, event):
        if not self.pressed:
            elapsed = (time.time() - self.start_time) / 60
            message = f"The alert window was closed without acknowledging after {elapsed:.2f} minutes."
            send_email(
                self.config, "Alert Window Closed Without Acknowledging", message
            )
        self.stop_sound()
        event.accept()


def show_popup(config, message, play_sound):
    dialog = AlertDialog(config, message, play_sound)
    logging.info(f"Showing popup: {message} with sound={play_sound}")
    dialog.exec()
    logging.info(f"Popup {message} completed")
