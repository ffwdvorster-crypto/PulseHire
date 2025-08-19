import io
import os
import re
import sqlite3
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Set, Optional

import pandas as pd
import streamlit as st
from dateutil import parser as dtparse

# ---- Version & Changelog ----
VERSION = "1.1.0"
CHANGELOG = [
    ("1.1.0", "2025-08-18", "Hiring areas + auto DNC by county",
     "Adds Blocked Counties settings page; auto-flags DNC (reason: outside of hiring area) on ingest; "
     "Apply-to-existing button; Candidate File shows DNC reason and override switch; Do Not Call page can restore. "
     "Also adds safe string handling to avoid 'int has no attribute strip' errors."),
    ("1.0.0", "2025-08-18", "Initial PSR Recruitment Portal",
     "Campaigns, Recruitment Drives, Candidates with de-dupe ingest, Candidate file view, DNC, Bulk Emails."),
]
st.set_page_config(page_title=f"PSR Recruitment Portal v{VERSION}", layout="wide")

DB_PATH = os.path.join(os.path.dirname(__file__), "portal.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

STATUSES = ["New","Called","No Answer","Voicemail","Interviewed","Rejected","Hired","DNC"]

# ------------ Helpers ------------
def sstrip(x) -> str:
    """Safe string strip: handles None/NaN/ints/dates cleanly."""
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

# ------------ DB ------------
def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def db_init():
    with db_conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREME
