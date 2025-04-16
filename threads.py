# threads.py
# Copyright (c) 2025 DJ Kruger
import os
import datetime
import random
import time
import logging
import sys
import subprocess
import queue
import requests
import threading
from PyQt6.QtCore import QThread, pyqtSignal
from config import load_config
from utils import calculate_executable_hash, send_email
import hashlib


class MainLogicThread(QThread):
    trigger_popup = pyqtSignal(str, bool)

    def __init__(self, stop_event):
        super().__init__()
        self.config = load_config()
        self.stop_event = stop_event
        logging.info("MainLogicThread initialized successfully")

    def run(self):
        logging.info("MainLogicThread started")
        current_hash = calculate_executable_hash()
        if current_hash and current_hash != self.config["expected_hash"]:
            send_email(
                self.config,
                "Integrity Check Failed",
                f"Hash mismatch: expected {self.config['expected_hash']}, got {current_hash}",
            )

        while not self.stop_event.is_set():
            try:
                self.config = load_config()
                now = datetime.datetime.now()
                start_time = datetime.datetime.strptime(
                    self.config["start_time"], "%H:%M"
                ).time()
                end_time = datetime.datetime.strptime(
                    self.config["end_time"], "%H:%M"
                ).time()

                if start_time > end_time:
                    start_dt = now.replace(
                        hour=start_time.hour, minute=start_time.minute, second=0
                    )
                    if now.time() < end_time:
                        start_dt -= datetime.timedelta(days=1)
                    end_dt = start_dt + datetime.timedelta(days=1)
                    end_dt = end_dt.replace(
                        hour=end_time.hour, minute=end_time.minute, second=0
                    )
                else:
                    start_dt = now.replace(
                        hour=start_time.hour, minute=start_time.minute, second=0
                    )
                    end_dt = now.replace(
                        hour=end_time.hour, minute=end_time.minute, second=0
                    )

                if now < start_dt:
                    time.sleep((start_dt - now).total_seconds())
                    continue

                if now < end_dt:
                    total_seconds = (end_dt - now).total_seconds()
                    if total_seconds <= 0:
                        time.sleep(60)
                        continue
                    wait_time = random.uniform(0, total_seconds)
                    time.sleep(wait_time)
                    self.trigger_popup.emit("Security Alert", True)
                    time.sleep((end_dt - datetime.datetime.now()).total_seconds() + 60)
                else:
                    time.sleep(60)
            except Exception as e:
                logging.error(f"Error in MainLogicThread: {str(e)}")
                send_email(
                    self.config,
                    "Thread Error",
                    f"MainLogicThread encountered an error: {str(e)}",
                )
                time.sleep(60)


class SoundThread(QThread):
    def __init__(self, config, stop_event):
        super().__init__()
        self.config = config
        self.stop_event = stop_event

    def run(self):
        logging.info("SoundThread started")
        while not self.stop_event.is_set():
            now = datetime.datetime.now()
            start_time = datetime.datetime.strptime(
                self.config["start_time"], "%H:%M"
            ).time()
            end_time = datetime.datetime.strptime(
                self.config["end_time"], "%H:%M"
            ).time()

            if start_time > end_time:
                in_schedule = now.time() >= start_time or now.time() < end_time
            else:
                in_schedule = start_time <= now.time() < end_time

            if in_schedule and self.config["random_sound_enabled"]:
                wait_time = random.randint(
                    self.config["random_sound_min_seconds"],
                    self.config["random_sound_max_seconds"],
                )
                time.sleep(wait_time)
                try:
                    from pygame import mixer

                    mixer.music.load(resource_path("alert_sound.mp3"))
                    mixer.music.play(-1)
                    time.sleep(5)
                    mixer.music.stop()
                    send_email(
                        self.config,
                        "Random Sound Triggered",
                        f"Sound played at {time.strftime('%H:%M:%S')}",
                    )
                except Exception as e:
                    logging.error(f"Random sound failed: {str(e)}")
                    send_email(
                        self.config,
                        "Random Sound Error",
                        f"Failed to play random sound: {str(e)}",
                    )
            else:
                time.sleep(60)


class UpdateCheckerThread(QThread):
    update_available = pyqtSignal(str)

    def __init__(self, config, stop_event):
        super().__init__()
        self.config = config
        self.stop_event = stop_event
        self.current_version = "1.0.0"
        self.app_dir = (
            os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(__file__)
        )
        logging.info("UpdateCheckerThread initialized successfully")

    def run(self):
        logging.info("UpdateCheckerThread started")
        while not self.stop_event.is_set():
            try:
                response = requests.get(self.config["update_url"], timeout=5)
                response.raise_for_status()
                update_data = response.json()
                latest_version = update_data.get("version")
                if latest_version and latest_version > self.current_version:
                    self.apply_update(update_data)
                    self.update_available.emit(f"Updated to {latest_version}")
                    self.current_version = latest_version
                else:
                    logging.info("No update available")
            except Exception as e:
                logging.error(f"Update check failed: {str(e)}")
            time.sleep(3600)

    def apply_update(self, update_data):
        from utils import send_email

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
                send_email(
                    self.config, "Update Error", f"Hash mismatch for {file_name}"
                )

        if "requirements.txt" in changes:
            if getattr(sys, "frozen", False):
                self.update_available.emit(
                    f"New dependencies detected. Please download the latest installer from {update_data.get('download_url', 'unknown URL')}"
                )
            else:
                try:
                    subprocess.check_call(
                        [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "-r",
                            os.path.join(self.app_dir, "requirements.txt"),
                        ]
                    )
                    logging.info("Updated dependencies")
                except Exception as e:
                    logging.error(f"Failed to update dependencies: {str(e)}")
                    send_email(
                        self.config,
                        "Update Error",
                        f"Failed to update dependencies: {str(e)}",
                    )

        if "app.py" in changes:
            logging.info("Restarting app to apply update")
            subprocess.Popen([sys.executable] + sys.argv)
            sys.exit(0)


class ManualPopupThread(QThread):
    trigger_popup = pyqtSignal(str, bool)

    def __init__(self, stop_event):
        super().__init__()
        self.stop_event = stop_event
        logging.info("ManualPopupThread initialized successfully")

    def run(self):
        logging.info("ManualPopupThread started")
        while not self.stop_event.is_set():
            try:
                popup_data = queue.Queue().get(timeout=1.0)
                self.trigger_popup.emit(popup_data["message"], popup_data["play_sound"])
                queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error in ManualPopupThread: {str(e)}")
                send_email(
                    load_config(),
                    "ManualPopupThread Error",
                    f"Error processing manual popup: {str(e)}",
                )
                time.sleep(5)
