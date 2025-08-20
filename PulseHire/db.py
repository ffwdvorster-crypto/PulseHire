import sqlite3, json, os, datetime

DB_FILE = "pulsehire.db"

def get_db():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Users
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        name TEXT,
        password_hash TEXT,
        role TEXT CHECK(role IN ('admin','recruiter','hr','viewer')) NOT NULL DEFAULT 'recruiter',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # Audit
    cur.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        target TEXT,
        meta_json TEXT,
        at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # Settings
    cur.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value_json TEXT
    )""")

    # Campaigns
    cur.execute("""CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        hours_notes TEXT,
        requirements_text TEXT,
        req_need_weekends INTEGER DEFAULT 0,
        req_need_evenings INTEGER DEFAULT 0,
        req_need_weekdays INTEGER DEFAULT 1,
        req_remote_ok INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # Campaign hours
    cur.execute("""CREATE TABLE IF NOT EXISTS campaign_hours (
        campaign_id INTEGER,
        dow INTEGER,
        enabled INTEGER,
        start_time TEXT,
        end_time TEXT,
        PRIMARY KEY (campaign_id, dow)
    )""")

    # Active recruitment
    cur.execute("""CREATE TABLE IF NOT EXISTS active_recruitment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER,
        start_date TEXT,
        cutoff_date TEXT,
        notes TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # Blocked counties
    cur.execute("""CREATE TABLE IF NOT EXISTS blocked_counties (
        county TEXT PRIMARY KEY
    )""")

    # Candidates
    cur.execute("""CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        name TEXT,
        phone TEXT,
        county TEXT,
        availability TEXT,
        source TEXT,
        completion_time TEXT,
        notes TEXT,
        status TEXT,
        last_attempt TEXT,
        interview_dt TEXT,
        campaign TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        dnc INTEGER DEFAULT 0,
        dnc_reason TEXT,
        dnc_override INTEGER DEFAULT 0,
        is_test INTEGER DEFAULT 0,
        notice_period TEXT,
        planned_leave TEXT,
        score_tier TEXT,
        flags_json TEXT
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cand_email ON candidates(LOWER(email))")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cand_name_phone ON candidates(LOWER(name), phone)")

    # Attachments
    cur.execute("""CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER,
        filename TEXT,
        path TEXT,
        uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        doc_type TEXT
    )""")

    # Test scores
    cur.execute("""CREATE TABLE IF NOT EXISTS test_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER,
        provider TEXT,
        test_name TEXT,
        score_raw TEXT,
        score_pct REAL,
        imported_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()

def set_setting(key, value):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings(key,value_json) VALUES(?,?)", (key, json.dumps(value)))
    conn.commit(); conn.close()

def get_setting(key, default=None):
    conn = get_db(); conn.row_factory = sqlite3.Row; cur = conn.cursor()
    cur.execute("SELECT value_json FROM settings WHERE key=?", (key,))
    row = cur.fetchone(); conn.close()
    return json.loads(row["value_json"]) if row else default

def add_audit(user_id, action, target, meta):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO audit_logs(user_id,action,target,meta_json) VALUES(?,?,?,?)",
                (user_id, action, target, json.dumps(meta or {})))
    conn.commit(); conn.close()

def purge_older_than_years(years=2):
    # For demo, just delete candidates older than N years by created_at
    conn = get_db(); cur = conn.cursor()
    cur.execute("""DELETE FROM candidates WHERE date(created_at) <= date('now', ?)""", (f'-{years} years',))
    n = cur.rowcount
    conn.commit(); conn.close()
    return n
