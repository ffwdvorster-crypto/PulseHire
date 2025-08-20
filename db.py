import os
import sqlite3
from datetime import datetime

DB_FILE = "pulsehire.db"

# --- Connections ---
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

# Back-compat alias for ingestion.py
def get_connection():
    return get_conn()

def _exec(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    return cur

# --- Schema init ---
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

    # Keywords (optional, for scoring seed)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT UNIQUE NOT NULL,
            tier INTEGER NOT NULL DEFAULT 2,
            notes TEXT
        )
    """)

    # Campaigns
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            hours TEXT,
            keywords TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Counties
    cur.execute("""
        CREATE TABLE IF NOT EXISTS counties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)

    # Candidates (with resume_text/notes/is_test for ingestion/scoring)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            source TEXT,
            resume_text TEXT,
            notes TEXT,
            is_test INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Attachments (path only for simplicity)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            path TEXT,
            uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
        )
    """)

    # Test scores (includes 'source' + is_test to match ingestion)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            score REAL,
            notes TEXT,
            recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
            is_test INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
        )
    """)

    # Interviews (notes)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            notes TEXT,
            date TEXT,
            recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
            is_test INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
        )
    """)

    # Audit logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()

# --- Campaigns ---
def add_campaign(name, hours=None, keywords=None, notes=None):
    conn = get_conn()
    _exec(conn, """
        INSERT INTO campaigns (name, hours, keywords, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, hours, keywords, notes, datetime.utcnow().isoformat()))
    conn.close()

def list_campaigns():
    conn = get_conn()
    rows = _exec(conn, "SELECT id, name, hours, keywords, notes, created_at FROM campaigns ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(zip([c[0] for c in rows.cursor.description], r)) if hasattr(rows, 'cursor') else dict(r) for r in rows]  # defensive
    # (Streamlit will mostly use its own dataframe creation; safe to ignore if not used.)

# --- Counties ---
def add_county(name):
    if not name or not name.strip():
        return
    conn = get_conn()
    try:
        _exec(conn, "INSERT INTO counties(name) VALUES(?)", (name.strip(),))
    except sqlite3.IntegrityError:
        pass
    conn.close()

def add_counties(names):
    for n in names:
        add_county(n)

def get_counties():
    conn = get_conn()
    rows = _exec(conn, "SELECT name FROM counties ORDER BY name").fetchall()
    conn.close()
    return rows

def remove_county(name):
    conn = get_conn()
    _exec(conn, "DELETE FROM counties WHERE name=?", (name,))
    conn.close()

# --- Candidates & related (for ingestion.py expectations) ---
def add_candidate(name=None, email=None, phone=None, source=None, resume_text=None, notes=None, is_test=0):
    conn = get_conn()
    cur = _exec(conn, """
        INSERT INTO candidates (name, email, phone, source, resume_text, notes, is_test, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, phone, source, resume_text, notes, int(is_test), datetime.utcnow().isoformat()))
    cid = cur.lastrowid
    conn.close()
    return cid

def find_candidate_by_email(email):
    conn = get_conn()
    row = _exec(conn, "SELECT * FROM candidates WHERE email=? ORDER BY id DESC LIMIT 1", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_test_score(candidate_id, source, score, notes=None, is_test=0):
    conn = get_conn()
    _exec(conn, """
        INSERT INTO test_scores (candidate_id, source, score, notes, recorded_at, is_test)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (candidate_id, source, score, notes, datetime.utcnow().isoformat(), int(is_test)))
    conn.close()

def add_interview_note(candidate_id, notes, date=None, is_test=0):
    conn = get_conn()
    _exec(conn, """
        INSERT INTO interviews (candidate_id, notes, date, recorded_at, is_test)
        VALUES (?, ?, ?, ?, ?)
    """, (candidate_id, notes, date, datetime.utcnow().isoformat(), int(is_test)))
    conn.close()

# --- (Optional) simple keyword helpers used by scoring.py ---
def list_keywords():
    conn = get_conn()
    rows = _exec(conn, "SELECT term, tier, notes FROM keywords ORDER BY tier, term").fetchall()
    conn.close()
    return [{"term": r["term"], "tier": r["tier"], "notes": r["notes"]} for r in rows]

def add_keyword(term, tier=2, notes=None):
    conn = get_conn()
    _exec(conn, "INSERT OR IGNORE INTO keywords(term, tier, notes) VALUES(?,?,?)", (term, int(tier), notes))
    conn.close()

# Initialize on import
init_db()
