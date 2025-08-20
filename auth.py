# auth.py — login + RBAC (PBKDF2 with per-user salt) + default admin seeding
import os, base64, hashlib, hmac
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional
from db import connect

PBKDF_ITER = 100_000

@dataclass
class User:
    id: int
    email: str
    name: str
    role: str

def _now() -> str:
    return datetime.now(UTC).isoformat()

def _hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF_ITER)
    return base64.b64encode(dk).decode()

def create_user(email: str, name: str, role: str, password: str):
    if role not in {"admin","recruiter","hr","viewer"}:
        raise ValueError("Invalid role")
    salt = os.urandom(16)
    pw_hash = _hash_password(password, salt)
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO users(email,name,role,password_hash,salt,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (email, name, role, pw_hash, base64.b64encode(salt).decode(), _now(), _now())
        )

def get_user_by_email(email: str) -> Optional[User]:
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(?)", (email,))
        row = cur.fetchone()
        if not row: return None
        return User(id=row["id"], email=row["email"], name=row["name"], role=row["role"])

def verify_password(email: str, password: str) -> Optional[User]:
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(?)", (email,))
        row = cur.fetchone()
        if not row: return None
        salt = base64.b64decode(row["salt"])
        expected = row["password_hash"]
        test = _hash_password(password, salt)
        if hmac.compare_digest(test, expected):
            return User(id=row["id"], email=row["email"], name=row["name"], role=row["role"])
        return None

def users_exist() -> bool:
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM users")
        return (cur.fetchone()["c"] or 0) > 0

def seed_admin_if_empty():
    """
    Seeds a default admin if there are no users.
    Default Admin:
      Email: admin@pulsehire.local
      Password: admin
    """
    if users_exist():
        return
    try:
        create_user("admin@pulsehire.local", "Admin", "admin", "admin")
    except Exception:
        # if a race condition happens in multi-worker environments, ignore
        pass
