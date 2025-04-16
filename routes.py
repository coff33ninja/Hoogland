# routes.py
# Copyright (c) 2025 DJ Kruger
# Licensed under the MIT License.
import os
import json
import random
import queue
import logging
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_login import login_required, logout_user, current_user, login_user
from werkzeug.utils import secure_filename
from mutagen.mp3 import MP3
from config import load_config, save_config, cipher, app_data_dir, config_path
from auth import User, validate_password, ph
from utils import send_credentials_email, send_email, resource_path

# Configure logging
logging.basicConfig(level=logging.INFO)

def register_routes(app: Flask):
    """
    Register all Flask routes for the Hoogland application.

    Args:
        app (Flask): The Flask application instance.
    """
    # Initialize queue for manual popup triggers
    popup_queue = queue.Queue()

    @app.route("/", methods=["GET"])
    def index():
        """Redirect to login or admin/user dashboard based on authentication."""
        if current_user.is_authenticated:
            return redirect(url_for("admin" if current_user.role == "admin" else "user_dashboard"))
        return redirect(url_for("login"))

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        """Handle initial admin account setup and SMTP configuration."""
        config = load_config()
        if config.get("users"):
            flash("Setup already completed.", "error")
            return redirect(url_for("login"))

        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            email = request.form.get("email")
            smtp_email = request.form.get("smtp_email")
            smtp_password = request.form.get("smtp_password")
            smtp_server = request.form.get("smtp_server", "smtp.gmail.com")
            smtp_port = request.form.get("smtp_port", "587")

            # Validate inputs
            if not all([username, password, email, smtp_email, smtp_password]):
                flash("All fields are required.", "error")
                return render_template("setup.html"), 400

            policy = config.get("password_policy", {})
            password_errors = validate_password(password, policy)
            if password_errors:
                for error in password_errors:
                    flash(error, "error")
                return render_template("setup.html"), 400

            if len(username) < 8:
                flash("Username must be at least 8 characters.", "error")
                return render_template("setup.html"), 400

            try:
                smtp_port = int(smtp_port)
                if smtp_port <= 0:
                    raise ValueError
            except ValueError:
                flash("SMTP port must be a valid number.", "error")
                return render_template("setup.html"), 400

            # Create new configuration
            hashed_password = ph.hash(password)
            new_config = {
                **config,
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
                "recipient_email": email,
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
                flash("Admin account created successfully! Credentials sent to email.", "success")
            except Exception as e:
                logging.error(f"Failed to send credentials email: {str(e)}")
                flash(f"Failed to send email: {str(e)}. Account created, but save credentials manually.", "warning")

            login_user(User(username, "admin"))
            return redirect(url_for("admin"))

        return render_template("setup.html")

    @app.route("/login", methods=["GET", "POST"])
    # @limiter.limit("5 per minute")  # Optional: Enable with flask-limiter
    def login():
        """Handle user login."""
        config = load_config()
        if not config.get("users"):
            return redirect(url_for("setup"))

        if current_user.is_authenticated:
            return redirect(url_for("admin" if current_user.role == "admin" else "user_dashboard"))

        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            for user in config.get("users", []):
                try:
                    if user["username"] == username and ph.verify(user["password_hash"], password):
                        login_user(User(username, user["role"]))
                        flash("Logged in successfully.", "success")
                        return redirect(url_for("admin" if user["role"] == "admin" else "user_dashboard"))
                except Exception as e:
                    logging.error(f"Password verification failed: {str(e)}")

            flash("Invalid username or password.", "error")
            return render_template("login.html"), 401

        return render_template("login.html")

    @app.route("/admin", methods=["GET", "POST"])
    @login_required
    def admin():
        """Handle admin panel functionality."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        config = load_config()
        backups = [f for f in os.listdir(app_data_dir) if f.startswith("config_backup_") and f.endswith(".json")]

        if request.method == "POST":
            # Handle configuration updates
            if "sender_email" in request.form:
                try:
                    new_config = {
                        **config,
                        "sender_email": request.form["sender_email"],
                        "password": cipher.encrypt(request.form["password"].encode()).decode() if request.form["password"] else config["password"],
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
                        "random_sound_enabled": "random_sound_enabled" in request.form,
                        "random_sound_min_seconds": int(request.form["random_sound_min_seconds"]),
                        "random_sound_max_seconds": int(request.form["random_sound_max_seconds"]),
                        "use_custom_sounds": "use_custom_sounds" in request.form,
                        "expected_hash": request.form["expected_hash"],
                        "enable_math_popup": "enable_math_popup" in request.form
                    }
                    save_config(new_config)
                    flash("Configuration updated successfully.", "success")
                except ValueError as e:
                    flash(f"Invalid input: {str(e)}", "error")
                except Exception as e:
                    flash(f"Failed to update configuration: {str(e)}", "error")

            # Handle password policy updates
            elif request.form.get("action") == "update_config":
                try:
                    config["password_policy"] = {
                        "min_length": int(request.form["pwd_min_length"]),
                        "require_uppercase": "pwd_require_uppercase" in request.form,
                        "require_lowercase": "pwd_require_lowercase" in request.form,
                        "require_number": "pwd_require_number" in request.form,
                        "require_symbol": "pwd_require_symbol" in request.form,
                        "symbols": request.form["pwd_symbols"]
                    }
                    save_config(config)
                    flash("Password policy updated successfully.", "success")
                except ValueError:
                    flash("Invalid password policy input.", "error")

        return render_template("admin.html", config=config, backups=backups)

    @app.route("/user", methods=["GET"])
    @login_required
    def user_dashboard():
        """Handle user dashboard."""
        config = load_config()
        return render_template("user.html", config=config)

    @app.route("/manage_users", methods=["GET", "POST"])
    @login_required
    def manage_users():
        """Handle user management."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        config = load_config()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add_user":
                username = request.form.get("username")
                password = request.form.get("password")
                email = request.form.get("email")
                role = request.form.get("role")

                # Validate inputs
                policy = config.get("password_policy", {})
                password_errors = validate_password(password, policy)
                if password_errors:
                    for error in password_errors:
                        flash(error, "error")
                    return render_template("users.html", users=config.get("users", [])), 400

                if len(username) < 8:
                    flash("Username must be at least 8 characters.", "error")
                    return render_template("users.html", users=config.get("users", [])), 400

                if any(u["username"] == username for u in config.get("users", [])):
                    flash("Username already exists.", "error")
                    return render_template("users.html", users=config.get("users", [])), 400

                # Add user
                hashed_password = ph.hash(password)
                config["users"].append({
                    "username": username,
                    "password_hash": hashed_password,
                    "role": role,
                    "email": email
                })
                save_config(config)
                flash(f"User '{username}' added successfully.", "success")

                # Send credentials email
                try:
                    smtp_password = cipher.decrypt(config["password"].encode()).decode()
                    send_credentials_email(email, username, password, role.capitalize(), {
                        "sender_email": config["sender_email"],
                        "password": smtp_password,
                        "smtp_server": config["smtp_server"],
                        "smtp_port": config["smtp_port"]
                    })
                except Exception as e:
                    logging.error(f"Failed to send credentials email: {str(e)}")
                    flash(f"Failed to send email: {str(e)}", "warning")

            elif action == "delete_user":
                username = request.form.get("username")
                if username == current_user.id:
                    flash("Cannot delete the current user.", "error")
                else:
                    config["users"] = [u for u in config["users"] if u["username"] != username]
                    save_config(config)
                    flash(f"User '{username}' deleted successfully.", "success")

            return redirect(url_for("manage_users"))

        return render_template("users.html", users=config.get("users", []))

    @app.route("/trigger_popup", methods=["POST"])
    @login_required
    def trigger_popup():
        """Trigger a manual popup alert."""
        config = load_config()
        message = request.form.get("message", "Manual Popup Triggered")
        play_sound = request.form.get("play_sound", "on") == "on"

        if message == "Solve a math problem" and config.get("enable_math_popup"):
            num1 = random.randint(1, 100)
            num2 = random.randint(1, 100)
            operation = random.choice(["+", "-"])
            problem = f"{num1} {operation} {num2}"
            solution = eval(problem)
            popup_queue.put({"message": f"Solve this: {problem}", "play_sound": play_sound, "solution": solution})
            flash("Math popup triggered successfully.", "success")
        else:
            popup_queue.put({"message": message, "play_sound": play_sound})
            flash("Popup triggered successfully.", "success")

        return redirect(url_for("admin" if current_user.role == "admin" else "user_dashboard"))

    @app.route("/upload_sound", methods=["POST"])
    @login_required
    def upload_sound():
        """Handle custom sound uploads."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        config = load_config()
        file = request.files.get("sound_file")
        if not file or file.filename == "":
            flash("No file selected.", "error")
            return redirect(url_for("admin"))

        if not file.filename.lower().endswith(".mp3"):
            flash("Only MP3 files are allowed.", "error")
            return redirect(url_for("admin"))

        if len(config.get("custom_sounds", [])) >= 5:
            flash("Maximum of 5 custom sounds reached.", "error")
            return redirect(url_for("admin"))

        # Validate MP3 file
        temp_path = os.path.join(app_data_dir, "temp", secure_filename(file.filename))
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        file.save(temp_path)
        try:
            MP3(temp_path)  # Validates MP3 format
            sound_dir = os.path.join(app_data_dir, "sounds")
            os.makedirs(sound_dir, exist_ok=True)
            sound_path = os.path.join(sound_dir, secure_filename(file.filename))
            os.rename(temp_path, sound_path)

            config["custom_sounds"] = config.get("custom_sounds", []) + [{"filename": file.filename, "active": True}]
            save_config(config)
            flash("Sound uploaded successfully.", "success")
        except Exception as e:
            logging.error(f"Invalid MP3 file: {str(e)}")
            flash("Invalid MP3 file.", "error")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return redirect(url_for("admin"))

    @app.route("/toggle_sound/<filename>", methods=["POST"])
    @login_required
    def toggle_sound(filename):
        """Toggle active status of a custom sound."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        config = load_config()
        for sound in config.get("custom_sounds", []):
            if sound["filename"] == filename:
                sound["active"] = request.form.get("active") == "on"
                break
        save_config(config)
        flash(f"Sound '{filename}' toggled successfully.", "success")
        return redirect(url_for("admin"))

    @app.route("/delete_sound/<filename>", methods=["GET"])
    @login_required
    def delete_sound(filename):
        """Delete a custom sound."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        config = load_config()
        sound_path = os.path.join(app_data_dir, "sounds", filename)
        config["custom_sounds"] = [s for s in config.get("custom_sounds", []) if s["filename"] != filename]
        save_config(config)
        if os.path.exists(sound_path):
            os.remove(sound_path)
        flash(f"Sound '{filename}' deleted successfully.", "success")
        return redirect(url_for("admin"))

    @app.route("/restore_config", methods=["POST"])
    @login_required
    def restore_config():
        """Restore configuration from file or backup."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        config = load_config()
        if "config_file" in request.files and request.files["config_file"].filename:
            file = request.files["config_file"]
            if not file.filename.endswith(".json"):
                flash("Only JSON files are allowed.", "error")
                return redirect(url_for("admin"))
            try:
                new_config = json.load(file)
                save_config(new_config)
                flash("Configuration restored from file.", "success")
            except Exception as e:
                flash(f"Failed to restore config: {str(e)}", "error")
        elif request.form.get("backup_file"):
            backup_path = os.path.join(app_data_dir, request.form["backup_file"])
            if os.path.exists(backup_path):
                try:
                    with open(backup_path, "r") as f:
                        new_config = json.load(f)
                    save_config(new_config)
                    flash("Configuration restored from backup.", "success")
                except Exception as e:
                    flash(f"Failed to restore backup: {str(e)}", "error")
            else:
                flash("Backup file not found.", "error")
        else:
            flash("No file or backup selected.", "error")

        return redirect(url_for("admin"))

    @app.route("/logs", methods=["GET"])
    @login_required
    def logs():
        """Display application logs."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        log_file = os.path.join(app_data_dir, "app.log")
        logs = []
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    logs = f.readlines()
            except Exception as e:
                flash(f"Failed to read logs: {str(e)}", "error")
        return render_template("logs.html", logs=logs)

    @app.route("/get_notifications", methods=["GET"])
    @login_required
    def get_notifications():
        """Display notifications."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        # Placeholder: Replace with actual notification storage if implemented
        notifications = []  # Example: ["Alert missed at 10:00", "Update available"]
        return render_template("notifications.html", notifications=notifications)

    @app.route("/download_backup", methods=["GET"])
    @login_required
    def download_backup():
        """Download the latest config backup."""
        if current_user.role != "admin":
            flash("Access denied: Admin privileges required.", "error")
            return redirect(url_for("user_dashboard"))

        backups = sorted([f for f in os.listdir(app_data_dir) if f.startswith("config_backup_") and f.endswith(".json")])
        if backups:
            latest_backup = os.path.join(app_data_dir, backups[-1])
            return send_file(latest_backup, as_attachment=True, download_name=backups[-1])
        flash("No backups found.", "error")
        return redirect(url_for("admin"))

    @app.route("/logout", methods=["GET"])
    @login_required
    def logout():
        """Handle user logout."""
        logout_user()
        flash("Logged out successfully.", "success")
        return redirect(url_for("login"))
