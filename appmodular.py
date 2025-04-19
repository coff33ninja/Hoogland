# app.py
# Copyright (c) 2025 DJ Kruger
# Licensed under the MIT License.
import os
import sys
import signal
import threading
import logging
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QPixmap, QIcon, QColor
from PyQt6.QtCore import Qt
from waitress import serve
from pygame import mixer
from flask import Flask
from config import load_config, save_config
from auth import init_login_manager
from threads import MainLogicThread, SoundThread, UpdateCheckerThread, ManualPopupThread
from alerts import show_popup, AlertDialog
from routes import register_routes
from utils import resource_path, cleanup

# Initialize logging
app_data_dir = os.path.join(os.getenv("APPDATA", os.path.expanduser("~/.hoogland")), "Hoogland")
log_file = os.path.join(app_data_dir, "app.log")
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.info("Application started")

# Initialize Flask app
app = Flask(__name__, template_folder=resource_path("templates"))
app.secret_key = os.urandom(24).hex()

# Initialize Flask-Login
init_login_manager(app)

# Register routes
register_routes(app)

# Initialize pygame mixer
mixer.init()

# Global variables
qt_app = None
stop_event = threading.Event()

def run_waitress():
    logging.info("Starting Waitress server on 0.0.0.0:5000")
    serve(app, host="0.0.0.0", port=5000, threads=2)

if __name__ == "__main__":
    # Load configuration
    config = load_config()
    if not config.get("users"):
        import webbrowser

        webbrowser.open("http://localhost:5000/setup")

    # Initialize Qt application
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    # System tray setup
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor("red"))
    tray_icon = QIcon(pixmap)
    tray = QSystemTrayIcon()
    tray.setIcon(tray_icon)
    tray.setToolTip("Security Alert App")
    tray.setVisible(True)

    tray_menu = QMenu()
    quit_action = tray_menu.addAction("Quit")
    quit_action.triggered.connect(lambda: cleanup(qt_app=qt_app, stop_event=stop_event))
    tray.setContextMenu(tray_menu)

    # Start threads
    main_thread = MainLogicThread(stop_event)
    main_thread.trigger_popup.connect(
        lambda message, play_sound: show_popup(config, message, play_sound)
    )
    main_thread.start()

    manual_thread = ManualPopupThread(stop_event)
    manual_thread.trigger_popup.connect(
        lambda message, play_sound: show_popup(config, message, play_sound)
    )
    manual_thread.start()

    sound_thread = SoundThread(config, stop_event)
    sound_thread.start()

    update_thread = UpdateCheckerThread(config, stop_event)
    update_thread.update_available.connect(
        lambda update_message: tray.showMessage(
            "Hoogland Update",
            update_message,
            QSystemTrayIcon.MessageIcon.Information,
            10000,
        )
    )
    update_thread.start()

    # Start Waitress server
    waitress_thread = threading.Thread(target=run_waitress, daemon=True)
    waitress_thread.start()

    # Signal handlers
    signal.signal(signal.SIGINT, lambda s, f: cleanup(qt_app=qt_app, stop_event=stop_event))
    signal.signal(signal.SIGTERM, lambda s, f: cleanup(qt_app=qt_app, stop_event=stop_event))

    # Run Qt event loop
    try:
        qt_app.exec()
    except Exception as e:
        logging.error(f"Qt app crashed: {str(e)}")
        cleanup(qt_app=qt_app, stop_event=stop_event)
