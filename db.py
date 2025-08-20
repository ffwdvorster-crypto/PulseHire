import os
import sqlite3
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "pulsehire.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _exec(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    return cur

def init_db(seed=True, seed_keywords=None, seed_admin=True):
    conn = get_connection()
    # Users
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin',
        created_at TEXT NOT NULL
    )""")
    # Keywords
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS keywords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        term TEXT UNIQUE NOT NULL,
        tier INTEGER NOT NULL DEFAULT 2,
        notes TEXT
    )""")
    # Campaigns
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        hours TEXT,
        keywords TEXT,
        notes TEXT,
        created_at TEXT NOT NULL
    )""")
    # Counties
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS counties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )""")
    # Candidates
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        phone TEXT,
        source TEXT,
        resume_text TEXT,
        notes TEXT,
        is_test INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    # Attachments (store path only for simplicity)
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        path TEXT,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
    )""")
    # Test scores
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS test_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        score REAL,
        notes TEXT,
        recorded_at TEXT NOT NULL,
        is_test INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
    )""")
    # Interviews (notes)
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS interviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        notes TEXT,
        date TEXT,
        recorded_at TEXT NOT NULL,
        is_test INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
    )""")
    # Audit logs
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    )""")
    # Ingestion files
    _exec(conn, """
    CREATE TABLE IF NOT EXISTS ingestion_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        filename TEXT NOT NULL,
        uploaded_at TEXT NOT NULL,
        is_test INTEGER NOT NULL DEFAULT 0
    )""")

    # Seed keywords
    if seed and seed_keywords:
        for kw in seed_keywords:
            try:
                _exec(conn, "INSERT OR IGNORE INTO keywords(term, tier, notes) VALUES(?,?,?)",
                      (kw["term"], kw.get("tier", 2), kw.get("notes")))
            except Exception:
                pass

    # Seed counties (Irish counties basic set)
    counties = [
        "Carlow","Cavan","Clare","Cork","Donegal","Dublin","Galway","Kerry","Kildare","Kilkenny",
        "Laois","Leitrim","Limerick","Longford","Louth","Mayo","Meath","Monaghan","Offaly","Roscommon",
        "Sligo","Tipperary","Waterford","Westmeath","Wexford","Wicklow"
    ]
    for c in counties:
        try:
            _exec(conn, "INSERT OR IGNORE INTO counties(name) VALUES(?)", (c,))
        except Exception:
            pass

    if seed and seed_admin:
        # Admin will be created by auth.ensure_seed_admin() which handles hashing.
        pass

    conn.close()

# --- Convenience funcs ---
def add_counties(names):
    conn = get_connection()
    for n in names:
        if n.strip():
            _exec(conn, "INSERT OR IGNORE INTO counties(name) VALUES(?)", (n.strip(),))
    conn.close()

def remove_county(name):
    conn = get_connection()
    _exec(conn, "DELETE FROM counties WHERE name=?", (name,))
    conn.close()

def list_counties():
    conn = get_connection()
    rows = _exec(conn, "SELECT name FROM counties ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]

def list_keywords():
    conn = get_connection()
    rows = _exec(conn, "SELECT term, tier, notes FROM keywords ORDER BY tier, term").fetchall()
    conn.close()
    return [{"term": r["term"], "tier": r["tier"], "notes": r["notes"]} for r in rows]

def add_keyword(term, tier=2, notes=None):
    conn = get_connection()
    _exec(conn, "INSERT OR IGNORE INTO keywords(term, tier, notes) VALUES(?,?,?)", (term, int(tier), notes))
    conn.close()

def add_campaign(name, hours=None, keywords=None, notes=None):
    conn = get_connection()
    _exec(conn, "INSERT INTO campaigns(name, hours, keywords, notes, created_at) VALUES(?,?,?,?,?)",
          (name, hours, keywords, notes, datetime.utcnow().isoformat()))
    conn.close()

def list_campaigns():
    conn = get_connection()
    rows = _exec(conn, "SELECT id, name, hours, keywords, notes, created_at FROM campaigns ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_candidate(name=None, email=None, phone=None, source=None, resume_text=None, notes=None, is_test=0):
    conn = get_connection()
    cur = _exec(conn, "INSERT INTO candidates(name, email, phone, source, resume_text, notes, is_test, created_at) VALUES(?,?,?,?,?,?,?,?)",
          (name, email, phone, source, resume_text, notes, int(is_test), datetime.utcnow().isoformat()))
    cid = cur.lastrowid
    conn.close()
    return cid

def find_candidate_by_email(email):
    conn = get_connection()
    row = _exec(conn, "SELECT * FROM candidates WHERE email=? ORDER BY id DESC LIMIT 1", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_test_score(candidate_id, source, score, notes=None, is_test=0):
    conn = get_connection()
    _exec(conn, "INSERT INTO test_scores(candidate_id, source, score, notes, recorded_at, is_test) VALUES(?,?,?,?,?,?)",
          (candidate_id, source, score, notes, datetime.utcnow().isoformat(), int(is_test)))
    conn.close()

def add_interview_note(candidate_id, notes, date=None, is_test=0):
    conn = get_connection()
    _exec(conn, "INSERT INTO interviews(candidate_id, notes, date, recorded_at, is_test) VALUES(?,?,?,?,?)",
          (candidate_id, notes, date, datetime.utcnow().isoformat(), int(is_test)))
    conn.close()

def log_action(user_id, action, details=None):
    conn = get_connection()
    _exec(conn, "INSERT INTO audit_logs(user_id, action, details, created_at) VALUES(?,?,?,?)",
          (user_id, action, details, datetime.utcnow().isoformat()))
    conn.close()