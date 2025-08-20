# db.py — SQLite schema + helpers
import os, json, sqlite3
from contextlib import contextmanager
from datetime import datetime, UTC

DB_PATH = os.path.join(os.path.dirname(__file__), "pulsehire.db")

def _now():
    return datetime.now(UTC).isoformat()

@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db():
    with connect() as con:
        cur = con.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            email TEXT UNIQUE,
            name TEXT,
            password_hash TEXT,
            salt TEXT,
            role TEXT CHECK(role IN ('admin','recruiter','hr','viewer')) NOT NULL,
            created_at TEXT, updated_at TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS audit_logs(
            id INTEGER PRIMARY KEY,
            user_id INTEGER, action TEXT, target TEXT, meta_json TEXT, at TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value_json TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS campaigns(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE,
            hours_notes TEXT, requirements_text TEXT,
            req_need_weekends INTEGER DEFAULT 0,
            req_need_evenings INTEGER DEFAULT 0,
            req_need_weekdays INTEGER DEFAULT 1,
            req_remote_ok INTEGER DEFAULT 0,
            created_at TEXT, updated_at TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS campaign_hours(
            campaign_id INTEGER, dow INTEGER, enabled INTEGER,
            start_time TEXT, end_time TEXT,
            PRIMARY KEY(campaign_id, dow)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS active_recruitment(
            id INTEGER PRIMARY KEY, campaign_id INTEGER,
            start_date TEXT, cutoff_date TEXT, notes TEXT,
            is_active INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS blocked_counties(
            county TEXT PRIMARY KEY
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS candidates(
            id INTEGER PRIMARY KEY,
            email TEXT, name TEXT, phone TEXT, county TEXT,
            availability TEXT, source TEXT, completion_time TEXT,
            notes TEXT, status TEXT, last_attempt TEXT, interview_dt TEXT,
            campaign TEXT,
            created_at TEXT, updated_at TEXT,
            dnc INTEGER DEFAULT 0, dnc_reason TEXT,
            dnc_override INTEGER DEFAULT 0,
            is_test INTEGER DEFAULT 0,
            notice_period TEXT,
            planned_leave TEXT,
            score_tier TEXT,
            flags_json TEXT
        )""")
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_cand_email ON candidates(LOWER(email))""")
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_cand_name_phone ON candidates(LOWER(name), phone)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS attachments(
            id INTEGER PRIMARY KEY, candidate_id INTEGER,
            filename TEXT, path TEXT, uploaded_at TEXT, doc_type TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS test_scores(
            id INTEGER PRIMARY KEY, candidate_id INTEGER,
            provider TEXT, test_name TEXT,
            score_raw TEXT, score_pct REAL, imported_at TEXT
        )""")

def get_setting(key, default=None):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT value_json FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return json.loads(row["value_json"]) if row else default

def set_setting(key, value):
    with connect() as con:
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO settings(key,value_json) VALUES(?,?)",
                    (key, json.dumps(value)))
