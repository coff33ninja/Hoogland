# Copyright (c) 2025 DJ Kruger
# Licensed under the MIT License. See LICENSE file in the repository root.
import threading
import time
import json
import os
import uuid
import random
import datetime
import sys
import hashlib
import logging
import signal
import queue
import subprocess
import re  # Add this import at the top of app.py
from queue import Queue
from pygame import mixer
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QColor
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText
from waitress import serve
from cryptography.fernet import Fernet
import requests
import webbrowser
from argon2 import PasswordHasher

# Generate or load encryption key
key_path = os.path.join(os.getenv("APPDATA", os.path.expanduser("~/.hoogland")), "Hoogland", "key.bin")
app_data_dir = os.path.dirname(key_path)
os.makedirs(app_data_dir, exist_ok=True)
if not os.path.exists(key_path):
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
else:
    with open(key_path, "rb") as f:
        key = f.read()
cipher = Fernet(key)

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Set app data directory for logs and config
log_file = os.path.join(app_data_dir, "app.log")
config_path = os.path.join(app_data_dir, "config.json")

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.info(f"Logging initialized to {log_file}")

app = Flask(__name__, template_folder=resource_path("templates"))
app.secret_key = os.urandom(24).hex()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, username, role):
        self.id = username
        self.role = role

@login_manager.user_loader
def load_user(username):
    config = load_config()
    for user in config.get("users", []):
        if user["username"] == username:
            return User(username, user["role"])
    return None

notifications = []
popup_queue = Queue()
stop_event = threading.Event()
qt_app = None

mixer.init()

ph = PasswordHasher()

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
                sound_path = resource_path("alert_sound.mp3")  # Default sound
                if self.config.get("use_custom_sounds", False) and self.config.get("custom_sounds"):
                    available_sounds = [s["filename"] for s in self.config["custom_sounds"]
                                      if s["active"] and os.path.exists(os.path.join(app_data_dir, "sounds", s["filename"]))]
                    if available_sounds:
                        sound_file = random.choice(available_sounds)
                        sound_path = os.path.join(app_data_dir, "sounds", sound_file)
                logging.info(f"Loading sound from: {sound_path}")
                mixer.music.load(sound_path)
                mixer.music.play(-1)  # Loop indefinitely
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
        if self.sound_thread:
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

def load_config():
    config_lock = threading.Lock()
    with config_lock:
        # Default configuration template including password rules
        default_config = {
            "users": [],
            "sender_email": "",
            "password": "",  # Encrypted SMTP password
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "recipient_email": "",  # Added recipient email field
            "start_time": "18:00",
            "end_time": "23:59",
            "sound_after_minutes": 3,
            "report_if_longer_than_minutes": 5,
            "email_if_not_pressed_after_minutes": 10,
            "min_wait_between_alerts_seconds": 60,  # Added sensible defaults
            "max_wait_between_alerts_seconds": 300,  # Added sensible defaults
            "random_sound_enabled": False,  # Added default
            "random_sound_min_seconds": 300,  # Added default
            "random_sound_max_seconds": 1800,  # Added default
            "use_custom_sounds": False,
            "custom_sounds": [],
            "predefined_messages": ["Stay awake!", "Security check!", "Alert now!", "System Check Required"],  # Added more default messages
            "update_url": "https://raw.githubusercontent.com/coff33ninja/Hoogland/main/latest_version.json",
            "custom_sounds": [],
            "use_custom_sounds": False,
            "expected_hash": "",  # Default empty hash
            "is_default": True,  # Flag indicating if it's the default config
            # --- Password Complexity Rules ---
            "password_policy": {
                "min_length": 8,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_number": True,
                "require_symbol": True,
                "symbols": "!@#$%^&*()-_=+[]{}|;:'\",.<>?/`~"  # Define allowed symbols
            }
        }

        config = None
        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                logging.info("Configuration file loaded successfully.")

                # --- Validate and update existing config ---
                config_updated = False
                # Ensure nested password_policy dict exists
                if "password_policy" not in config:
                    config["password_policy"] = {}
                    config_updated = True

                # Check top-level keys
                for key, default_value in default_config.items():
                    if key not in config:
                        logging.warning(f"Missing key '{key}' in config. Adding default value.")
                        config[key] = default_value
                        config_updated = True
                    # Check password policy keys
                    elif key == "password_policy":
                        for p_key, p_default_value in default_config["password_policy"].items():
                            if p_key not in config["password_policy"]:
                                logging.warning(f"Missing password policy key '{p_key}'. Adding default.")
                                config["password_policy"][p_key] = p_default_value
                                config_updated = True

                if config_updated:
                    logging.info("Updating config file with missing default keys.")
                    save_config(config)  # Save the updated config

            else:
                logging.warning("Configuration file not found. Creating default configuration file.")
                config = default_config
                save_config(config)  # Save the default config immediately

        except json.JSONDecodeError:
            logging.error("Invalid JSON in configuration file. Creating default configuration file.")
            config = default_config
            save_config(config)  # Save the default config immediately
        except Exception as e:
            logging.error(f"Error loading or creating config: {str(e)}. Using in-memory default.")
            config = default_config  # Fallback to in-memory default if save fails

        # Mark as not default if it was loaded or created
        if config and config.get("is_default"):
            config["is_default"] = False

        return config

def save_config(config):
    try:
        # Validate the configuration before saving
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a dictionary.")

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        logging.info("Configuration file saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save configuration: {str(e)}")

def send_email(config, subject, message):
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = config["sender_email"]
        msg["To"] = config["recipient_email"]
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["sender_email"], cipher.decrypt(config["password"].encode()).decode())
            server.sendmail(config["sender_email"], config["recipient_email"], msg.as_string())
        logging.info(f"Email sent: {subject}")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")

def send_credentials_email(to_email, username, password, role, smtp_config):
    msg = MIMEText(f"""
Your Hoogland account has been created. Please keep this information secure:

Username: {username}
Password: {password}
Role: {role}

Access the web GUI at http://localhost:5000 to manage settings.
    """)
    msg["Subject"] = "Your Hoogland Credentials"
    msg["From"] = smtp_config["sender_email"]
    msg["To"] = to_email
    with smtplib.SMTP(smtp_config["smtp_server"], smtp_config["smtp_port"]) as server:
        server.starttls()
        server.login(smtp_config["sender_email"], smtp_config["password"])
        server.sendmail(smtp_config["sender_email"], to_email, msg.as_string())

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

def validate_password(password, policy):
    """Validates a password against the configured policy."""
    errors = []
    if len(password) < policy.get("min_length", 8):
        errors.append(f"Password must be at least {policy.get('min_length', 8)} characters long.")
    if policy.get("require_uppercase", True) and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if policy.get("require_lowercase", True) and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if policy.get("require_number", True) and not re.search(r"\d", password):
        errors.append("Password must contain at least one number.")
    if policy.get("require_symbol", True):
        allowed_symbols = policy.get("symbols", "!@#$%^&*()-_=+[]{}|;:'\",.<>?/`~")
        pattern = f"[{re.escape(allowed_symbols)}]"
        if not re.search(pattern, password):
            errors.append(f"Password must contain at least one symbol ({allowed_symbols}).")
    return errors

class UpdateCheckerThread(QThread):
    update_available = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.current_version = "1.0.0"
        self.app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(__file__)

    def run(self):
        logging.info("UpdateCheckerThread started")
        while not stop_event.is_set():
            try:
                response = requests.get(self.config["update_url"], timeout=5)
                response.raise_for_status()
                update_data = response.json()
                latest_version = update_data.get("version")
                if latest_version and latest_version > self.current_version:
                    logging.info(f"Update available: {latest_version}")
                    self.apply_update(update_data)
                    self.update_available.emit(f"Updated to {latest_version}")
                    self.current_version = latest_version
                else:
                    logging.info("No update available")
            except Exception as e:
                logging.error(f"Update check failed: {str(e)}")
            time.sleep(3600)

    def apply_update(self, update_data):
        changes = update_data.get("changes", {})
        expected_hashes = update_data.get("hashes", {})
        for file_name, url in changes.items():
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            content = response.content
            if hashlib.sha256(content).hexdigest() == expected_hashes.get(file_name):
                with open(os.path.join(self.app_dir, file_name), "wb") as f:
                    f.write(content)
                logging.info(f"Updated {file_name}")
            else:
                logging.error(f"Hash mismatch for {file_name}")
                send_email(self.config, "Update Error", f"Hash mismatch for {file_name}")

        if "requirements.txt" in changes:
            if getattr(sys, "frozen", False):
                logging.info("New dependencies detected in frozen app, full update required")
                self.update_available.emit(f"New dependencies detected. Please download the latest installer from {update_data.get('download_url', 'unknown URL')}")
            else:
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", "-r", os.path.join(self.app_dir, "requirements.txt")]
                    )
                    logging.info("Updated dependencies")
                except Exception as e:
                    logging.error(f"Failed to update dependencies: {str(e)}")
                    send_email(self.config, "Update Error", f"Failed to update dependencies: {str(e)}")

        if "app.py" in changes:
            logging.info("Restarting app to apply update")
            subprocess.Popen([sys.executable] + sys.argv)
            sys.exit(0)

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
                    start_dt = now.replace(hour=start_time.hour, minute=start_time.minute, second=0)
                    if now.time() < end_time:
                        start_dt -= datetime.timedelta(days=1)
                    end_dt = start_dt + datetime.timedelta(days=1)
                    end_dt = end_dt.replace(hour=end_time.hour, minute=end_time.minute, second=0)
                else:
                    start_dt = now.replace(hour=start_time.hour, minute=start_time.minute, second=0)
                    end_dt = now.replace(hour=end_time.hour, minute=end_time.minute, second=0)

                if now < start_dt:
                    logging.info(f"Outside schedule, sleeping until {start_dt}")
                    time.sleep((start_dt - now).total_seconds())
                    continue

                if now < end_dt:
                    total_seconds = (end_dt - now).total_seconds()
                    if total_seconds <= 0:
                        time.sleep(60)
                        continue
                    wait_time = random.uniform(0, total_seconds)
                    logging.info(f"Random wait time: {wait_time} seconds")
                    time.sleep(wait_time)
                    logging.info("Triggering scheduled popup")
                    self.trigger_popup.emit("Security Alert", True)
                    logging.info("trigger_popup signal emitted for scheduled popup")
                    time.sleep((end_dt - datetime.datetime.now()).total_seconds() + 60)
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
                    mixer.music.load(resource_path("alert_sound.mp3"))
                    mixer.music.play(-1)
                    time.sleep(5)
                    mixer.music.stop()
                    send_email(self.config, "Random Sound Triggered", f"Sound played at {time.strftime('%H:%M:%S')}")
                except Exception as e:
                    logging.error(f"Random sound failed: {str(e)}")
                    send_email(self.config, "Random Sound Error", f"Failed to play random sound: {str(e)}")
            else:
                time.sleep(60)

@app.route("/setup", methods=["GET", "POST"])
def setup():
    logging.info("Accessed /setup route")
    config = load_config()
    if config and config.get("users"):
        return redirect(url_for("login"))  # Redirect to login if users exist

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        email = request.form["email"]
        smtp_email = request.form["smtp_email"]
        smtp_password = request.form["smtp_password"]
        smtp_server = request.form["smtp_server"]
        smtp_port = int(request.form["smtp_port"])

        # Load password policy from config
        policy = config.get("password_policy", {})

        # Validate password
        password_errors = validate_password(password, policy)
        if password_errors:
            for error in password_errors:
                flash(error, 'error')
            return render_template("setup.html"), 400

        # Validate username
        if len(username) < 8:
            flash("Username must be at least 8 characters.", 'error')
            return render_template("setup.html"), 400

        # Hash the password and create the admin user
        hashed_password = ph.hash(password)
        new_config = {
            "users": [{
                "username": username,
                "password_hash": hashed_password,
                "role": "admin",
                "email": email
            }],
            "sender_email": smtp_email,
            "password": cipher.encrypt(smtp_password.encode()).decode(),
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "password_policy": policy,  # Include the password policy
            "is_default": False
        }

        save_config(new_config)

        # Send credentials email
        try:
            send_credentials_email(email, username, password, "Admin", {
                "sender_email": smtp_email,
                "password": smtp_password,
                "smtp_server": smtp_server,
                "smtp_port": smtp_port
            })
        except Exception as e:
            logging.error(f"Failed to send credentials email: {str(e)}")
            return f"Failed to send email: {str(e)}", 500

        flash('Admin account created successfully!', 'success')
        login_user(User(username, "admin"))
        return redirect(url_for("admin"))

    return render_template("setup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    config = load_config()
    if not config or not config.get("users"):
        # Redirect to setup wizard if no users exist
        return redirect(url_for("setup"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Check credentials
        for user in config["users"]:
            if user["username"] == username and ph.verify(user["password_hash"], password):
                login_user(User(username, user["role"]))
                return redirect(url_for("admin" if user["role"] == "admin" else "user_dashboard"))

        return "Invalid credentials", 401
    return render_template("login.html")

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if current_user.role != "admin":
        flash("Access denied: Admin privileges required.", "error")
        return redirect(url_for("user_dashboard"))

    config = load_config()

    # Ensure password_policy exists in the config
    if "password_policy" not in config:
        config["password_policy"] = {
            "min_length": 8,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_number": True,
            "require_symbol": True,
            "symbols": "!@#$%^&*()-_=+[]{}|;:'\",.<>?/`~"
        }

    if request.method == "POST":
        action = request.form["action"]
        if action == "add_user":
            username = request.form["username"]
            password = request.form["password"]
            email = request.form["email"]
            role = request.form["role"]

            # Load password policy
            policy = config.get("password_policy", {})

            # Validate password
            password_errors = validate_password(password, policy)
            if password_errors:
                for error in password_errors:
                    flash(error, 'error')
                return render_template("admin.html", config=config, users=config.get("users", [])), 400

            # Validate username
            if len(username) < 8:
                flash("Username must be at least 8 characters.", 'error')
                return render_template("admin.html", config=config, users=config.get("users", [])), 400

            # Check if username already exists
            if any(u["username"] == username for u in config.get("users", [])):
                flash("Username already exists.", 'error')
                return render_template("admin.html", config=config, users=config.get("users", [])), 400

            # Add the user
            hashed_password = ph.hash(password)
            config["users"].append({
                "username": username,
                "password_hash": hashed_password,
                "role": role,
                "email": email
            })
            save_config(config)
            flash(f"User '{username}' added successfully.", 'success')

            # Send credentials email
            try:
                send_credentials_email(email, username, password, role.capitalize(), {
                    "sender_email": config["sender_email"],
                    "password": cipher.decrypt(config["password"].encode()).decode(),
                    "smtp_server": config["smtp_server"],
                    "smtp_port": config["smtp_port"]
                })
            except Exception as e:
                logging.error(f"Failed to send credentials email: {str(e)}")
                flash(f"Failed to send email: {str(e)}", 'error')

            return redirect(url_for("admin"))

    return render_template("admin.html", config=config, users=config.get("users", []))

@app.route("/trigger_popup", methods=["POST"])
@login_required
def trigger_popup():
    if current_user.role != "admin":
        flash("Access denied: Admin privileges required.", "error")
        return redirect(url_for("user_dashboard"))

    message = request.form.get("message", "Manual Popup Triggered")
    play_sound = request.form.get("play_sound", "true").lower() == "true"

    # Add the popup to the queue
    popup_queue.put({"message": message, "play_sound": play_sound})
    flash("Popup triggered successfully.", "success")
    return redirect(url_for("admin"))

@app.route('/upload_sound', methods=['POST'])
@login_required
def upload_sound():
    # Ensure the user has admin rights
    if current_user.role != 'admin':
        flash("Access denied: Admin privileges required.", "error")
        return redirect(url_for('admin'))

    # Check if a file is included in the request
    if 'sound_file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('admin'))

    file = request.files['sound_file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('admin'))

    # Validate the file type (only allow MP3 files)
    if not file.filename.endswith('.mp3'):
        flash('Only MP3 files are allowed.', 'error')
        return redirect(url_for('admin'))

    # Save the file to the designated sounds directory
    sounds_dir = os.path.join(app_data_dir, "sounds")
    os.makedirs(sounds_dir, exist_ok=True)  # Ensure the directory exists
    save_path = os.path.join(sounds_dir, secure_filename(file.filename))

    try:
        file.save(save_path)

        # Update the configuration to include the new sound
        config = load_config()
        if 'custom_sounds' not in config:
            config['custom_sounds'] = []

        # Avoid duplicate entries
        if not any(s['filename'] == file.filename for s in config['custom_sounds']):
            config['custom_sounds'].append({'filename': file.filename, 'active': True})
            save_config(config)
            flash(f'Sound "{file.filename}" uploaded successfully.', 'success')
        else:
            flash(f'Sound "{file.filename}" already exists.', 'warning')
    except Exception as e:
        logging.error(f"Failed to upload sound: {str(e)}")
        flash('Failed to upload sound.', 'error')

    return redirect(url_for('admin'))

@app.route('/restore_config', methods=['POST'])
@login_required
def restore_config():
    # Ensure the user has admin rights
    if current_user.role != 'admin':
        flash("Access denied: Admin privileges required.", "error")
        return redirect(url_for('admin'))

    # Check if a file is included in the request
    if 'config_file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('admin'))

    file = request.files['config_file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('admin'))

    # Validate the file type (only allow JSON files)
    if not file.filename.endswith('.json'):
        flash('Only JSON files are allowed.', 'error')
        return redirect(url_for('admin'))

    # Save the uploaded configuration file
    try:
        config_data = json.load(file)
        save_config(config_data)
        flash('Configuration restored successfully.', 'success')
    except Exception as e:
        logging.error(f"Failed to restore configuration: {str(e)}")
        flash('Failed to restore configuration. Ensure the file is valid.', 'error')

    return redirect(url_for('admin'))

@app.route('/manage_users', methods=['GET', 'POST'])
@login_required
def manage_users():
    # Ensure the user has admin rights
    if current_user.role != 'admin':
        flash("Access denied: Admin privileges required.", "error")
        return redirect(url_for('admin'))

    config = load_config()

    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')

        if action == 'delete_user':
            # Delete the user from the config
            config['users'] = [user for user in config['users'] if user['username'] != username]
            save_config(config)
            flash(f"User '{username}' deleted successfully.", 'success')

        elif action == 'update_role':
            # Update the user's role
            new_role = request.form.get('role')
            for user in config['users']:
                if user['username'] == username:
                    user['role'] = new_role
                    break
            save_config(config)
            flash(f"User '{username}' role updated to '{new_role}'.", 'success')

    return render_template('users.html', users=config.get('users', []))

@app.route('/logs', methods=['GET'])
@login_required
def logs():
    # Ensure the user has admin rights
    if current_user.role != 'admin':
        flash("Access denied: Admin privileges required.", "error")
        return redirect(url_for('admin'))

    log_file_path = os.path.join(app_data_dir, "app.log")
    try:
        with open(log_file_path, "r") as f:
            log_content = f.readlines()
        return render_template("logs.html", logs=log_content)
    except Exception as e:
        logging.error(f"Failed to read log file: {str(e)}")
        flash("Failed to load logs.", "error")
        return redirect(url_for('admin'))

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

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def run_waitress():
    logging.info("Starting Waitress server on 0.0.0.0:5000")
    serve(app, host="0.0.0.0", port=5000, threads=2)

if __name__ == "__main__":
    # Check if configuration exists
    config = load_config()
    if config is None:
        # Launch the web UI for setup
        logging.info("Launching setup web UI...")
        webbrowser.open("http://localhost:5000/setup")

    # Start the Qt application
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    logging.info("Qt application initialized")

    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor("red"))
    tray_icon = QIcon(pixmap)
    tray = QSystemTrayIcon()
    tray.setIcon(tray_icon)
    tray.setToolTip("Security Alert App")
    tray.setVisible(True)
    logging.info("System tray icon initialized")

    tray_menu = QMenu()
    quit_action = tray_menu.addAction("Quit")
    quit_action.triggered.connect(cleanup)
    tray.setContextMenu(tray_menu)

    def show_popup(message, play_sound):
        config = load_config()
        try:
            dialog = AlertDialog(config, message, play_sound)
            logging.info(f"Showing popup: {message} with sound={play_sound}")
            dialog.exec()
            logging.info(f"Popup {message} completed")
        except Exception as e:
            logging.error(f"Error in show_popup: {str(e)}")

    def show_update_notification(update_message):
        tray.showMessage("Hoogland Update", update_message, QSystemTrayIcon.MessageIcon.Information, 10000)
        notifications.append(f"{time.strftime('%H:%M:%S')} - Update: {update_message}")

    logging.info("Starting MainLogicThread")
    main_thread = MainLogicThread()
    main_thread.trigger_popup.connect(show_popup)
    main_thread.start()

    logging.info("Starting ManualPopupThread")
    manual_thread = ManualPopupThread()
    manual_thread.trigger_popup.connect(show_popup)
    manual_thread.start()

    logging.info("Starting SoundThread")
    sound_thread = SoundThread(load_config())
    sound_thread.start()

    logging.info("Starting UpdateCheckerThread")
    update_thread = UpdateCheckerThread(load_config())
    update_thread.update_available.connect(show_update_notification)
    update_thread.start()

    waitress_thread = threading.Thread(target=run_waitress, daemon=True)
    waitress_thread.start()

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
