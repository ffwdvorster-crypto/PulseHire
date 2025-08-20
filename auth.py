import sqlite3
import hashlib
import db

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def login(email: str, password: str):
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, email, password FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()
    if row and row[2] == hash_pw(password):
        return {"id": row[0], "email": row[1]}
    return None

def create_user(email: str, password: str):
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hash_pw(password)))
    conn.commit()
    conn.close()

def change_password(email: str, new_password: str):
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password=? WHERE email=?", (hash_pw(new_password), email))
    conn.commit()
    conn.close()

def ensure_seed_admin():
    """Create seeded admin after DB init."""
    conn = db.get_conn()
    cur = conn.cursor()
    # Make sure table exists (in case init wasn't called yet)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    cur.execute("SELECT 1 FROM users WHERE email=?", ("admin@pulsehire.local",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (email, password) VALUES (?, ?)",
            ("admin@pulsehire.local", hash_pw("admin123"))
        )
    conn.commit()
    conn.close()

# IMPORTANT: do NOT call ensure_seed_admin() here.
# Call it from app.py *after* db.init_db().
