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

# --- Seed admin user ---
def seed_admin():
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", ("admin@pulsehire.local",))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (email, password) VALUES (?, ?)", 
                    ("admin@pulsehire.local", hash_pw("admin123")))
    conn.commit()
    conn.close()

# Call seeding on import
seed_admin()
