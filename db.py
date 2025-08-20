import sqlite3
import os

DB_FILE = "pulsehire.db"

def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Candidates
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Campaigns
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            hours TEXT,
            keywords TEXT,
            notes TEXT
        )
    """)

    # Counties
    cur.execute("""
        CREATE TABLE IF NOT EXISTS counties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)

    # Attachments (resume uploads etc.)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            filename TEXT,
            path TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )
    """)

    # Test scores
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            test_name TEXT,
            score REAL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )
    """)

    # Audit logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

# --- Helpers used by app.py ---

def add_campaign(name, hours, keywords, notes):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO campaigns (name, hours, keywords, notes) VALUES (?, ?, ?, ?)",
                (name, hours, keywords, notes))
    conn.commit()
    conn.close()

def add_county(name):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO counties (name) VALUES (?)", (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def get_counties():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT name FROM counties ORDER BY name")
    rows = cur.fet
