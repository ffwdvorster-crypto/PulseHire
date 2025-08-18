import io
import os
import re
import sqlite3
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Set, Optional

import pandas as pd
import streamlit as st
from dateutil import parser as dtparse

# ---- Version & Changelog (simple, code-based) ----
VERSION = "1.0.0"

# ---- Version & Changelog (simple, code-based) ----
VERSION = "1.0.0"

CHANGELOG = [
    # (version, date, summary, details)
    ("1.0.0", "2025-08-18", "Initial PSR Recruitment Portal",
     "Campaigns, Recruitment Drives, Candidates with de-dupe ingest, Candidate file view, DNC, Bulk Emails."),
    # Add new entries above this line as you update:
    # ("1.0.1", "YYYY-MM-DD", "Your short summary", "Your detailed description...")
]

st.set_page_config(page_title=f"PSR Recruitment Portal v{VERSION}", layout="wide")

DB_PATH = os.path.join(os.path.dirname(__file__), "portal.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

STATUSES = ["New","Called","No Answer","Voicemail","Interviewed","Rejected","Hired","DNC"]

def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def db_init():
    with db_conn() as con:
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
        CREATE TABLE IF NOT EXISTS drives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            start_date TEXT,
            cutoff_date TEXT,
            fte_target INTEGER,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
