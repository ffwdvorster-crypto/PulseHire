import sqlite3
from werkzeug.security import generate_password_hash

DB_FILE = "pulsehire.db"

def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        name TEXT,
        password_hash TEXT,
        role TEXT CHECK(role IN ('admin','recruiter','hr','viewer')) NOT NULL DEFAULT 'admin',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

def seed_admin_if_empty():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (count,) = cur.fetchone()
    if count == 0:
        cur.execute(
            "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
            ("admin@pulsehire.local", "Default Admin", generate_password_hash("admin"), "admin")
        )
        conn.commit()

def get_user_by_email(email: str):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (email,))
    row = cur.fetchone()
    return dict(row) if row else None

def set_setting(key, value_json):
    import json
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value_json TEXT)")
    cur.execute("INSERT OR REPLACE INTO settings(key,value_json) VALUES(?,?)",
                (key, json.dumps(value_json)))
    conn.commit()

def get_setting(key, default=None):
    import json
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value_json TEXT)")
    cur.execute("SELECT value_json FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return (json.loads(row["value_json"]) if row else default)
