
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
            dnc INTEGER DEFAULT 0
        )""")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_email ON candidates (LOWER(email))")
        con.execute("CREATE INDEX IF NOT EXISTS idx_candidates_name_phone ON candidates (LOWER(name), phone)")
        con.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            filename TEXT,
            path TEXT,
            uploaded_at TEXT,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )""")
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

# --- Migration: add is_test flag to candidates (safe to run repeatedly)
        try:
            con.execute("ALTER TABLE candidates ADD COLUMN is_test INTEGER DEFAULT 0")
        except Exception:
            pass
            
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower()) if s is not None else ""

def autodetect_columns(df: pd.DataFrame) -> Dict[str, str]:
    norm_cols = {_norm(c): c for c in df.columns}
    def find_col(cands: List[str]):
        for cand in cands:
            key = _norm(cand)
            if key in norm_cols:
                return norm_cols[key]
            for norm_name, orig in norm_cols.items():
                if key in norm_name:
                    return orig
        return None
    return {
        "candidate_name": find_col(["Please provide your full name","Full Name","Name","Candidate Name"]),
        "email": find_col(["What is your email address?","Email Address","Email"]),
        "phone": find_col(["Please enter your phone number","Phone Number","Phone","Contact Number"]),
        "county": find_col(["What county are you based in","County","Location"]),
        "availability": find_col(["If you are only able to work part time","Availability","Shift availability"]),
        "completion_time": find_col(["Completion time","Submitted at","Timestamp"]),
        "source": find_col(["Where did you see the job advertisement?","Source","Job board"]),
        "notes": find_col(["Anything else you want to tell us?","Notes","Additional information"]),
    }

def upsert_candidate(row: Dict[str, Any], is_test: int = 0):
    now = datetime.utcnow().isoformat()
    email = (row.get("email") or "").strip()
    name = (row.get("name") or "").strip()
    phone = (row.get("phone") or "").strip()
    with db_conn() as con:
        cur = con.cursor()
        if email:
            cur.execute("SELECT id FROM candidates WHERE LOWER(email)=LOWER(?)", (email,))
            hit = cur.fetchone()
            if hit:
                cid = hit[0]
 cur.execute("""
                    UPDATE candidates SET
                        name=?, phone=?, county=?, availability=?, source=?, completion_time=?, notes=?, campaign=?,
                        is_test=CASE WHEN ?=1 THEN 1 ELSE COALESCE(is_test,0) END,
                        updated_at=?
                    WHERE id=?
                """, (name, phone, row.get("county"), row.get("availability"), row.get("source"),
                      row.get("completion_time"), row.get("notes"), row.get("campaign"),
                      int(is_test), now, cid))
                return cid, "updated(email)"
        if name and phone:
            cur.execute("SELECT id FROM candidates WHERE LOWER(name)=LOWER(?) AND phone=?", (name, phone))
            hit = cur.fetchone()
            if hit:
                cid = hit[0]
                   cur.execute("""
                    UPDATE candidates SET
                        email=?, county=?, availability=?, source=?, completion_time=?, notes=?, campaign=?,
                        is_test=CASE WHEN ?=1 THEN 1 ELSE COALESCE(is_test,0) END,
                        updated_at=?
                    WHERE id=?
                """, (email, row.get("county"), row.get("availability"), row.get("source"),
                      row.get("completion_time"), row.get("notes"), row.get("campaign"),
                      int(is_test), now, cid))
                return cid, "updated(name+phone)"
              cur.execute("""
            INSERT INTO candidates (
                email, name, phone, county, availability, source, completion_time, notes,
                status, last_attempt, interview_dt, campaign,
                created_at, updated_at, dnc, is_test
            )
            VALUES (?,?,?,?,?,?,?,?, 'New','', '', ?, ?, ?, 0, ?)
        """, (email, name, phone, row.get("county"), row.get("availability"), row.get("source"),
              row.get("completion_time"), row.get("notes"), row.get("campaign"), now, now, int(is_test)))

        return cur.lastrowid, "inserted"

def update_candidate_fields(row_id: int, fields: Dict[str, Any]):
    keys = []
    vals = []
    for k, v in fields.items():
        keys.append(f"{k}=?")
        vals.append(v)
    keys.append("updated_at=?")
    vals.append(datetime.utcnow().isoformat())
    vals.append(row_id)
    with db_conn() as con:
        con.execute(f"UPDATE candidates SET {', '.join(keys)} WHERE id=?", vals)

def list_candidates(status: Optional[List[str]]=None, campaign: Optional[str]=None, search: str="", exclude_dnc: bool=True):
    sql = "SELECT id, name, email, phone, county, availability, source, status, last_attempt, interview_dt, notes, campaign FROM candidates"
    clauses = []
    params = []
    if exclude_dnc:
        clauses.append("dnc=0")
    if status:
        placeholders = ",".join(["?"]*len(status))
        clauses.append(f"status IN ({placeholders})")
        params.extend(status)
    if campaign:
        clauses.append("campaign=?")
        params.append(campaign)
    if search:
        q = f"%{search.lower()}%"
        clauses.append("(LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR phone LIKE ?)")
        params.extend([q, q, search])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY updated_at DESC, created_at DESC"
    with db_conn() as con:
        return pd.read_sql_query(sql, con, params=params)

def get_candidate(cid: int):
    with db_conn() as con:
        row = con.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
        if not row: return None
        cols = [c[0] for c in con.execute("PRAGMA table_info(candidates)").fetchall()]
    return dict(zip([c[1] for c in con.execute("PRAGMA table_info(candidates)")] , row))

def list_attachments(cid: int):
    with db_conn() as con:
        return pd.read_sql_query("SELECT id, filename, path, uploaded_at FROM attachments WHERE candidate_id=? ORDER BY uploaded_at DESC", con, params=(cid,))

def add_attachment(cid: int, file_name: str, file_bytes: bytes):
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = f"{cid}_{ts}_{re.sub(r'[^A-Za-z0-9_.-]', '_', file_name)}"
    path = os.path.join(UPLOAD_DIR, safe_name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    with db_conn() as con:
        con.execute("INSERT INTO attachments (candidate_id, filename, path, uploaded_at) VALUES (?,?,?,?)",
                    (cid, file_name, path, datetime.utcnow().isoformat()))

def add_campaign(name: str, hours: str, req_text: str, need_wknd: bool, need_eve: bool, need_wkd: bool, remote_ok: bool):
    now = datetime.utcnow().isoformat()
    with db_conn() as con:
        con.execute("""
        INSERT OR IGNORE INTO campaigns (name, hours, requirements_text, req_need_weekends, req_need_evenings, req_need_weekdays, req_remote_ok, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (name, hours, req_text, int(need_wknd), int(need_eve), int(need_wkd), int(remote_ok), now, now))
        con.execute("""
        UPDATE campaigns SET hours=?, requirements_text=?, req_need_weekends=?, req_need_evenings=?, req_need_weekdays=?, req_remote_ok=?, updated_at=?
        WHERE name=?
        """, (hours, req_text, int(need_wknd), int(need_eve), int(need_wkd), int(remote_ok), now, name))

def list_campaigns():
    with db_conn() as con:
        return pd.read_sql_query("SELECT id, name, hours, requirements_text, req_need_weekends, req_need_evenings, req_need_weekdays, req_remote_ok FROM campaigns ORDER BY name", con)

def add_drive(campaign_id: int, start_date: date, cutoff_date: date, fte_target: int, notes: str):
    now = datetime.utcnow().isoformat()
    with db_conn() as con:
        con.execute("""
        INSERT INTO drives (campaign_id, start_date, cutoff_date, fte_target, notes, created_at, updated_at)
        VALUES (?,?,?,?,?, ?, ?)
        """, (campaign_id, str(start_date), str(cutoff_date), int(fte_target), notes, now, now))

def list_drives(campaign_id: Optional[int]=None):
    sql = """SELECT d.id, c.name as campaign, d.start_date, d.cutoff_date, d.fte_target, d.notes
             FROM drives d JOIN campaigns c ON c.id=d.campaign_id"""
    params = []
    if campaign_id:
        sql += " WHERE d.campaign_id=?"
        params.append(campaign_id)
    sql += " ORDER BY d.start_date DESC"
    with db_conn() as con:
        return pd.read_sql_query(sql, con, params=params)

def ingest_forms(up_df: pd.DataFrame, field_map: Dict[str,str], campaign_name: str, is_test: int = 0) -> Dict[str,int]:
    detected = 0
    inserted = 0
    updated = 0
    for _, r in up_df.iterrows():
        row = {
            "name": r.get(field_map.get("candidate_name"), ""),
            "email": r.get(field_map.get("email"), ""),
            "phone": r.get(field_map.get("phone"), ""),
            "county": r.get(field_map.get("county"), ""),
            "availability": r.get(field_map.get("availability"), ""),
            "source": r.get(field_map.get("source"), ""),
            "completion_time": r.get(field_map.get("completion_time"), ""),
            "notes": r.get(field_map.get("notes"), ""),
            "campaign": campaign_name,
        }
           cid, action = upsert_candidate(row, is_test=is_test)
        detected += 1
        if action.startswith("inserted"):
            inserted += 1
        else:
            updated += 1
    return {"rows_seen": detected, "inserted": inserted, "updated": updated}

# Initialize DB
db_init()

# --------- Sidebar navigation ---------
st.sidebar.title("PSR Portal")
page = st.sidebar.radio("Go to", ["Dashboard","Campaigns","Recruitment Drives","Candidates","Do Not Call"])

# --------- Dashboard ---------
if page == "Dashboard":
    st.title("Dashboard")
    st.write("Quick counts")
    with db_conn() as con:
        total = con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        new = con.execute("SELECT COUNT(*) FROM candidates WHERE status='New' AND dnc=0").fetchone()[0]
        interviewed = con.execute("SELECT COUNT(*) FROM candidates WHERE status='Interviewed'").fetchone()[0]
        rejected = con.execute("SELECT COUNT(*) FROM candidates WHERE status='Rejected'").fetchone()[0]
        hired = con.execute("SELECT COUNT(*) FROM candidates WHERE status='Hired'").fetchone()[0]
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total candidates", total)
    c2.metric("New", new)
    c3.metric("Interviewed", interviewed)
    c4.metric("Rejected", rejected)
    c5.metric("Hired", hired)

# --------- Campaigns ---------
elif page == "Campaigns":
    st.title("Campaigns")
    st.write("Create or update campaigns once, then reuse them for drives.")
    with st.form("campaign_form", clear_on_submit=False):
        name = st.text_input("Campaign name *")
        hours = st.text_area("Hours of operation")
        req_text = st.text_area("Requirements (free text)")
        cols = st.columns(4)
        need_wknd = cols[0].checkbox("Requires weekends")
        need_eve = cols[1].checkbox("Requires evenings")
        need_wkd = cols[2].checkbox("Requires weekdays")
        remote_ok = cols[3].checkbox("Remote acceptable", value=True)
        submit = st.form_submit_button("Save campaign")
        if submit and name.strip():
            add_campaign(name.strip(), hours, req_text, need_wknd, need_eve, need_wkd, remote_ok)
            st.success("Campaign saved.")
    st.subheader("Existing campaigns")
    st.dataframe(list_campaigns(), use_container_width=True)

# --------- Recruitment Drives ---------
elif page == "Recruitment Drives":
    st.title("Recruitment Drives")
    camps = list_campaigns()
    if camps.empty:
        st.info("Create a campaign first in the Campaigns tab.")
    else:
        camp_names = dict(zip(camps["name"], camps["id"]))
        chosen = st.selectbox("Campaign", list(camp_names.keys()))
        start = st.date_input("Start date", value=date.today())
        cutoff = st.date_input("Cutoff date", value=date.today())
        fte = st.number_input("FTE target", min_value=0, step=1, value=0)
        notes = st.text_area("Notes (optional)")
        if st.button("Add drive"):
            add_drive(camp_names[chosen], start, cutoff, fte, notes)
            st.success("Drive added.")
        st.subheader("Recent drives for this campaign")
        st.dataframe(list_drives(camp_names[chosen]), use_container_width=True)

# --------- Candidates ---------
elif page == "Candidates":
    st.title("Candidates")
    st.caption("Upload MS Forms Excel; de-duplicate and persist. Then filter, bulk email, and click a candidate to open their file.")
    with st.expander("Upload & Ingest", expanded=False):
        up_file = st.file_uploader("Upload MS Forms Excel (.xlsx)", type=["xlsx"])
        if up_file is not None:
            try:
                up_df = pd.read_excel(up_file)
                st.success(f"Loaded {len(up_df)} rows.")
                  mark_as_test = st.checkbox("Mark this upload as test data")
                detected = autodetect_columns(up_df)
                st.write("Column mapping:")
                field_map = {}
                map_cols = [("candidate_name","Full name"),("email","Email"),("phone","Phone"),("county","County/Location"),
                            ("availability","Availability"),("completion_time","Completion time"),("source","Source"),("notes","Notes")]
                for key, label in map_cols:
                    options = ["-- none --"] + list(up_df.columns)
                    default = detected.get(key) if detected.get(key) in up_df.columns else "-- none --"
                    field_map[key] = st.selectbox(label, options, index=options.index(default) if default in options else 0, key=f"map_{key}")
                    if field_map[key] == "-- none --":
                        field_map[key] = None
                campaign_name = st.text_input("Apply to campaign (optional)", value="")
                if st.button("Ingest & De-duplicate"):
                    res = ingest_forms(up_df, field_map, campaign_name, is_test=int(mark_as_test))
                    st.success(f"Ingested {res['rows_seen']} rows | Inserted {res['inserted']} | Updated {res['updated']}")
            except Exception as e:
                st.error(f"Error reading Excel: {e}")
    # Filters + table
    colf1, colf2, colf3, colf4 = st.columns([2,2,3,2])
    status_filter = colf1.multiselect("Status", STATUSES, default=["New","Called","No Answer","Voicemail","Interviewed"])
    camp_filter = colf2.text_input("Campaign contains")
    search_text = colf3.text_input("Search name/email/phone")
    exclude_dnc = colf4.checkbox("Exclude DNC", value=True)
    df = list_candidates(status=status_filter, campaign=camp_filter if camp_filter.strip() else None, search=search_text.strip(), exclude_dnc=exclude_dnc)
    st.dataframe(df, use_container_width=True, height=400)
    # Bulk email
    st.subheader("Bulk Emails")
    emails = df["email"].dropna().unique().tolist()
    sep = st.radio("Delimiter", [", ", "; ", " "], horizontal=True, index=0)
    st.text_area("Copy-paste emails", value=sep.join(emails), height=100)

    # Candidate file
    st.subheader("Candidate File")
    if not df.empty:
        cid = st.selectbox("Pick a candidate", df["id"].tolist(), format_func=lambda i: f"{df.loc[df['id']==i, 'name'].values[0]} — {df.loc[df['id']==i, 'email'].values[0]}")
        with db_conn() as con:
            row = con.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
            cols = [c[1] for c in con.execute("PRAGMA table_info(candidates)").fetchall()]
        cand = dict(zip(cols, row))
        # Display and edit
        c1, c2 = st.columns([2,3])
        with c1:
            st.write(f"**Name:** {cand.get('name','')}")
            st.write(f"**Email:** {cand.get('email','')}")
            st.write(f"**Phone:** {cand.get('phone','')}")
            st.write(f"**County:** {cand.get('county','')}")
            st.write(f"**Availability:** {cand.get('availability','')}")
            st.write(f"**Source:** {cand.get('source','')}")
            new_status = st.selectbox("Status", STATUSES, index=STATUSES.index(cand.get("status","New")) if cand.get("status","New") in STATUSES else 0)
            last_attempt = st.text_input("Last attempt", value=cand.get("last_attempt","") or "")
            interview_dt = st.text_input("Interview date/time (YYYY-MM-DD HH:MM)", value=cand.get("interview_dt","") or "")
            notes = st.text_area("Notes", value=cand.get("notes","") or "", height=120)
            dnc_flag = st.checkbox("Do Not Call", value=bool(cand.get("dnc",0)))
            if st.button("Save changes"):
                update_candidate_fields(cid, {"status": new_status, "last_attempt": last_attempt, "interview_dt": interview_dt, "notes": notes, "dnc": int(dnc_flag)})
                st.success("Saved.")
        with c2:
            st.write("**Attachments**")
            at_df = list_attachments(cid)
            st.dataframe(at_df, use_container_width=True, height=200)
            up = st.file_uploader("Attach file to candidate", key="fileup", accept_multiple_files=False)
            if up is not None:
                add_attachment(cid, up.name, up.read())
                st.success("File attached. Re-select candidate to refresh.")
    else:
        st.info("No candidates match your filters yet.")

# --------- Do Not Call ---------
elif page == "Do Not Call":
    st.title("Do Not Call")
    with db_conn() as con:
        df = pd.read_sql_query("SELECT id, name, email, phone, reason, created_at FROM (SELECT c.id, c.name, c.email, c.phone, CASE WHEN c.dnc=1 THEN 'Flagged' ELSE '' END AS reason, c.updated_at AS created_at FROM candidates c WHERE dnc=1) ORDER BY created_at DESC", con)
    st.dataframe(df, use_container_width=True)

st.caption("PSR Recruitment Portal — data stored in portal.db; uploads saved under ./uploads")
