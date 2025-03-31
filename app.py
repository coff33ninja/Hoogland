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
import logging
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user

# Set up logging
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Flask app setup
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this to a secure random key in production

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)

# Dummy user for authentication (replace with secure authentication in production)
class User(UserMixin):
    pass

user = User()
user.id = 'admin'

@login_manager.user_loader
def load_user(user_id):
    if user_id == 'admin':
        return user
    return None

# Global list for web notifications
notifications = []

# Tkinter root setup (hidden)
root = tk.Tk()
root.withdraw()

# Load configuration
def load_config():
    config_path = 'config.json'
    default_config = {
        "sender_email": "your_email@example.com",
        "password": "your_password",
        "recipient_email": "recipient@example.com",
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "start_time": "18:00",
        "end_time": "06:00",
        "sound_after_minutes": 3,
        "report_if_longer_than_minutes": 5,
        "email_if_not_pressed_after_minutes": 10,
        "min_wait_between_alerts_seconds": 600,
        "max_wait_between_alerts_seconds": 7200,
        "expected_hash": "abc123...",
        "is_default": True
    }
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        logging.info("Default config generated. Please update config.json.")
        return default_config
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        if config.get("is_default", False):
            logging.warning("Config is default. Please update config.json.")
        return config
    except json.JSONDecodeError:
        logging.error("Invalid JSON in config file. Using default config.")
        return default_config

# Send email function
def send_email(config, subject, message):
    try:
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = config['sender_email']
        msg['To'] = config['recipient_email']
        with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
            server.starttls()
            server.login(config['sender_email'], config['password'])
            server.sendmail(config['sender_email'], config['recipient_email'], msg.as_string())
        logging.info(f"Email sent: {subject}")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")

# Desktop alert function
def create_alert_window(config):
    alert_window = Toplevel(root)
    alert_window.title("Security Alert")
    alert_window.geometry("300x100")
    start_time = time.time()
    pressed = tk.BooleanVar(value=False)

    def play_sound():
        if alert_window.winfo_exists() and not pressed.get():
            playsound('alert_sound.mp3')

    def send_email_not_pressed():
        if alert_window.winfo_exists() and not pressed.get():
            elapsed = (time.time() - start_time) / 60
            message = f"The alert was not acknowledged after {elapsed:.2f} minutes."
            send_email(config, "Alert Not Acknowledged", message)
            notifications.append(f"{time.strftime('%H:%M:%S')} - {message}")

    def on_button_press():
        pressed.set(True)
        elapsed = time.time() - start_time
        if elapsed > config['report_if_longer_than_minutes'] * 60:
            message = f"The alert was acknowledged after {elapsed / 60:.2f} minutes."
            send_email(config, "Alert Acknowledged Late", message)
            notifications.append(f"{time.strftime('%H:%M:%S')} - {message}")
        alert_window.destroy()

    def on_close():
        if not pressed.get():
            elapsed = (time.time() - start_time) / 60
            message = f"The alert window was closed without acknowledging after {elapsed:.2f} minutes."
            send_email(config, "Alert Window Closed Without Acknowledging", message)
            notifications.append(f"{time.strftime('%H:%M:%S')} - {message}")
        alert_window.destroy()

    root.after(int(config['sound_after_minutes'] * 60 * 1000), play_sound)
    root.after(int(config['email_if_not_pressed_after_minutes'] * 60 * 1000), send_email_not_pressed)
    button = Button(alert_window, text="I accept", command=on_button_press)
    button.pack(pady=20)
    alert_window.protocol("WM_DELETE_WINDOW", on_close)
    return alert_window

# Main logic
def main_logic():
    while True:
        config = load_config()
        now = datetime.datetime.now()
        start_time = datetime.datetime.strptime(config['start_time'], "%H:%M").time()
        end_time = datetime.datetime.strptime(config['end_time'], "%H:%M").time()

        # Adjust for overnight schedules
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
            time.sleep((start_dt - now).total_seconds())

        while datetime.datetime.now() < end_dt:
            wait_time = random.randint(config['min_wait_between_alerts_seconds'], config['max_wait_between_alerts_seconds'])
            next_alert = datetime.datetime.now() + datetime.timedelta(seconds=wait_time)
            if next_alert > end_dt:
                wait_time = (end_dt - datetime.datetime.now()).total_seconds()
                if wait_time <= 0:
                    break
            time.sleep(wait_time)
            alert_window = create_alert_window(config)
            root.wait_window(alert_window)
            logging.info(f"Alert triggered at {time.strftime('%H:%M:%S')}")

        time.sleep(60)  # Wait before checking the next cycle

# Flask routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'password':
            login_user(user)
            return redirect(url_for('admin'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/logs')
@login_required
def logs():
    with open('app.log', 'r') as f:
        logs = f.readlines()
    return render_template('logs.html', logs=logs)

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    config = load_config()
    if request.method == 'POST':
        config = {
            "sender_email": request.form['sender_email'],
            "password": request.form['password'],
            "recipient_email": request.form['recipient_email'],
            "smtp_server": request.form['smtp_server'],
            "smtp_port": int(request.form['smtp_port']),
            "start_time": request.form['start_time'],
            "end_time": request.form['end_time'],
            "sound_after_minutes": int(request.form['sound_after_minutes']),
            "report_if_longer_than_minutes": int(request.form['report_if_longer_than_minutes']),
            "email_if_not_pressed_after_minutes": int(request.form['email_if_not_pressed_after_minutes']),
            "min_wait_between_alerts_seconds": int(request.form['min_wait_between_alerts_seconds']),
            "max_wait_between_alerts_seconds": int(request.form['max_wait_between_alerts_seconds']),
            "expected_hash": request.form['expected_hash'],
            "is_default": False
        }
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)
        logging.info("Configuration updated via admin backend.")
    return render_template('admin.html', config=config)

@app.route('/notifications')
@login_required
def get_notifications():
    return render_template('notifications.html', notifications=notifications)

# Start main logic in a thread
main_thread = threading.Thread(target=main_logic)
main_thread.start()

# Run Flask app
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
    root.mainloop()  # Ensure Tkinter event loop runs
