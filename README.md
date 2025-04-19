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
- **Encrypted Password Storage**: Email credentials are securely hashed using Argon2 and stored in the configuration file.
- **Silent Updates**: Automatically pulls updates from GitHub, applying changes or notifying for full installer downloads.
- **System Tray Integration**: Runs discreetly with a tray icon for easy access and exit.
- **Setup Wizard**: On first run, a setup wizard guides you through creating an admin account and configuring SMTP settings.
- **User Management**: Admins can create and manage both admin and normal user accounts via the web GUI.

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
   pyinstaller --onedir --windowed --add-data "alert_sound.mp3;." --add-data "templates;templates" --add-data "static;static" app.py
   ```
- **Compile Installer**:
   - Open `setup.iss` in Inno Setup Compiler and build to generate `HooglandInstaller.exe`.

## Web GUI
On first run (or if `config.json` is missing), Hoogland launches a browser to `http://localhost:5000/setup`. The web interface allows you to:
- **Setup Wizard**:
  - Create an admin account with a unique username, secure password, and email address.
  - Configure SMTP settings for email notifications.
  - Credentials are securely hashed and stored, and the password is sent to the provided email.
- **Login**:
  - Use the credentials created during the setup wizard.
- **Configure Settings**:
  - Set email details (sender, recipient, SMTP server, port).
  - Define the alert time window (e.g., `start_time: 18:00`, `end_time: 23:59`).
  - Adjust alert timing, sound options, and email triggers.
  - Update the GitHub update URL.
- **User Management**:
  - Admins can create new users (admin or normal) and delete existing ones.
  - Credentials for new users are emailed securely.
- **Trigger Manual Popups**: Test alerts with custom messages and sound.
- **View Logs**: Check application logs for debugging.
- **Manage Backups**: Download or restore configuration backups.

After initial setup, access the GUI anytime by navigating to `http://localhost:5000` and logging in.

## First Run
On the first run, if `config.json` is missing, Hoogland will redirect to the setup wizard at `http://localhost:5000/setup`. The setup wizard ensures the first account created is an admin account. After completing the setup, you can log in and manage additional users and settings.

## Login Details
- **Admin Account**:
  - Created during the setup wizard.
  - Credentials are emailed to the admin for secure storage.
- **User Accounts**:
  - Admins can create additional admin or normal user accounts via the web GUI.
  - Credentials for new users are emailed securely.

## Usage
1. Run the app or installer.
2. On first launch, complete the setup wizard via the web GUI.
3. The app minimizes to the system tray, triggering random alerts during the set window.
4. Acknowledge alerts to log response times and avoid email warnings.
5. Updates are checked hourly, applying changes silently or notifying via the tray.

## Security Enhancements
- **Password Hashing**: All passwords are hashed using Argon2 for secure storage.
- **Tamper Detection**: Critical files are verified for integrity, and tampering attempts are logged.
- **Encrypted SMTP Credentials**: SMTP passwords are encrypted using a secure key stored in the OS's credential manager.

## Development
- **Repository**: [https://github.com/coff33ninja/Hoogland](https://github.com/coff33ninja/Hoogland)
- **Versioning**: Uses semantic versioning (e.g., `1.0.0`). Check `UpdateCheckerThread.current_version` in `app.py`.
- **Contributing**: Fork, modify, and submit a PR!

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
