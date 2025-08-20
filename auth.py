import sqlite3
import bcrypt

DB_FILE = "pulsehire.db"

def get_db():
    return sqlite3.connect(DB_FILE)

def ensure_admin_exists():
    conn = get_db()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, name TEXT, password_hash TEXT, role TEXT)")
    conn.commit()
    c.execute("SELECT * FROM users WHERE email=?", ("admin@pulsehire.local",))
    if not c.fetchone():
        hashed = bcrypt.hashpw("admin".encode("utf-8"), bcrypt.gensalt())
        c.execute("INSERT INTO users (email, name, password_hash, role) VALUES (?,?,?,?)",
                  ("admin@pulsehire.local", "Admin", hashed, "admin"))
        conn.commit()
    conn.close()

def login_user(email, password):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, email, name, password_hash, role FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode("utf-8"), row[3]):
        return {"id": row[0], "email": row[1], "name": row[2], "role": row[4]}
    return None
