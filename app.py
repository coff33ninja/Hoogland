import threading
import time
import json
import os
import random
import datetime
import tkinter as tk
from tkinter import Toplevel, Button
import smtplib
from email.mime.text import MIMEText
from playsound import playsound
import sys
import hashlib
import logging
from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from queue import Queue

# Set up logging
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Flask app setup
app = Flask(__name__)
app.secret_key = "your_secret_key"  # Change this to a secure random key in production

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


# Global list for web notifications and queue for manual popups
notifications = []
popup_queue = Queue()

# Tkinter root setup (hidden)
root = tk.Tk()
root.withdraw()


# Load configuration
def load_config():
    config_path = "config.json"
    default_config = {
        "sender_email": "your_email@example.com",
        "password": "your_password",
        "recipient_email": "recipient@example.com",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "start_time": "18:00",
        "end_time": "06:00",
        "sound_after_minutes": 3,
        "report_if_longer_than_minutes": 5,
        "email_if_not_pressed_after_minutes": 10,
        "min_wait_between_alerts_seconds": 600,
        "max_wait_between_alerts_seconds": 7200,
        "random_sound_enabled": False,
        "random_sound_min_seconds": 1800,
        "random_sound_max_seconds": 3600,
        "expected_hash": "abc123...",
        "is_default": True,
        "predefined_messages": ["Stay awake!", "Security check!", "Alert now!"],
    }
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=4)
        logging.info("Default config generated.")
        try:
            send_email(
                default_config,
                "Config Missing",
                "Default config generated. Update required.",
            )
        except:
            logging.error("Email failed on default config generation.")
        return default_config
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        required_keys = [
            "sender_email",
            "password",
            "recipient_email",
            "smtp_server",
            "smtp_port",
            "start_time",
            "end_time",
            "sound_after_minutes",
            "report_if_longer_than_minutes",
            "email_if_not_pressed_after_minutes",
            "min_wait_between_alerts_seconds",
            "max_wait_between_alerts_seconds",
            "random_sound_enabled",
            "random_sound_min_seconds",
            "random_sound_max_seconds",
            "expected_hash",
            "is_default",
            "predefined_messages",
        ]
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            logging.error(f"Missing keys in config: {missing_keys}")
            send_email(config, "Config Error", f"Missing keys: {missing_keys}")
            return default_config
        if config.get("is_default", False):
            logging.warning("Config is default.")
            send_email(
                config, "Default Config Detected", "Running with default config."
            )
        return config
    except json.JSONDecodeError:
        logging.error("Invalid JSON in config file.")
        send_email(default_config, "Config Error", "Invalid JSON detected.")
        return default_config


# Send email function
def send_email(config, subject, message):
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = config["sender_email"]
        msg["To"] = config["recipient_email"]
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["sender_email"], config["password"])
            server.sendmail(
                config["sender_email"], config["recipient_email"], msg.as_string()
            )
        logging.info(f"Email sent: {subject}")
        notifications.append(f"{time.strftime('%H:%M:%S')} - {subject}: {message}")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        notifications.append(f"{time.strftime('%H:%M:%S')} - Email Failed: {str(e)}")


# Code validation
def calculate_executable_hash():
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        try:
            with open(exe_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logging.error(f"Hash calculation failed: {str(e)}")
            send_email(
                load_config(), "Hash Error", f"Failed to calculate hash: {str(e)}"
            )
            return None
    return None


# Desktop alert function (modified for custom message and sound)
def create_alert_window(config, message="Security Alert", play_sound=True):
    alert_window = Toplevel(root)
    alert_window.title("Security Alert")
    alert_window.geometry("300x100")
    start_time = time.time()
    pressed = tk.BooleanVar(value=False)

    tk.Label(alert_window, text=message).pack(pady=10)

    def trigger_sound():
        if alert_window.winfo_exists() and not pressed.get() and play_sound:
            try:
                playsound("alert_sound.mp3")
            except Exception as e:
                logging.error(f"Sound playback failed: {str(e)}")
                send_email(config, "Sound Error", f"Failed to play sound: {str(e)}")

    def send_email_not_pressed():
        if alert_window.winfo_exists() and not pressed.get():
            elapsed = (time.time() - start_time) / 60
            message = f"The alert was not acknowledged after {elapsed:.2f} minutes."
            send_email(config, "Alert Not Acknowledged", message)

    def on_button_press():
        pressed.set(True)
        elapsed = time.time() - start_time
        if elapsed > config["report_if_longer_than_minutes"] * 60:
            message = f"The alert was acknowledged after {elapsed / 60:.2f} minutes."
            send_email(config, "Alert Acknowledged Late", message)
        else:
            message = f"Alert acknowledged in {elapsed / 60:.2f} minutes."
            send_email(config, "Alert Acknowledged", message)
        alert_window.destroy()

    def on_close():
        if not pressed.get():
            elapsed = (time.time() - start_time) / 60
            message = f"The alert window was closed without acknowledging after {elapsed:.2f} minutes."
            send_email(config, "Alert Window Closed Without Acknowledging", message)
        alert_window.destroy()

    if play_sound:
        root.after(int(config["sound_after_minutes"] * 60 * 1000), trigger_sound)
    root.after(
        int(config["email_if_not_pressed_after_minutes"] * 60 * 1000),
        send_email_not_pressed,
    )
    button = Button(alert_window, text="I accept", command=on_button_press)
    button.pack(pady=20)
    alert_window.protocol("WM_DELETE_WINDOW", on_close)
    return alert_window


# Random sound function
def random_sound_thread(config):
    while True:
        now = datetime.datetime.now()
        start_time = datetime.datetime.strptime(config["start_time"], "%H:%M").time()
        end_time = datetime.datetime.strptime(config["end_time"], "%H:%M").time()

        if start_time > end_time:
            in_schedule = now.time() >= start_time or now.time() < end_time
        else:
            in_schedule = start_time <= now.time() < end_time

        if in_schedule and config["random_sound_enabled"]:
            wait_time = random.randint(
                config["random_sound_min_seconds"], config["random_sound_max_seconds"]
            )
            time.sleep(wait_time)
            try:
                playsound("alert_sound.mp3")
                send_email(
                    config,
                    "Random Sound Triggered",
                    f"Sound played at {time.strftime('%H:%M:%S')}",
                )
            except Exception as e:
                logging.error(f"Random sound failed: {str(e)}")
                send_email(
                    config,
                    "Random Sound Error",
                    f"Failed to play random sound: {str(e)}",
                )
        else:
            time.sleep(60)


# Main logic with queue handling
def main_logic():
    config = load_config()
    current_hash = calculate_executable_hash()
    if current_hash and current_hash != config["expected_hash"]:
        send_email(
            config,
            "Integrity Check Failed",
            f"Hash mismatch: expected {config['expected_hash']}, got {current_hash}",
        )

    while True:
        config = load_config()
        now = datetime.datetime.now()
        start_time = datetime.datetime.strptime(config["start_time"], "%H:%M").time()
        end_time = datetime.datetime.strptime(config["end_time"], "%H:%M").time()

        if start_time > end_time:
            if now.time() < end_time:
                start_dt = now.replace(
                    hour=start_time.hour, minute=start_time.minute, second=0
                ) - datetime.timedelta(days=1)
            else:
                start_dt = now.replace(
                    hour=start_time.hour, minute=start_time.minute, second=0
                )
            end_dt = start_dt + datetime.timedelta(days=1)
            end_dt = end_dt.replace(hour=end_time.hour, minute=end_time.minute)
        else:
            start_dt = now.replace(
                hour=start_time.hour, minute=start_time.minute, second=0
            )
            end_dt = start_dt.replace(hour=end_time.hour, minute=end_time.minute)

        if now < start_dt:
            time.sleep((start_dt - now).total_seconds())

        while datetime.datetime.now() < end_dt:
            # Check for manual popup requests
            if not popup_queue.empty():
                popup_data = popup_queue.get()
                alert_window = create_alert_window(
                    config, popup_data["message"], popup_data["play_sound"]
                )
                root.wait_window(alert_window)
                logging.info(f"Manual popup triggered: {popup_data['message']}")
            else:
                wait_time = random.randint(
                    config["min_wait_between_alerts_seconds"],
                    config["max_wait_between_alerts_seconds"],
                )
                next_alert = datetime.datetime.now() + datetime.timedelta(
                    seconds=wait_time
                )
                if next_alert > end_dt:
                    wait_time = (end_dt - datetime.datetime.now()).total_seconds()
                    if wait_time <= 0:
                        break
                time.sleep(wait_time)
                alert_window = create_alert_window(config)
                root.wait_window(alert_window)
                logging.info(f"Alert triggered at {time.strftime('%H:%M:%S')}")

        time.sleep(60)


# Flask routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if (
            request.form["username"] == "admin"
            and request.form["password"] == "password"
        ):
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
                "report_if_longer_than_minutes": int(
                    request.form["report_if_longer_than_minutes"]
                ),
                "email_if_not_pressed_after_minutes": int(
                    request.form["email_if_not_pressed_after_minutes"]
                ),
                "min_wait_between_alerts_seconds": int(
                    request.form["min_wait_between_alerts_seconds"]
                ),
                "max_wait_between_alerts_seconds": int(
                    request.form["max_wait_between_alerts_seconds"]
                ),
                "random_sound_enabled": request.form["random_sound_enabled"] == "on",
                "random_sound_min_seconds": int(
                    request.form["random_sound_min_seconds"]
                ),
                "random_sound_max_seconds": int(
                    request.form["random_sound_max_seconds"]
                ),
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
            send_email(
                config, "Config Update Error", f"Failed to update config: {str(e)}"
            )
    return render_template("admin.html", config=config)


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
    send_email(
        config,
        "Manual Popup Triggered",
        f"Popup initiated with message: {message}, sound: {play_sound}",
    )
    return redirect(url_for("admin"))


@app.route("/notifications")
@login_required
def get_notifications():
    return render_template("notifications.html", notifications=notifications)


@app.route("/download_backup")
@login_required
def download_backup():
    backups = [
        f
        for f in os.listdir()
        if f.startswith("config_backup_") and f.endswith(".json")
    ]
    if backups:
        latest_backup = max(backups, key=os.path.getctime)
        return send_file(latest_backup, as_attachment=True)
    return "No backups available.", 404


# Start threads
main_thread = threading.Thread(target=main_logic)
main_thread.start()
sound_thread = threading.Thread(target=random_sound_thread, args=(load_config(),))
sound_thread.start()

# Run Flask app
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
    root.mainloop()
