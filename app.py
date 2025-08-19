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
        # Settings: blocked counties
        con.execute("""
        CREATE TABLE IF NOT EXISTS blocked_counties (
            county TEXT PRIMARY KEY
        )""")
        # --- Migrations (safe each start)
        try:
            con.execute("ALTER TABLE candidates ADD COLUMN is_test INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            con.execute("ALTER TABLE candidates ADD COLUMN dnc_reason TEXT")
        except Exception:
            pass
        try:
            con.execute("ALTER TABLE candidates ADD COLUMN dnc_override INTEGER DEFAULT 0")
        except Exception:
            pass
        # Seed initial blocked counties if empty
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM blocked_counties")
        if cur.fetchone()[0] == 0:
            initial = [
                "Cavan","Cork","Galway","Leitrim","Donegal","Longford",
                "Louth","Monaghan","Mayo","Roscommon","Sligo","Dublin"
            ]
            cur.executemany("INSERT OR IGNORE INTO blocked_counties(county) VALUES (?)", [(c,) for c in initial])

# ------------ Blocked counties helpers ------------
def get_blocked_counties() -> List[str]:
    with db_conn() as con:
        rows = con.execute("SELECT county FROM blocked_counties ORDER BY county").fetchall()
    return [r[0] for r in rows]

def set_blocked_counties(counties: List[str]):
    with db_conn() as con:
        con.execute("DELETE FROM blocked_counties")
        con.executemany("INSERT OR IGNORE INTO blocked_counties(county) VALUES (?)", [(sstrip(c),) for c in counties if sstrip(c)])

def apply_blocked_counties_to_candidates() -> int:
    blocked = [c.lower() for c in get_blocked_counties()]
    if not blocked:
        return 0
    placeholders = ",".join(["?"] * len(blocked))
    sql = f"""
    UPDATE candidates
       SET dnc=1,
           dnc_reason=CASE WHEN dnc_override=1 THEN dnc_reason ELSE 'outside of hiring area' END
     WHERE LOWER(county) IN ({placeholders})
       AND dnc_override=0
    """
    with db_conn() as con:
        cur = con.cursor()
        cur.execute(sql, blocked)
        return cur.rowcount

# ------------ Column autodetect ------------
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

# ------------ Candidate data helpers ------------
def upsert_candidate(row: Dict[str, Any], is_test: int = 0):
    now = datetime.utcnow().isoformat()
    email  = sstrip(row.get("email"))
    name   = sstrip(row.get("name"))
    phone  = sstrip(row.get("phone"))
    county = sstrip(row.get("county"))

    blocked = [c.lower() for c in get_blocked_counties()]
    is_blocked = county.lower() in blocked if county else False

    with db_conn() as con:
        cur = con.cursor()
        if email:
            cur.execute("SELECT id, dnc_override FROM candidates WHERE LOWER(email)=LOWER(?)", (email,))
            hit = cur.fetchone()
            if hit:
                cid, override = hit
                auto_cols = ""
                auto_vals: List[Any] = []
                if is_blocked and (override or 0) == 0:
                    auto_cols = ", dnc=?, dnc_reason=?"
                    auto_vals = [1, "outside of hiring area"]
                cur.execute(f"""
                    UPDATE candidates SET
                        name=?, phone=?, county=?, availability=?, source=?, completion_time=?, notes=?, campaign=?,
                        is_test=CASE WHEN ?=1 THEN 1 ELSE COALESCE(is_test,0) END
                        {auto_cols},
                        updated_at=?
                    WHERE id=?
                """, (name, phone, county, sstrip(row.get("availability")), sstrip(row.get("source")),
                      sstrip(row.get("completion_time")), sstrip(row.get("notes")), sstrip(row.get("campaign")),
                      int(is_test), *auto_vals, now, cid))
                return cid, "updated(email)"
        if name and phone:
            cur.execute("SELECT id, dnc_override FROM candidates WHERE LOWER(name)=LOWER(?) AND phone=?", (name, phone))
            hit = cur.fetchone()
            if hit:
                cid, override = hit
                auto_cols = ""
                auto_vals = []
                if is_blocked and (override or 0) == 0:
                    auto_cols = ", dnc=?, dnc_reason=?"
                    auto_vals = [1, "outside of hiring area"]
                cur.execute(f"""
                    UPDATE candidates SET
                        email=?, county=?, availability=?, source=?, completion_time=?, notes=?, campaign=?,
                        is_test=CASE WHEN ?=1 THEN 1 ELSE COALESCE(is_test,0) END
                        {auto_cols},
                        updated_at=?
                    WHERE id=?
                """, (email, county, sstrip(row.get("availability")), sstrip(row.get("source")),
                      sstrip(row.get("completion_time")), sstrip(row.get("notes")), sstrip(row.get("campaign")),
                      int(is_test), *auto_vals, now, cid))
                return cid, "updated(name+phone)"
        # Insert new
        dnc_val = 1 if is_blocked else 0
        dnc_reason = "outside of hiring area" if is_blocked else None
        cur.execute("""
            INSERT INTO candidates (
                email, name, phone, county, availability, source, completion_time, notes,
                status, last_attempt, interview_dt, campaign,
                created_at, updated_at, dnc, is_test, dnc_reason, dnc_override
            )
            VALUES (?,?,?,?,?,?,?,?, 'New','', '', ?, ?, ?, ?, ?, ?, 0)
        """, (email, name, phone, county, sstrip(row.get("availability")), sstrip(row.get("source")),
              sstrip(row.get("completion_time")), sstrip(row.get("notes")), sstrip(row.get("campaign")),
              now, now, dnc_val, int(is_test), dnc_reason))
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

def list_dnc():
    with db_conn() as con:
        return pd.read_sql_query(
            "SELECT id, name, email, phone, county, dnc_reason, updated_at FROM candidates WHERE dnc=1 ORDER BY updated_at DESC",
            con
        )

def restore_from_dnc(cid: int):
    update_candidate_fields(cid, {"dnc": 0, "dnc_reason": None})

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
            "name":            sstrip(r.get(field_map.get("candidate_name"))   if field_map.get("candidate_name")   else ""),
            "email":           sstrip(r.get(field_map.get("email"))            if field_map.get("email")            else ""),
            "phone":           sstrip(r.get(field_map.get("phone"))            if field_map.get("phone")            else ""),
            "county":          sstrip(r.get(field_map.get("county"))           if field_map.get("county")           else ""),
            "availability":    sstrip(r.get(field_map.get("availability"))     if field_map.get("availability")     else ""),
            "source":          sstrip(r.get(field_map.get("source"))           if field_map.get("source")           else ""),
            "completion_time": sstrip(r.get(field_map.get("completion_time"))  if field_map.get("completion_time")  else ""),
            "notes":           sstrip(r.get(field_map.get("notes"))            if field_map.get("notes")            else ""),
            "campaign":        sstrip(campaign_name),
        }
        _, action = upsert_candidate(row, is_test=is_test)
        detected += 1
        if action.startswith("inserted"):
            inserted += 1
        else:
            updated += 1
    return {"rows_seen": detected, "inserted": inserted, "updated": updated}

# ------------ Init ------------
db_init()

# ------------ Sidebar nav ------------
st.sidebar.title("PSR Portal")
page = st.sidebar.radio(
    "Go to",
    ["Dashboard","Campaigns","Recruitment Drives","Candidates","Do Not Call","Hiring Areas","Changelog"]
)

# ------------ Pages ------------
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
    df = list_candidates(status=status_filter, campaign=camp_filter if camp_filter.strip() else None,
                         search=search_text.strip(), exclude_dnc=exclude_dnc)
    st.dataframe(df, use_container_width=True, height=400)

    # Bulk email
    st.subheader("Bulk Emails")
    emails = df["email"].dropna().unique().tolist()
    sep = st.radio("Delimiter", [", ", "; ", " "], horizontal=True, index=0)
    st.text_area("Copy-paste emails", value=sep.join(emails), height=100)

    # Candidate file
    st.subheader("Candidate File")
    if not df.empty:
        cid = st.selectbox("Pick a candidate", df["id"].tolist(),
                           format_func=lambda i: f"{df.loc[df['id']==i, 'name'].values[0]} — {df.loc[df['id']==i, 'email'].values[0]}")
        with db_conn() as con:
            row = con.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
            cols = [c[1] for c in con.execute("PRAGMA table_info(candidates)").fetchall()]
        cand = dict(zip(cols, row))
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
            dnc_reason = st.text_input("DNC reason", value=cand.get("dnc_reason","") or "")
            override = st.checkbox("Protect from auto-DNC (exception)", value=bool(cand.get("dnc_override",0)))
            if st.button("Save changes"):
                fields = {
                    "status": new_status,
                    "last_attempt": last_attempt,
                    "interview_dt": interview_dt,
                    "notes": notes,
                    "dnc": int(dnc_flag),
                    "dnc_reason": (dnc_reason if dnc_flag else None),
                    "dnc_override": int(override),
                }
                update_candidate_fields(cid, fields)
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

elif page == "Do Not Call":
    st.title("Do Not Call")
    dnc_df = list_dnc()
    st.dataframe(dnc_df, use_container_width=True)
    if not dnc_df.empty:
        cid_restore = st.selectbox("Restore candidate (choose ID)", dnc_df["id"].tolist())
        reason_show = dnc_df.loc[dnc_df["id"]==cid_restore, "dnc_reason"].values[0]
        st.caption(f"Reason: {reason_show or '(none)'}")
        if st.button("Restore to active (remove DNC)"):
            restore_from_dnc(int(cid_restore))
            st.success("Candidate restored to active.")
            st.experimental_rerun()

elif page == "Hiring Areas":
    st.title("Hiring Areas")
    st.caption("Maintain the list of counties we do NOT hire from. New ingests will auto-flag DNC with reason 'outside of hiring area'.")
    current = get_blocked_counties()
    left, right = st.columns(2)
    with left:
        st.subheader("Blocked counties")
        st.write(", ".join(current) if current else "None")
        text = st.text_area("Edit list (one county per line)", value="\n".join(current), height=240)
        if st.button("Save blocked counties"):
            updated = [line.strip() for line in text.splitlines() if line.strip()]
            set_blocked_counties(updated)
            st.success("Blocked counties updated.")
    with right:
        st.subheader("Apply rule to existing candidates")
        st.caption("Flags candidates whose county is in the list (unless protected by override).")
        if st.button("Apply now"):
            changed = apply_blocked_counties_to_candidates()
            st.success(f"Updated {changed} candidate(s).")

elif page == "Changelog":
    st.title("Changelog")
    st.caption(f"Current version: v{VERSION}")
    entries = list(reversed(CHANGELOG))
    for (ver, when, summary, details) in entries:
        with st.expander(f"v{ver} — {when} · {summary}", expanded=(ver == VERSION)):
            st.write(details)

st.caption("PSR Recruitment Portal — data stored in portal.db; uploads saved under ./uploads")
