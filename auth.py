import bcrypt
from datetime import datetime
from db import get_connection, _exec

def hash_password(pw: str) -> bytes:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())

def verify_password(pw: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed)
    except Exception:
        return False

def create_user(email: str, password: str, role: str = "admin"):
    conn = get_connection()
    ph = hash_password(password)
    _exec(conn, "INSERT INTO users(email, password_hash, role, created_at) VALUES(?,?,?,?)",
          (email.strip().lower(), ph, role, datetime.utcnow().isoformat()))
    conn.close()

def user_exists(email: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE email=?", (email.strip().lower(),))
    ok = cur.fetchone() is not None
    conn.close()
    return ok

def get_user(email: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email, password_hash, role FROM users WHERE email=?", (email.strip().lower(),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "password_hash": row[2], "role": row[3]}

def verify_user(email: str, password: str):
    u = get_user(email)
    if not u:
        return None
    if verify_password(password, u["password_hash"]):
        return u
    return None

def change_password(email: str, old_password: str, new_password: str) -> bool:
    u = verify_user(email, old_password)
    if not u:
        return False
    conn = get_connection()
    ph = hash_password(new_password)
    _exec(conn, "UPDATE users SET password_hash=? WHERE email=?", (ph, email.strip().lower()))
    conn.close()
    return True

def ensure_seed_admin():
    # Seeded admin (admin@pulsehire.local / admin123)
    email = "admin@pulsehire.local"
    password = "admin123"
    if not user_exists(email):
        create_user(email, password, role="admin")