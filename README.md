# Hoogland

Prerequisites

Install the required packages:
bash
pip install flask flask-login playsound==1.2.2

You’ll also need:

    An alert_sound.mp3 file in the same directory as the script (download a free sound file if needed).
    A config.json file (generated automatically if missing).

How It Works

    Desktop Messages:
        The create_alert_window function creates a Tkinter popup with an "I accept" button at random intervals between min_wait_between_alerts_seconds and max_wait_between_alerts_seconds during the start_time to end_time window.
        After sound_after_minutes, an annoying sound plays if the button isn’t pressed.
        If the button is pressed after report_if_longer_than_minutes, an email and web notification are sent.
        If the button isn’t pressed after email_if_not_pressed_after_minutes, another email and web notification are sent.
        Closing the window without pressing the button triggers a notification as well.
    Flask Integration:
        The Flask app runs in parallel, providing a log viewer (/logs), admin panel (/admin), and notification viewer (/notifications).
        Web notifications mirror email events and are stored in the notifications list, accessible via the /notifications route.
    Config Management:
        The load_config function checks for config.json, generates a default if missing, and reloads it dynamically when updated via the admin panel.
    Threading:
        The main logic runs in a separate thread to avoid blocking the Flask server.
        Tkinter’s event loop is managed within the main thread alongside Flask.

Testing

    Setup:
        Save the script as app.py.
        Create a templates folder with the HTML files.
        Place alert_sound.mp3 in the script directory.
        Run python app.py.
    Access:
        Login at http://localhost:5000/login with admin/password.
        Update the config via http://localhost:5000/admin (e.g., set start_time to a few minutes from now for testing).
        Watch for desktop popups during the specified time window.
    Validation:
        Check app.log for logs.
        Verify emails are sent (configure valid SMTP settings first).
        Confirm web notifications appear at http://localhost:5000/notifications.

Notes

    Sound File: Ensure alert_sound.mp3 exists, or adjust the path in the code.
    Email: Use valid credentials (e.g., Gmail with an App Password).
    Security: Replace the dummy admin/password with a proper authentication system for production.
    PyInstaller: To compile, use pyinstaller --onefile --windowed --add-data "alert_sound.mp3;." --add-data "templates;templates" app.py.
