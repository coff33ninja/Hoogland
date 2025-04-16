# utils.py
import os
import sys
import hashlib
import smtplib
from email.mime.text import MIMEText
import logging
from config import load_config, cipher


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def send_email(config, subject, message):
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = config["sender_email"]
        msg["To"] = config["recipient_email"]
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls()
            server.login(
                config["sender_email"],
                cipher.decrypt(config["password"].encode()).decode(),
            )
            server.sendmail(
                config["sender_email"], config["recipient_email"], msg.as_string()
            )
        logging.info(f"Email sent: {subject}")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")


def send_credentials_email(to_email, username, password, role, smtp_config):
    msg = MIMEText(
        f"""
Your Hoogland account has been created. Please keep this information secure:

Username: {username}
Password: {password}
Role: {role}

Access the web GUI at http://localhost:5000 to manage settings.
    """
    )
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
            send_email(
                load_config(), "Hash Error", f"Failed to calculate hash: {str(e)}"
            )
            return None
    return None


def cleanup(qt_app=None, stop_event=None):
    logging.info("Initiating cleanup")
    if stop_event:
        stop_event.set()
    config = load_config()
    from pygame import mixer

    mixer.music.stop()
    send_email(
        config, "Program Stopped", "Program stopped due to user request or exception."
    )
    if qt_app:
        qt_app.quit()
    logging.info("Cleanup completed")
    sys.exit(0)
