# config.py
import json
import os
import threading
import logging
from cryptography.fernet import Fernet

# Paths
app_data_dir = os.path.join(os.getenv("APPDATA", os.path.expanduser("~/.hoogland")), "Hoogland")
key_path = os.path.join(app_data_dir, "key.bin")
config_path = os.path.join(app_data_dir, "config.json")

# Generate or load encryption key
os.makedirs(app_data_dir, exist_ok=True)
if not os.path.exists(key_path):
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
else:
    with open(key_path, "rb") as f:
        key = f.read()
cipher = Fernet(key)

def load_config():
    config_lock = threading.Lock()
    with config_lock:
        default_config = {
            "users": [],
            "sender_email": "",
            "password": "",
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "recipient_email": "",
            "start_time": "18:00",
            "end_time": "23:59",
            "sound_after_minutes": 3,
            "report_if_longer_than_minutes": 5,
            "email_if_not_pressed_after_minutes": 10,
            "min_wait_between_alerts_seconds": 60,
            "max_wait_between_alerts_seconds": 300,
            "random_sound_enabled": False,
            "random_sound_min_seconds": 300,
            "random_sound_max_seconds": 1800,
            "use_custom_sounds": False,
            "custom_sounds": [],
            "predefined_messages": ["Stay awake!", "Security check!", "Alert now!", "System Check Required"],
            "update_url": "https://raw.githubusercontent.com/coff33ninja/Hoogland/main/latest_version.json",
            "expected_hash": "",
            "is_default": True,
            "password_policy": {
                "min_length": 8,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_number": True,
                "require_symbol": True,
                "symbols": "!@#$%^&*()-_=+[]{}|;:'\",.<>?/`~"
            },
            "enable_math_popup": False,
        }

        config = None
        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                logging.info("Configuration file loaded successfully.")

                config_updated = False
                if "password_policy" not in config:
                    config["password_policy"] = default_config["password_policy"]
                    config_updated = True

                for key, default_value in default_config.items():
                    if key not in config:
                        logging.warning(f"Missing key '{key}' in config. Adding default value.")
                        config[key] = default_value
                        config_updated = True
                    elif key == "password_policy":
                        for p_key, p_default_value in default_config["password_policy"].items():
                            if p_key not in config["password_policy"]:
                                config["password_policy"][p_key] = p_default_value
                                config_updated = True

                if config_updated:
                    save_config(config)

            else:
                logging.warning("Configuration file not found. Creating default configuration file.")
                config = default_config
                save_config(config)

        except json.JSONDecodeError:
            logging.error("Invalid JSON in configuration file. Creating default configuration file.")
            config = default_config
            save_config(config)
        except Exception as e:
            logging.error(f"Error loading or creating config: {str(e)}. Using in-memory default.")
            config = default_config

        if config.get("is_default"):
            config["is_default"] = False

        return config

def save_config(config):
    try:
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a dictionary.")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        logging.info("Configuration file saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save configuration: {str(e)}")
