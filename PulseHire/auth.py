import sqlite3, bcrypt
from db import get_db

def ensure_admin_exists():
    conn = get_db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        name TEXT,
        password_hash TEXT,
        role TEXT
    )""")
    conn.commit()
    c.execute("SELECT 1 FROM users WHERE email=?", ("admin@pulsehire.local",))
    if not c.fetchone():
        hashed = bcrypt.hashpw("admin".encode("utf-8"), bcrypt.gensalt())
        c.execute("INSERT INTO users(email,name,password_hash,role) VALUES(?,?,?,?)",
                  ("admin@pulsehire.local","Admin",hashed,"admin"))
        conn.commit()
    conn.close()

def login_user(email, password):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id,email,name,password_hash,role FROM users WHERE lower(email)=lower(?)", (email,))
    row = c.fetchone(); conn.close()
    if row and bcrypt.checkpw(password.encode("utf-8"), row[3]):
        return {"id":row[0],"email":row[1],"name":row[2],"role":row[4]}
    return None

def create_user(email, name, password, role="recruiter"):
    if role not in ("admin","recruiter","hr","viewer"):
        raise ValueError("Invalid role")
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)", (email,))
    if c.fetchone():
        conn.close(); raise ValueError("A user with that email already exists.")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    c.execute("INSERT INTO users(email,name,password_hash,role) VALUES(?,?,?,?)",
              (email, name or email.split("@")[0], hashed, role))
    conn.commit(); conn.close()

def change_password(user_id, new_password):
    conn = get_db(); c = conn.cursor()
    hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
    c.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed, user_id))
    conn.commit(); n=c.rowcount; conn.close(); return n

def list_users():
    conn = get_db(); conn.row_factory = sqlite3.Row; c = conn.cursor()
    c.execute("SELECT id,email,name,role FROM users ORDER BY role,email")
    rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows
