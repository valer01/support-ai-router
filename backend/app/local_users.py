"""Local username/password user store — bcrypt-hashed, persisted to JSON.
Adapted from ask-devops-dashboard's local_users.py (same pattern, renamed).
"""
from __future__ import annotations
import json
import os
import secrets
import stat
import string
import threading

import bcrypt

_DATA_DIR = os.environ.get(
    "SUPPORTROUTER_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data")
)
_USERS_PATH = os.path.join(_DATA_DIR, "local_users.json")
_INITIAL_CREDS_PATH = os.path.join(_DATA_DIR, "INITIAL_LOGIN_CREDENTIALS.txt")
_LOCK = threading.Lock()

DEFAULT_USERNAME = os.environ.get("SUPPORTROUTER_SEED_USERNAME", "support.admin")


def _ensure_dir():
    os.makedirs(_DATA_DIR, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if not os.path.exists(_USERS_PATH):
        return {}
    with _LOCK:
        with open(_USERS_PATH) as f:
            return json.load(f)


def _save(users: dict):
    _ensure_dir()
    with _LOCK:
        with open(_USERS_PATH, "w") as f:
            json.dump(users, f, indent=2)
        os.chmod(_USERS_PATH, stat.S_IRUSR | stat.S_IWUSR)


def _gen_password(length: int = 18) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()


def verify_password(username: str, plaintext: str) -> bool:
    users = _load()
    user = users.get(username)
    if not user:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode(), user["password_hash"].encode())
    except Exception:
        return False


def get_user(username: str):
    return _load().get(username)


def set_password(username: str, plaintext: str, name: str = "", email: str = ""):
    users = _load()
    existing = users.get(username, {})
    users[username] = {
        "password_hash": hash_password(plaintext),
        "name": name or existing.get("name") or username,
        "email": email or existing.get("email", ""),
    }
    _save(users)


def seed_default_user_if_missing() -> str | None:
    if os.path.exists(_USERS_PATH):
        return None
    password = _gen_password()
    set_password(DEFAULT_USERNAME, password, name="Support Router Admin")
    _ensure_dir()
    with open(_INITIAL_CREDS_PATH, "w") as f:
        f.write(
            "Support AI Router — initial local login credentials\n"
            "=====================================================\n"
            f"Username: {DEFAULT_USERNAME}\n"
            f"Password: {password}\n\n"
            "Log in once at /auth/login, then DELETE this file.\n"
        )
    os.chmod(_INITIAL_CREDS_PATH, stat.S_IRUSR | stat.S_IWUSR)
    return password
