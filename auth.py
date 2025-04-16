# auth.py
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from argon2 import PasswordHasher
import re
from config import load_config, save_config, cipher

ph = PasswordHasher()


class User(UserMixin):
    def __init__(self, username, role):
        self.id = username
        self.role = role


def init_login_manager(app):
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(username):
        config = load_config()
        for user in config.get("users", []):
            if user["username"] == username:
                return User(username, user["role"])
        return None


def validate_password(password, policy):
    errors = []
    if len(password) < policy.get("min_length", 8):
        errors.append(
            f"Password must be at least {policy.get('min_length', 8)} characters long."
        )
    if policy.get("require_uppercase", True) and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if policy.get("require_lowercase", True) and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if policy.get("require_number", True) and not re.search(r"\d", password):
        errors.append("Password must contain at least one number.")
    if policy.get("require_symbol", True):
        allowed_symbols = policy.get("symbols", "!@#$%^&*()-_=+[]{}|;:'\",.<>?/`~")
        pattern = f"[{re.escape(allowed_symbols)}]"
        if not re.search(pattern, password):
            errors.append(
                f"Password must contain at least one symbol ({allowed_symbols})."
            )
    return errors
