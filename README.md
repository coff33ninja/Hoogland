Here’s the updated `README.md` with the `--onefile` method added alongside `--onedir`, explaining both options clearly for packaging your app.

```markdown
# Hoogland

A desktop alert system with a web interface for configuration and monitoring, designed to keep you awake or ensure security checks are acknowledged.

---

## Prerequisites

Install the required Python packages in a virtual environment:
```bash
pip install flask flask-login waitress pyqt6 pygame pyinstaller
```

You’ll also need:
- **An `alert_sound.mp3` file**: Place it in the same directory as `app.py` (download a free sound file if needed).
- **A `config.json` file**: Generated automatically if missing, but you can customize it (see Config Management below).
- **HTML templates**: Create a `templates` folder with `login.html`, `admin.html`, `logs.html`, and `notifications.html` (see Testing for details).

---

## How It Works

### Desktop Alerts (PyQt6)
- **Popup Behavior**:
  - Popups appear at random intervals between `min_wait_between_alerts_seconds` and `max_wait_between_alerts_seconds`, but only within the `start_time` to `end_time` window defined in `config.json`.
  - A PyQt6 dialog shows a message (e.g., "Security Alert") with an "I accept" button and stays on top of other windows.
  - After `sound_after_minutes`, an annoying sound (`alert_sound.mp3`) loops until the button is pressed.
  - If the button is pressed after `report_if_longer_than_minutes`, an email and web notification are sent to report the delay.
  - If not pressed after `email_if_not_pressed_after_minutes`, an email and web notification are sent as a reminder.
  - Closing the window without pressing "I accept" triggers a notification about the unacknowledged alert.
- **System Tray**: A red square icon in the system tray provides a "Quit" option to stop the app cleanly.

### Web Interface (Flask + Waitress)
- **Routes**:
  - `/login`: Log in with `admin`/`password`.
  - `/admin`: Configure settings (e.g., timings, email), trigger manual popups, and manage config backups.
  - `/logs`: View `app.log` contents.
  - `/notifications`: See a list of events (mirrors email notifications).
- **Server**: Waitress runs the Flask app on `0.0.0.0:5000`, making it accessible locally or remotely (e.g., `http://192.168.1.100:5000`).

### Config Management
- **`load_config` Function**:
  - Loads `config.json` from the script’s directory.
  - If missing, generates a default config and emails a notification (if SMTP is set up).
  - Dynamically reloads when updated via the `/admin` panel.
  - Validates time formats (`HH:MM`) and reverts to defaults if invalid.

### Threading
- **MainLogicThread**: Handles scheduled popups without blocking the web server or GUI.
- **ManualPopupThread**: Processes manual popups triggered via `/admin`.
- **SoundThread**: Plays random sounds if `random_sound_enabled` is true in the config.
- **Waitress Thread**: Runs the Flask server in parallel with the PyQt6 event loop.

---

## Testing

### Setup
1. Save the script as `app.py`.
2. Create a `templates` folder with:
   - `login.html`: Basic form with `username` and `password` fields.
   - `admin.html`: Config form (matches `config.json` keys) and popup trigger.
   - `logs.html`: Displays log lines.
   - `notifications.html`: Lists notifications.
   (Example `login.html` provided in prior chats or script comments.)
3. Place `alert_sound.mp3` in the script directory.
4. Run:
   ```powershell
   python app.py
   ```

### Access
- **Local**: Go to `http://localhost:5000/login`, log in with `admin`/`password`.
- **Remote**: Use `http://<your-ip>:5000/login` (e.g., `http://192.168.1.100:5000`) after opening port 5000 in your firewall.
- **Config**: Update settings at `/admin` (e.g., set `start_time` to a few minutes from now for testing).

### Validation
- **Popups**: Watch for desktop alerts during the time window.
- **Logs**: Check `app.log` for detailed output.
- **Emails**: Verify emails are sent (configure valid SMTP settings in `config.json` first).
- **Notifications**: Confirm events appear at `/notifications`.

---

## Packaging with PyInstaller

You can package the app into a standalone executable using PyInstaller with two methods: `--onedir` or `--onefile`.

### Option 1: `--onedir` (Recommended)
```powershell
pyinstaller --onedir --windowed --add-data "alert_sound.mp3;." --add-data "templates;templates" app.py
```
- **What It Does**:
  - Creates a folder (`dist\app`) containing:
    - `app.exe`: The executable.
    - `alert_sound.mp3`: Copied as-is.
    - `templates`: Folder with HTML files.
    - Dependency files (e.g., PyQt6, pygame DLLs).
  - `--windowed`: Hides the console window.
  - `--add-data`: Includes the sound file and templates.
- **Distribution**: Zip the `dist\app` folder (e.g., `app.zip`). Users unzip and run `app.exe` from the folder.
- **Why Use It?**: Less likely to trigger antivirus false positives since it doesn’t self-extract (unlike `--onefile`).

### Option 2: `--onefile`
```powershell
pyinstaller --onefile --windowed --add-data "alert_sound.mp3;." --add-data "templates;templates" app.py
```
- **What It Does**:
  - Creates a single `dist\app.exe` file with everything bundled inside.
  - Extracts files to a temporary folder (e.g., `_MEIxxxxxx`) at runtime.
- **Distribution**: Share the single `app.exe` file. No folder needed.
- **Why Use It?**: Convenient for distribution as a single file.
- **Caveat**: More likely to be flagged by antivirus due to the self-extraction behavior.

### Avoiding Antivirus False Positives
- **Test Both**: Run the resulting `.exe` (from either method) and scan with your antivirus (e.g., Windows Defender).
  - ** `--onedir`**: Preferred if false positives occur with `--onefile`.
  - ** `--onefile`**: May trigger heuristics due to unpacking; proceed to next steps if flagged.
- **Sign the Executable**: Use a code-signing certificate (e.g., from DigiCert, ~$60/year) to add trust:
  1. Buy and install the certificate.
  2. Sign with `signtool` (Windows SDK): `signtool sign /f your_cert.pfx /p your_password dist\app.exe`.
- **Rebuild Bootloader**: Compile PyInstaller’s bootloader from source for a unique signature:
  1. `git clone https://github.com/pyinstaller/pyinstaller.git`
  2. `cd pyinstaller/bootloader && python ./waf all --target-arch=64bit`
  3. `cd .. && pip install -e .`
  4. Re-run your PyInstaller command.
- **Whitelist**: Add an exception in your antivirus for testing.

---

## Notes
- **Sound File**: Ensure `alert_sound.mp3` exists in the project root when building, or adjust `resource_path()` in the script.
- **Email**: Use valid SMTP credentials (e.g., Gmail with an App Password) in `config.json`.
- **Security**: Replace `admin`/`password` with a stronger auth system for production.
- **Custom Icon**: Add `--icon your_icon.ico` to PyInstaller for a branded tray icon.
- **Config**: Include `config.json` with the app or let it generate a default on first run.

Enjoy your alert system!
```

---

### Key Additions
- **Packaging Section**: Now includes both `--onedir` and `--onefile` options with pros, cons, and command examples.
- **Antivirus Info**: Explains why `--onefile` might trigger false positives and how `--onedir` avoids it, plus advanced mitigation steps (signing, bootloader rebuild).
- **Clarity**: Kept the structure tight and actionable for users or testers.

This README now covers all bases—functionality, setup, testing, and packaging options—so you’re set to share or deploy this bad boy! Let me know if you want any final tweaks!
