
# Hoogland
Hoogland is a security alert application designed to keep users vigilant during specified time windows, such as night shifts or monitoring duties. It triggers random popups with sound notifications to ensure attention, logs interactions, and sends email reports. Configuration is managed through an intuitive web-based GUI, and the app supports silent updates from GitHub for seamless maintenance.

## Purpose
The primary goal of Hoogland is to enhance security and alertness by:
- Delivering unpredictable alerts within a user-defined schedule (e.g., 18:00–23:59).
- Requiring user acknowledgment to prevent unattended stations.
- Sending email notifications for late responses, unacknowledged alerts, or system events.
- Providing a tamper-resistant configuration with encrypted password storage.

Ideal for security personnel, system administrators, or anyone needing to stay awake and responsive during critical hours.

## Features
- **Random Alerts**: Popups occur at unpredictable intervals within a configurable time window.
- **Web-Based Configuration UI**: Manage settings via a browser at `http://localhost:5000/admin`.
- **Encrypted Password Storage**: Email credentials are securely encrypted and only editable via the GUI.
- **Silent Updates**: Automatically pulls updates from GitHub, applying changes or notifying for full installer downloads.
- **System Tray Integration**: Runs discreetly with a tray icon for easy access and exit.

## Installation
1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Run Locally**:
   ```bash
   python app.py
   ```
3. **Or Use the Installer**:
   - Download `HooglandInstaller.exe` from [Releases](https://github.com/coff33ninja/Hoogland/releases).
   - Run the installer to set up with a Startup shortcut.

## Building
- **Bundle with PyInstaller**:
   ```bash
   pyinstaller --onedir --windowed --add-data "alert_sound.mp3;." --add-data "templates;templates" app.py
   ```
- **Compile Installer**:
   - Open `setup.iss` in Inno Setup Compiler and build to generate `HooglandInstaller.exe`.

## Web GUI
On first run (or if `config.json` is missing), Hoogland launches a browser to `http://localhost:5000/admin`. The web interface allows you to:
- **Login**: Use default credentials:
  - **Username**: `admin`
  - **Password**: `password`
- **Configure Settings**:
  - Set email details (sender, recipient, SMTP server, port).
  - Define the alert time window (e.g., `start_time: 18:00`, `end_time: 23:59`).
  - Adjust alert timing, sound options, and email triggers.
  - Update the GitHub update URL.
- **Trigger Manual Popups**: Test alerts with custom messages and sound.
- **View Logs**: Check application logs for debugging.
- **Manage Backups**: Download or restore configuration backups.

After initial setup, access the GUI anytime by navigating to `http://localhost:5000` and logging in.

## Login Details
- **Default Credentials**:
  - **Username**: `admin`
  - **Password**: `password`
- **Security Note**: These are hardcoded for simplicity. For production, modify `app.py`’s `login()` function to use secure, configurable credentials (e.g., environment variables or a database).

## Usage
1. Run the app or installer.
2. On first launch, configure via the web GUI.
3. The app minimizes to the system tray, triggering random alerts during the set window.
4. Acknowledge alerts to log response times and avoid email warnings.
5. Updates are checked hourly, applying changes silently or notifying via the tray.

## Development
- **Repository**: [https://github.com/coff33ninja/Hoogland](https://github.com/coff33ninja/Hoogland)
- **Versioning**: Uses semantic versioning (e.g., `1.0.0`). Check `UpdateCheckerThread.current_version` in `app.py`.
- **Contributing**: Fork, modify, and submit a PR!
```

---

### Steps to Update
1. **Replace `README.md`**:
   - Open `Hoogland/README.md` in a text editor.
   - Copy and paste the above content.

2. **Commit and Push**:
   ```powershell
   cd Hoogland
   git add README.md
   git commit -m "Update README with purpose, login details, and web GUI info"
   git push origin main
   ```

3. **Verify**:
   - Check `https://github.com/coff33ninja/Hoogland` to ensure the README reflects the new info.

---

### Notes
- **Login Security**: I noted the hardcoded credentials as a limitation. If you want to enhance this, I can help add environment variables or a user config file.
- **Web GUI Details**: Assumes you have `admin.html`, `login.html`, etc., in `templates/`. If not, let me know, and I’ll provide sample templates.
- **Purpose**: Tailored to a security/alertness use case—adjust if your vision differs!
- **Email Functionality**: Ensure SMTP settings are correct for your email provider. I can help with that if needed.
- **Testing**: After updating, run the app to ensure the GUI and email features work as expected.
- **Documentation**: Consider adding a `docs/` folder for more detailed user guides or API documentation in the future.
- **Future Features**: If you plan to add more features, consider a `CHANGELOG.md` to track changes and updates.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
