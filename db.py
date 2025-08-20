import sqlite3

DB_FILE = "pulsehire.db"

def get_db():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Basic tables (extend later)
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, name TEXT, password_hash TEXT, role TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value_json TEXT)")
    conn.commit()
    conn.close()
