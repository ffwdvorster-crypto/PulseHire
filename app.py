# PulseHire — Streamlit app
# Features: Auth+RBAC, Active recruitment, Campaigns (with weekly hours), Candidates (bulk actions),
# Hiring Areas (auto-DNC), Attachments with types, Compliance tab, Retention cleanup, Branding + theme toggle

import os
import re
import io
import json
import hashlib
import sqlite3
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import streamlit as st

# ---------- App Meta / Branding ----------
APP_NAME = "PulseHire"
VERSION = "1.3.0"

st.set_page_config(page_title=f"{APP_NAME} v{VERSION}", layout="wide")

# Theme toggle (session)
if "theme" not in st.session_state:
    st.session_state["theme"] = "light"

def inject_theme_css():
    light = {
        "--bg": "#ffffff",
        "--panel": "#f8fafc",
        "--text": "#111827",
        "--muted": "#6b7280",
        "--brand": "#00b89f",
        "--brand-2": "#1a6f49",
        "--accent": "#ffc600",
        "--danger": "#ef4444",
        "--ok": "#10b981",
    }
    dark = {
        "--bg": "#0f172a",
        "--panel": "#111827",
        "--text": "#e5e7eb",
        "--muted": "#9ca3af",
        "--brand": "#00b89f",
        "--brand-2": "#22d3ee",
        "--accent": "#ffd166",
        "--danger": "#f87171",
        "--ok": "#34d399",
    }
    vars = dark if st.session_state["theme"] == "dark" else light
    css = f"""
    <style>
      :root {{
        {"".join([f"{k}:{v};" for k,v in vars.items()])}
      }}
      .pulse-header {{
        display:flex; align-items:center; justify-content:space-between;
        padding: 12px 16px; background: var(--panel); border-radius: 12px; margin-bottom: 8px;
        border: 1px solid rgba(0,0,0,0.06);
      }}
      .pulse-title {{
        font-family: Nunito, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
        font-weight: 800; font-size: 22px; color: var(--text);
      }}
      .pulse-badge {{
        display:inline-flex; align-items:center; gap:8px; padding:4px 10px; border-radius:999px;
        background: var(--brand); color: white; font-weight:700; font-size: 12px; margin-left:8px;
      }}
      .pulse-topright {{
        display:flex; align-items:center; gap:10px;
      }}
      .pulse-chip {{
        display:inline-block; padding:2px 8px; border-radius:999px; background: var(--panel);
        border:1px solid rgba(0,0,0,0.08); color: var(--text); font-size:12px;
      }}
      .ok {{ color: var(--ok); }}
      .danger {{ color: var(--danger); }}
      .stButton>button {{
        border-radius: 10px; font-weight: 700;
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

inject_theme_css()

# ---------- Paths / DB ----------
ROOT = os.path.dirname(__file__)
DB_PATH = os.path.join(ROOT, "portal.db")
UPLOAD_DIR = os.path.join(ROOT, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- Constants ----------
STATUSES = ["New","Called","No Answer","Voicemail","Interviewed","Rejected","Hired","DNC"]
DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
ATTACH_TYPES = ["CV","Visa","Speed Test","Interview Notes","Other"]

# ---------- Utilities ----------
def sstrip(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip()

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", sstrip(s).lower()) if s is not None else ""

def subtract_workdays(d: date, n: int) -> date:
    days = 0
    cur = d
    while days < n:
        cur -= timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return cur

# ---------- Auth / RBAC ----------
def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return salt.hex() + ":" + hashed.hex()

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return check == expected
    except Exception:
        return False

def db_init():
    with db_conn() as con:
        # Users / auth
        con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            name TEXT,
            password_hash TEXT,
            role TEXT, -- admin, recruiter, hr, viewer
            created_at TEXT,
            updated_at TEXT
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            target TEXT,
            meta TEXT,
            at TEXT
        )""")
        # Campaigns + hours
        con.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            hours TEXT,
            requirements_text TEXT,
            req_need_weekends INTEGER DEFAULT 0,
            req_need_evenings INTEGER DEFAULT 0,
            req_need_weekdays INTEGER DEFAULT 0,
            req_remote_ok INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS campaign_hours (
            campaign_id INTEGER,
            dow INTEGER,
            enabled INTEGER DEFAULT 0,
            start_time TEXT,
            end_time TEXT,
            PRIMARY KEY (campaign_id, dow),
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
        )""")
        # Active recruitment
        con.execute("""
        CREATE TABLE IF NOT EXISTS active_recruitment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            start_date TEXT,
            cutoff_date TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
        )""")
        # Candidates
        con.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            name TEXT,
            phone TEXT,
            county TEXT,
            availability TEXT,
            source TEXT,
            completion_time TEXT,
            notes TEXT,
            status TEXT DEFAULT 'New',
            last_attempt TEXT,
            interview_dt TEXT,
            campaign TEXT,
            created_at TEXT,
            updated_at TEXT,
            dnc INTEGER DEFAULT 0,
            -- enrich
            notice_period TEXT,
            planned_leave TEXT
        )""")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_email ON candidates (LOWER(email))")
        con.execute("CREATE INDEX IF NOT EXISTS idx_candidates_name_phone ON candidates (LOWER(name), phone)")
        # Attachments
        con.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            filename TEXT,
            path TEXT,
            uploaded_at TEXT,
            doc_type TEXT,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )""")
        # Test scores
        con.execute("""
        CREATE TABLE IF NOT EXISTS test_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            provider TEXT,
            test_name TEXT,
            score_raw TEXT,
            score_pct TEXT,
            imported_at TEXT,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )""")
        # Hiring areas / auto-DNC
        con.execute("""CREATE TABLE IF NOT EXISTS blocked_counties (county TEXT
