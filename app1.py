import threading
import time
import json
import os
import random
import datetime
import sys
import hashlib
import logging
import signal
import queue
from queue import Queue
from pygame import mixer
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QColor
from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText

# Set up logging
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Flask app setup
app = Flask(__name__)
app.secret_key = "your_secret_key"  # Change this to a secure key in production

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    pass

user = User()
user.id = "admin"

@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return user
    return None

# Global variables
notifications = []
popup_queue = Queue()
stop_event = threading.Event()
qt_app = None

# Initialize pygame mixer
mixer.init()

# AlertDialog class (unchanged from your last version)
class AlertDialog(QDialog):
    def __init__(self, config, message="Security Alert", play_sound=True):
        super().__init__()
        logging.info("AlertDialog initialized")
        self.config = config
        self.message = message
        self.play_sound = play_sound
        self.start_time = time.time()
        self.pressed = False
        self.sound_thread = None
        self.stop_sound_event = threading.Event()
        self.init_ui()

    def init_ui(self):
        logging.info("Setting up AlertDialog UI")
        self.setWindowTitle("Security Alert")
        self.setGeometry(300, 300, 300, 100)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout()
        label = QLabel(self.message, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        button = QPushButton("I accept", self)
        button.clicked.connect(self.on_button_press)
        layout.addWidget(button)

        self.setLayout(layout)

        if self.play_sound:
            self.start_sound()
        QTimer.singleShot(int(self.config["email_if_not_pressed_after_minutes"] * 60 * 1000), self.send_email_not_pressed)

    def start_sound(self):
        def play_sound_loop():
            try:
                mixer.music.load("alert_sound.mp3")
                mixer.music.play(-1)
                logging.info("Sound started in loop")
                while not self.stop_sound_event.is_set():
                    time.sleep(0.1)
                mixer.music.stop()
                logging.info("Sound stopped")
            except Exception as e:
                logging.error(f"Sound playback failed: {str(e)}")
                send_email(self.config, "Sound Error", f"Failed to play sound: {str(e)}")

        if self.play_sound and not self.sound_thread:
            self.stop_sound_event.clear()
            self.sound_thread = threading.Thread(target=play_sound_loop, daemon=True)
            self.sound_thread.start()

    def stop_sound(self):
        if self.sound_thread and self.play_sound:
            self.stop_sound_event.set()
            self.sound_thread.join()
            self.sound_thread = None

    def send_email_not_pressed(self):
        if not self.pressed:
            elapsed = (time.time() - self.start_time) / 60
            message = f"The alert was not acknowledged after {elapsed:.2f} minutes."
            send_email(self.config, "Alert Not Acknowledged", message)

    def on_button_press(self):
        self.pressed = True
        self.stop_sound()
        elapsed = time.time() - self.start_time
        if elapsed > self.config["report_if_longer_than_minutes"] * 60:
            message = f"The alert was acknowledged after {elapsed / 60:.2f} minutes."
            send_email(self.config, "Alert Acknowledged Late", message)
        else:
            message = f"Alert acknowledged in {elapsed / 60:.2f} minutes."
            send_email(self.config, "Alert Acknowledged", message)
        self.accept()

    def closeEvent(self, event):
        if not self.pressed:
            elapsed = (time.time() - self.start_time) / 60
            message = f"The alert window was closed without acknowledging after {elapsed:.2f} minutes."
            send_email(self.config, "Alert Window Closed Without Acknowledging", message)
        self.stop_sound()
        event.accept()

# [load_config, send_email, calculate_executable_hash unchanged]
def load_config():
    config_path = "config.json"
    default_config = {
        "sender_email": "your_email@example.com",
        "password": "your_password",
        "recipient_email": "recipient@example.com",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "start_time": "00:00",
        "end_time": "23:59",
        "sound_after_minutes": 3,
        "report_if_longer_than_minutes": 5,
        "email_if_not_pressed_after_minutes": 10,
        "min_wait_between_alerts_seconds": 10,
        "max_wait_between_alerts_seconds": 20,
        "random_sound_enabled": False,
        "random_sound_min_seconds": 1800,
        "random_sound_max_seconds": 3600,
        "expected_hash": "abc123...",
        "is_default": True,
        "predefined_messages": ["Stay awake!", "Security check!", "Alert now!"],
    }

    def validate_time_string(time_str, key):
        import re
        if not isinstance(time_str, str):
            logging.error(f"Invalid type for {key}: expected str, got {type(time_str)}, using default")
            return default_config[key]
        cleaned = re.sub(r"[^0-9:]", "", time_str)
        if not re.match(r"^\d{2}:\d{2}$", cleaned):
            logging.error(f"Invalid {key} format: {time_str}, expected HH:MM, using default")
            return default_config[key]
        try:
            datetime.datetime.strptime(cleaned, "%H:%M")
            return cleaned
        except ValueError:
            logging.error(f"Invalid {key} value: {time_str}, out of range, using default")
            return default_config[key]

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            updated = False
            for key, default_value in default_config.items():
                if key not in config:
                    logging.warning(f"Missing key {key} in config, using default: {default_value}")
                    config[key] = default_value
                    updated = True
                elif key in ["start_time", "end_time"]:
                    corrected = validate_time_string(config[key], key)
                    if corrected != config[key]:
                        config[key] = corrected
                        updated = True
                elif isinstance(default_value, int) and not isinstance(config[key], int):
                    logging.error(f"Invalid type for {key}: expected int, got {type(config[key])}, reverting to default")
                    config[key] = default_value
                    updated = True
                elif isinstance(default_value, bool) and not isinstance(config[key], bool):
                    logging.error(f"Invalid type for {key}: expected bool, got {type(config[key])}, reverting to default")
                    config[key] = default_value
                    updated = True
            if updated:
                with open(config_path, "w") as f:
                    json.dump(config, f, indent=4)
                logging.info("Config file updated with corrected values")
            if config.get("is_default", False):
                logging.warning("Config is default.")
                send_email(config, "Default Config Detected", "Running with default config.")
            return config
        except json.JSONDecodeError:
            logging.error("Invalid JSON in config file.")
            send_email(default_config, "Config Error", "Invalid JSON detected in config.json.")

    backups = [f for f in os.listdir() if f.startswith("config_backup_") and f.endswith(".json")]
    if backups:
        latest_backup = max(backups, key=os.path.getctime)
        try:
            with open(latest_backup, "r") as f:
                config = json.load(f)
            logging.info(f"Restored config from backup: {latest_backup}")
            with open(config_path, "w") as f:
                json.dump(config, f, indent=4)
            send_email(config, "Config Restored", f"Restored config from {latest_backup}.")
            return config
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in backup: {latest_backup}")

    with open(config_path, "w") as f:
        json.dump(default_config, f, indent=4)
    logging.info("Default config generated.")
    try:
        send_email(default_config, "Config Missing", "Default config generated. Update required.")
    except:
        logging.error("Email failed on default config generation.")
    return default_config

def send_email(config, subject, message):
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = config["sender_email"]
        msg["To"] = config["recipient_email"]
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["sender_email"], config["password"])
            server.sendmail(config["sender_email"], config["recipient_email"], msg.as_string())
        logging.info(f"Email sent: {subject}")
        notifications.append(f"{time.strftime('%H:%M:%S')} - {subject}: {message}")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        notifications.append(f"{time.strftime('%H:%M:%S')} - Email Failed: {str(e)}")

def calculate_executable_hash():
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        try:
            with open(exe_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logging.error(f"Hash calculation failed: {str(e)}")
            send_email(load_config(), "Hash Error", f"Failed to calculate hash: {str(e)}")
            return None
    return None

# [ManualPopupThread, MainLogicThread, SoundThread unchanged]
class ManualPopupThread(QThread):
    trigger_popup = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        logging.info("ManualPopupThread initialized successfully")

    def run(self):
        logging.info("ManualPopupThread started")
        while not stop_event.is_set():
            try:
                popup_data = popup_queue.get(timeout=1.0)
                logging.info(f"Processing manual popup: {popup_data['message']}")
                self.trigger_popup.emit(popup_data["message"], popup_data["play_sound"])
                logging.info("trigger_popup signal emitted for manual popup")
                popup_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error in ManualPopupThread: {str(e)}")
                send_email(load_config(), "ManualPopupThread Error", f"Error processing manual popup: {str(e)}")
                time.sleep(5)

class MainLogicThread(QThread):
    trigger_popup = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        try:
            self.config = load_config()
            logging.info("MainLogicThread initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize MainLogicThread: {str(e)}")
            raise

    def run(self):
        logging.info("MainLogicThread started")
        try:
            current_hash = calculate_executable_hash()
            if current_hash and current_hash != self.config["expected_hash"]:
                send_email(self.config, "Integrity Check Failed", f"Hash mismatch: expected {self.config['expected_hash']}, got {current_hash}")
        except Exception as e:
            logging.error(f"Error during hash check: {str(e)}")

        while not stop_event.is_set():
            try:
                logging.info("MainLogicThread loop running")
                self.config = load_config()
                now = datetime.datetime.now()
                start_time = datetime.datetime.strptime(self.config["start_time"], "%H:%M").time()
                end_time = datetime.datetime.strptime(self.config["end_time"], "%H:%M").time()

                logging.info(f"Current time: {now.time()}, Start time: {start_time}, End time: {end_time}")

                if start_time > end_time:
                    if now.time() < end_time:
                        start_dt = now.replace(hour=start_time.hour, minute=start_time.minute, second=0) - datetime.timedelta(days=1)
                    else:
                        start_dt = now.replace(hour=start_time.hour, minute=start_time.minute, second=0)
                    end_dt = start_dt + datetime.timedelta(days=1)
                    end_dt = end_dt.replace(hour=end_time.hour, minute=end_time.minute)
                else:
                    start_dt = now.replace(hour=start_time.hour, minute=start_time.minute, second=0)
                    end_dt = start_dt.replace(hour=end_time.hour, minute=end_time.minute)

                if now < start_dt:
                    logging.info(f"Outside schedule, sleeping until {start_dt}")
                    time.sleep((start_dt - now).total_seconds())
                    continue

                if datetime.datetime.now() < end_dt:
                    wait_time = random.randint(self.config["min_wait_between_alerts_seconds"], self.config["max_wait_between_alerts_seconds"])
                    next_alert = datetime.datetime.now() + datetime.timedelta(seconds=wait_time)
                    if next_alert > end_dt:
                        wait_time = (end_dt - datetime.datetime.now()).total_seconds()
                        if wait_time <= 0:
                            time.sleep(60)
                            continue
                    time.sleep(wait_time)
                    logging.info("Triggering scheduled popup")
                    self.trigger_popup.emit("Security Alert", True)
                    logging.info("trigger_popup signal emitted for scheduled popup")
                else:
                    logging.info("Outside schedule window, waiting 60 seconds")
                    time.sleep(60)
            except Exception as e:
                logging.error(f"Error in MainLogicThread: {str(e)}")
                send_email(self.config, "Thread Error", f"MainLogicThread encountered an error: {str(e)}")
                time.sleep(60)

class SoundThread(QThread):
    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        logging.info("SoundThread started")
        while not stop_event.is_set():
            now = datetime.datetime.now()
            start_time = datetime.datetime.strptime(self.config["start_time"], "%H:%M").time()
            end_time = datetime.datetime.strptime(self.config["end_time"], "%H:%M").time()

            if start_time > end_time:
                in_schedule = now.time() >= start_time or now.time() < end_time
            else:
                in_schedule = start_time <= now.time() < end_time

            if in_schedule and self.config["random_sound_enabled"]:
                wait_time = random.randint(self.config["random_sound_min_seconds"], self.config["random_sound_max_seconds"])
                time.sleep(wait_time)
                try:
                    mixer.music.load("alert_sound.mp3")
                    mixer.music.play(-1)
                    time.sleep(5)
                    mixer.music.stop()
                    send_email(self.config, "Random Sound Triggered", f"Sound played at {time.strftime('%H:%M:%S')}")
                except Exception as e:
                    logging.error(f"Random sound failed: {str(e)}")
                    send_email(self.config, "Random Sound Error", f"Failed to play random sound: {str(e)}")
            else:
                time.sleep(60)

# Flask routes (unchanged)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "password":
            login_user(user)
            return redirect(url_for("admin"))
        return "Invalid credentials"
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/logs")
@login_required
def logs():
    try:
        with open("app.log", "r") as f:
            logs = f.readlines()
    except FileNotFoundError:
        logs = ["Log file not found."]
    return render_template("logs.html", logs=logs)

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    config = load_config()
    backups = [f for f in os.listdir() if f.startswith("config_backup_") and f.endswith(".json")]
    if request.method == "POST":
        try:
            config = {
                "sender_email": request.form["sender_email"],
                "password": request.form["password"],
                "recipient_email": request.form["recipient_email"],
                "smtp_server": request.form["smtp_server"],
                "smtp_port": int(request.form["smtp_port"]),
                "start_time": request.form["start_time"],
                "end_time": request.form["end_time"],
                "sound_after_minutes": int(request.form["sound_after_minutes"]),
                "report_if_longer_than_minutes": int(request.form["report_if_longer_than_minutes"]),
                "email_if_not_pressed_after_minutes": int(request.form["email_if_not_pressed_after_minutes"]),
                "min_wait_between_alerts_seconds": int(request.form["min_wait_between_alerts_seconds"]),
                "max_wait_between_alerts_seconds": int(request.form["max_wait_between_alerts_seconds"]),
                "random_sound_enabled": request.form["random_sound_enabled"] == "on",
                "random_sound_min_seconds": int(request.form["random_sound_min_seconds"]),
                "random_sound_max_seconds": int(request.form["random_sound_max_seconds"]),
                "expected_hash": request.form["expected_hash"],
                "is_default": False,
                "predefined_messages": config["predefined_messages"],
            }
            with open("config.json", "w") as f:
                json.dump(config, f, indent=4)
            backup_path = f"config_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_path, "w") as f:
                json.dump(config, f, indent=4)
            logging.info("Configuration updated and backed up.")
            send_email(config, "Config Updated", "Configuration updated via web UI.")
        except Exception as e:
            logging.error(f"Config update failed: {str(e)}")
            send_email(config, "Config Update Error", f"Failed to update config: {str(e)}")
    return render_template("admin.html", config=config, backups=backups)

@app.route("/trigger_popup", methods=["POST"])
@login_required
def trigger_popup():
    config = load_config()
    message_type = request.form["message_type"]
    if message_type == "custom":
        message = request.form["custom_message"]
    else:
        message = message_type
    play_sound = request.form.get("play_sound") == "on"
    popup_queue.put({"message": message, "play_sound": play_sound})
    logging.info(f"Manual popup requested: {message}, sound: {play_sound}")
    send_email(config, "Manual Popup Triggered", f"Popup initiated with message: {message}, sound: {play_sound}")
    return redirect(url_for("admin"))

@app.route("/notifications")
@login_required
def get_notifications():
    return render_template("notifications.html", notifications=notifications)

@app.route("/download_backup")
@login_required
def download_backup():
    backups = [f for f in os.listdir() if f.startswith("config_backup_") and f.endswith(".json")]
    if backups:
        latest_backup = max(backups, key=os.path.getctime)
        return send_file(latest_backup, as_attachment=True)
    return "No backups available.", 404

@app.route("/restore_config", methods=["POST"])
@login_required
def restore_config():
    config = load_config()
    if "config_file" in request.files and request.files["config_file"].filename != "":
        file = request.files["config_file"]
        filename = secure_filename(file.filename)
        file.save(filename)
        try:
            with open(filename, "r") as f:
                new_config = json.load(f)
            with open("config.json", "w") as f:
                json.dump(new_config, f, indent=4)
            os.remove(filename)
            logging.info(f"Config restored from uploaded file: {filename}")
            send_email(config, "Config Restored", f"Config restored from uploaded file: {filename}")
        except Exception as e:
            logging.error(f"Failed to restore config from upload: {str(e)}")
            send_email(config, "Config Restore Error", f"Failed to restore config from {filename}: {str(e)}")
    elif "backup_file" in request.form and request.form["backup_file"]:
        backup_file = request.form["backup_file"]
        if os.path.exists(backup_file):
            try:
                with open(backup_file, "r") as f:
                    new_config = json.load(f)
                with open("config.json", "w") as f:
                    json.dump(new_config, f, indent=4)
                logging.info(f"Config restored from backup: {backup_file}")
                send_email(config, "Config Restored", f"Config restored from backup: {backup_file}")
            except Exception as e:
                logging.error(f"Failed to restore config from backup: {str(e)}")
                send_email(config, "Config Restore Error", f"Failed to restore config from {backup_file}: {str(e)}")
    return redirect(url_for("admin"))

# Cleanup function
def cleanup(signum=None, frame=None):
    logging.info("Initiating cleanup")
    stop_event.set()
    config = load_config()
    mixer.music.stop()
    send_email(config, "Program Stopped", "Program stopped due to user request or exception.")
    if qt_app:
        qt_app.quit()
    logging.info("Cleanup completed")
    sys.exit(0)

# Signal handlers
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# Flask runner with remote access
def run_flask():
    logging.info("Starting Flask app with remote access on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)

# Main execution
if __name__ == "__main__":
    # Initialize Qt app
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    logging.info("Qt application initialized")

    # Create a self-generated icon (red square)
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor("red"))
    tray_icon = QIcon(pixmap)

    # Set up system tray
    tray = QSystemTrayIcon()
    tray.setIcon(tray_icon)
    tray.setToolTip("Security Alert App")
    tray.setVisible(True)
    logging.info("System tray icon initialized")

    # Add a context menu with a Quit option
    tray_menu = QMenu()
    quit_action = tray_menu.addAction("Quit")
    quit_action.triggered.connect(cleanup)
    tray.setContextMenu(tray_menu)

    # Show popup function
    def show_popup(message, play_sound):
        config = load_config()
        try:
            dialog = AlertDialog(config, message, play_sound)
            logging.info(f"Showing popup: {message} with sound={play_sound}")
            dialog.exec()
            logging.info(f"Popup {message} completed")
        except Exception as e:
            logging.error(f"Error in show_popup: {str(e)}")

    # Start threads
    logging.info("Starting MainLogicThread")
    main_thread = MainLogicThread()
    main_thread.trigger_popup.connect(show_popup)
    main_thread.start()

    logging.info("Starting ManualPopupThread")
    manual_thread = ManualPopupThread()
    manual_thread.trigger_popup.connect(show_popup)
    manual_thread.start()

    sound_thread = SoundThread(load_config())
    sound_thread.start()

    # Run Flask in a separate thread with remote access
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run Qt event loop
    logging.info("Starting Qt event loop")
    try:
        qt_app.exec()
        logging.info("Qt event loop exited normally")
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt")
        cleanup()
    except Exception as e:
        logging.error(f"Qt app crashed: {str(e)}")
        cleanup()
