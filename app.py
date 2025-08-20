# app.py — PulseHire full app per spec
import os, io, json
from datetime import datetime, date
import pandas as pd
import streamlit as st

from db import init_db, connect, get_setting, set_setting
from auth import seed_admin_if_empty, verify_password, create_user
from theme import inject_css, BRAND
from scoring import SEED_KEYWORDS, extract_text, score_cv
from ingestion import import_testgorilla, import_interview_notes, save_attachment
from utils import subtract_workdays, apply_dnc_blocked_counties

APP_VERSION = "0.1.0"

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

st.set_page_config(page_title="PulseHire", layout="wide")

# Init DB + seed admin if needed
init_db()
seed_admin_if_empty()

# Theme toggle
if "theme_dark" not in st.session_state:
    st.session_state["theme_dark"] = True
inject_css(st, dark=st.session_state["theme_dark"])

# Auth
def login_ui():
    st.image(BRAND["logo_path"], width=140) if os.path.exists(BRAND["logo_path"]) else None
    st.markdown(f"## {BRAND['name']}")
    st.caption("Login with your email and password")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Sign in", type="primary", use_container_width=True):
        user = verify_password(email, password)
        if user:
            st.session_state["user"] = user.__dict__
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.divider()
    st.caption("First-time admin? Default user is **admin@pulsehire.local / admin** — change it after login.")

def require_role(allowed):
    user = st.session_state.get("user")
    return user and user.get("role") in allowed

# Header
def app_header():
    cols = st.columns([0.08, 0.62, 0.30])
    with cols[0]:
        if os.path.exists(BRAND["logo_path"]):
            st.image(BRAND["logo_path"])
    with cols[1]:
        st.markdown(f"### {BRAND['name']}")
    with cols[2]:
        d = st.toggle("🌙 Dark mode", value=st.session_state["theme_dark"])
        if d != st.session_state["theme_dark"]:
            st.session_state["theme_dark"] = d
            st.rerun()
        user = st.session_state.get("user")
        if user:
            st.write(f"**{user['name']}** · {user['role'].title()}")
            if st.button("Sign out"):
                st.session_state.pop("user", None)
                st.rerun()

# Sidebar nav (RBAC-aware)
PAGES = ["Dashboard","Campaigns","Active recruitment","Candidates","Do Not Call","Keywords","Hiring Areas","Compliance","Changelog"]

def sidebar_nav():
    st.sidebar.markdown("### Navigation")
    page = st.sidebar.radio("", PAGES, index=3)
    if require_role(["admin"]):
        with st.sidebar.expander("Admin"):
            if st.button("Create user (demo)"):
                with st.form("new_user"):
                    email = st.text_input("Email")
                    name  = st.text_input("Name")
                    role  = st.selectbox("Role", ["admin","recruiter","hr","viewer"])
                    pw    = st.text_input("Password", type="password")
                    if st.form_submit_button("Create"):
                        try:
                            create_user(email, name, role, pw)
                            st.success("User created.")
                        except Exception as e:
                            st.error(str(e))
    return page

# === Pages ===

def page_dashboard():
    st.subheader("Dashboard")
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) c FROM candidates"); c = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) d FROM candidates WHERE dnc=1"); d = cur.fetchone()["d"]
        cur.execute("SELECT COUNT(*) a FROM active_recruitment WHERE is_active=1"); a = cur.fetchone()["a"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Candidates", c)
    c2.metric("Do Not Call", d)
    c3.metric("Active recruitment", a)
    st.caption("More dashboards can be added later (coverage, shifts, etc.).")

def page_campaigns():
    st.subheader("Campaigns")
    with connect() as con:
        cur = con.cursor()
        with st.form("new_campaign"):
            name = st.text_input("Name")
            reqs = st.text_area("Requirements (text)")
            notes = st.text_area("Hours / notes")
            c1, c2, c3, c4 = st.columns(4)
            weekends = c1.checkbox("Needs weekends", False)
            evenings = c2.checkbox("Needs evenings", False)
            weekdays = c3.checkbox("Needs weekdays", True)
            remote_ok = c4.checkbox("Remote OK", False)
            if st.form_submit_button("Add campaign"):
                cur.execute("""INSERT INTO campaigns(name,requirements_text,hours_notes,
                             req_need_weekends,req_need_evenings,req_need_weekdays,req_remote_ok,created_at,updated_at)
                             VALUES(?,?,?,?,?,?,?,datetime('now'),datetime('now'))""",
                            (name, reqs, notes, int(weekends), int(evenings), int(weekdays), int(remote_ok)))
                st.success("Campaign created")
    with connect() as con:
        df = pd.read_sql_query("SELECT * FROM campaigns", con)
    st.dataframe(df, use_container_width=True)

def page_active_recruitment():
    st.subheader("Active recruitment")
    with connect() as con:
        cur = con.cursor()
        # Create
        with st.form("new_active"):
            cur.execute("SELECT id,name FROM campaigns ORDER BY name")
            rows = cur.fetchall()
            campaign_map = {r["name"]: r["id"] for r in rows}
            camp_name = st.selectbox("Campaign", list(campaign_map.keys()) if campaign_map else [])
            start = st.date_input("Start date", value=date.today())
            cutoff_default = subtract_workdays(start, 7)
            cutoff = st.date_input("Cutoff date", value=cutoff_default)
            notes = st.text_area("Notes", "")
            if st.form_submit_button("Start"):
                cur.execute("""INSERT INTO active_recruitment(campaign_id,start_date,cutoff_date,notes,is_active,created_at,updated_at)
                               VALUES(?,?,?,?,1,datetime('now'),datetime('now'))""",
                            (campaign_map[camp_name], start.isoformat(), cutoff.isoformat(), notes))
                st.success("Active recruitment started.")

    with connect() as con:
        df = pd.read_sql_query("""SELECT a.id, c.name as campaign, a.start_date, a.cutoff_date, a.is_active, a.notes
                                  FROM active_recruitment a JOIN campaigns c ON a.campaign_id=c.id
                                  ORDER BY a.id DESC""", con)
    st.dataframe(df, use_container_width=True)
    if not df.empty:
        ids = df["id"].tolist()
        sel = st.selectbox("Select to deactivate", ids)
        if st.button("Deactivate"):
            with connect() as con:
                con.execute("UPDATE active_recruitment SET is_active=0, updated_at=datetime('now') WHERE id=?", (int(sel),))
            st.success("Deactivated.")
            st.rerun()

def _candidate_filters_ui():
    cols = st.columns(5)
    with cols[0]:
        status = st.selectbox("Status", ["(any)","Applied","Interviewed","Hired","Rejected"])
    with cols[1]:
        tier = st.selectbox("Score tier", ["(any)","High","Medium","Low"])
    with cols[2]:
        dnc = st.selectbox("DNC", ["(any)","Yes","No"])
    with cols[3]:
        test_min = st.number_input("TestGorilla % ≥", 0, 100, 0)
    with cols[4]:
        test_name = st.text_input("Test name contains")
    q = st.text_input("Search name/email/phone")
    return {"status":status, "tier":tier, "dnc":dnc, "test_min":test_min, "test_name":test_name, "q":q}

def page_candidates():
    st.subheader("Candidates")

    # Ingest actions
    with st.expander("Ingest files"):
        c1, c2 = st.columns(2)
        with c1:
            tg = st.file_uploader("TestGorilla Excel (.xlsx)", type=["xlsx"], key="tg")
            if tg and st.button("Import TestGorilla"):
                num = import_testgorilla(tg)
                st.success(f"Imported {num} scores.")
        with c2:
            iv = st.file_uploader("Interview Notes (MS Forms) .xlsx", type=["xlsx"], key="iv")
            if iv and st.button("Import Interview Notes"):
                num = import_interview_notes(iv, UPLOAD_DIR)
                st.success(f"Processed {num} interview note rows.")

    # Filters
    f = _candidate_filters_ui()

    # Fetch + filter
    with connect() as con:
        base = "SELECT * FROM candidates"
        df = pd.read_sql_query(base, con)
    if f["status"] != "(any)":
        df = df[df["status"]==f["status"]]
    if f["tier"] != "(any)":
        df = df[df["score_tier"]==f["tier"]]
    if f["dnc"] != "(any)":
        df = df[df["dnc"] == (1 if f["dnc"]=="Yes" else 0)]
    if f["q"]:
        ql = f["q"].strip().lower()
        df = df[df.apply(lambda r: ql in (str(r["name"]).lower() if r["name"] else "") or
                                   ql in (str(r["email"]).lower() if r["email"] else "") or
                                   ql in (str(r["phone"]).lower() if r["phone"] else ""), axis=1)]

    # Left sidebar picker (alphabetical)
    names = df.sort_values("name", na_position="last")["name"].fillna("—").tolist()
    ids = df.sort_values("name", na_position="last")["id"].tolist()
    pick = st.selectbox("Candidate picker (A–Z)", [f"{n} (#{i})" for n,i in zip(names, ids)]) if ids else None
    selected_id = int(pick.split("#")[-1].rstrip(")")) if pick else None

    # Bulk actions
    if not df.empty:
        st.markdown("### Bulk actions")
        sel = st.multiselect("Select candidate IDs", df["id"].tolist())
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("Bulk DNC"):
                with connect() as con:
                    for cid in sel: con.execute("UPDATE candidates SET dnc=1, dnc_reason='Manual', updated_at=datetime('now') WHERE id=?", (cid,))
                st.success("Bulk DNC applied.")
        with b2:
            if st.button("Bulk un-DNC"):
                with connect() as con:
                    for cid in sel: con.execute("UPDATE candidates SET dnc=0, dnc_reason=NULL, updated_at=datetime('now') WHERE id=?", (cid,))
                st.success("Restored from DNC.")
        with b3:
            camp = st.text_input("Assign campaign (name)")
            if st.button("Bulk assign campaign") and camp:
                with connect() as con:
                    for cid in sel: con.execute("UPDATE candidates SET campaign=?, updated_at=datetime('now') WHERE id=?", (camp, cid))
                st.success("Campaign assigned.")

    st.markdown("### Candidate table")
    st.dataframe(df[["id","name","email","phone","county","status","score_tier","dnc"]], use_container_width=True, height=400)

    # Candidate file view
    if selected_id:
        render_candidate_file(selected_id)

def render_candidate_file(cid: int):
    st.markdown("---")
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM candidates WHERE id=?", (cid,))
        cand = cur.fetchone()
    if not cand:
        st.warning("Candidate not found.")
        return

    # Sticky header
    left, right = st.columns([0.7, 0.3])
    with left:
        st.markdown(f"### {cand['name'] or '—'}")
        chips = []
        if cand["score_tier"]:
            chips.append(("Tier", cand["score_tier"]))
        flags = json.loads(cand["flags_json"]) if cand["flags_json"] else {}
        if flags.get("reliability_caution"): chips.append(("Reliability", "Caution"))
        if flags.get("previous_employee"): chips.append(("HR clearance", "Required"))
        if flags.get("call_centre_inferred"): chips.append(("Call centre exp", "Inferred"))
        for k,v in chips:
            st.markdown(f"<span class='chip' style='background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,.12)'>{k}: <b>{v}</b></span> ", unsafe_allow_html=True)
    with right:
        st.write(cand["email"] or "—")
        st.write(cand["phone"] or "—")
        st.write(f"Status: **{cand['status'] or '—'}**")
        st.write(f"DNC: **{'Yes' if cand['dnc'] else 'No'}** — {cand['dnc_reason'] or ''}")

    tabs = st.tabs(["Details","CV","TestGorilla","Interview Notes","Attachments","Notes","Audit Trail","Compliance"])

    with tabs[0]:
        c1, c2, c3 = st.columns(3)
        c1.write(f"County: {cand['county'] or '—'}")
        c2.write(f"Availability: {cand['availability'] or '—'}")
        c3.write(f"Source: {cand['source'] or '—'}")
        c1.write(f"Notice period: {cand['notice_period'] or '—'}")
        c2.write(f"Leave: {cand['planned_leave'] or '—'}")
        st.text_area("Notes", value=cand["notes"] or "", key=f"notes_{cid}")
        if st.button("Save notes"):
            with connect() as con:
                con.execute("UPDATE candidates SET notes=?, updated_at=datetime('now') WHERE id=?",
                            (st.session_state[f"notes_{cid}"], cid))
            st.success("Notes saved.")

    with tabs[1]:
        st.write("Upload CV (PDF/DOCX/TXT) to (re)score:")
        cv = st.file_uploader("CV", type=["pdf","docx","txt"], key=f"cv_{cid}")
        if cv and st.button("Upload & score"):
            text = extract_text(cv)
            # store CV as attachment
            save_attachment(cid, f"cv_{cid}_{cv.name}", cv.read(), "CV", UPLOAD_DIR)
            # (re)score
            keywords = get_setting("keywords", SEED_KEYWORDS)
            tier, flags = score_cv(text, keywords)
            with connect() as con:
                con.execute("UPDATE candidates SET score_tier=?, flags_json=?, updated_at=datetime('now') WHERE id=?",
                            (tier, json.dumps(flags), cid))
            st.success(f"Scored: **{tier}** ({flags.get('score_pct')}%)")
            st.experimental_rerun()

        # show current tier/flags
        st.write(f"Current tier: **{cand['score_tier'] or '—'}**")
        st.json(json.loads(cand["flags_json"]) if cand["flags_json"] else {})

    with tabs[2]:
        with connect() as con:
            df = pd.read_sql_query("SELECT provider, test_name, score_pct, imported_at FROM test_scores WHERE candidate_id=? ORDER BY imported_at DESC", con, params=(cid,))
        st.dataframe(df, use_container_width=True)

    with tabs[3]:
        st.write("Interview imports will attach a PDF automatically to the Attachments tab and set status to Interviewed.")

    with tabs[4]:
        # Upload any document
        up = st.file_uploader("Add attachment", type=None, key=f"att_{cid}")
        doc_type = st.selectbox("Doc type", ["CV","Visa","Speed Test","Interview Notes","Other"])
        if up and st.button("Upload attachment"):
            save_attachment(cid, up.name, up.read(), doc_type, UPLOAD_DIR)
            st.success("Attachment saved.")
            st.experimental_rerun()
        with connect() as con:
            df = pd.read_sql_query("SELECT id, filename, doc_type, uploaded_at, path FROM attachments WHERE candidate_id=? ORDER BY uploaded_at DESC", con, params=(cid,))
        st.dataframe(df.drop(columns=["path"]), use_container_width=True)

    with tabs[5]:
        st.write("Use the Details tab for main notes.")

    with tabs[6]:
        st.write("Audit trail placeholder (log actions on future iterations).")

    with tabs[7]:
        st.markdown("""
**Purpose**  
This portal stores and processes recruitment data to manage candidate pipelines for Your Company. It complies with GDPR and internal security standards.

**Lawful basis**  
Consent (where captured) and/or Legitimate Interests for recruitment.

**Data collected**  
Candidate identifiers; application responses; attachments (CV, visa, speed test, interview notes); assessments (TestGorilla); audit logs.

**Security & Access**  
Role-based access; audit logs; HTTPS; protected storage.

**Retention**  
Data retained **2 years**, auto-deleted weekly; manual **purge candidate** option; retention actions logged.

**Data subject rights**  
Access, rectification, erasure, restriction, objection, portability. Contact: privacy@yourcompany.com.

**Automated processing**  
Scoring is advisory only; **no automated rejection**.

**DNC / Exclusions**  
Do Not Call with reason; county-based auto-DNC with manual override; visa/campaign rules produce flags, not hard rejections.

*Last updated: 2025-08-20*
""")

def page_dnc():
    st.subheader("Do Not Call")
    with connect() as con:
        df = pd.read_sql_query("SELECT id,name,email,phone,county,dnc_reason FROM candidates WHERE dnc=1 ORDER BY name", con)
    st.dataframe(df, use_container_width=True)
    cid = st.number_input("Restore candidate id", min_value=1, step=1)
    if st.button("Restore"):
        with connect() as con:
            con.execute("UPDATE candidates SET dnc=0, dnc_reason=NULL WHERE id=?", (int(cid),))
        st.success("Restored from DNC.")

def page_keywords():
    st.subheader("Keywords (Global)")
    cur_kw = get_setting("keywords", SEED_KEYWORDS)
    tabs = st.tabs(list(cur_kw.keys()))
    for i, cat in enumerate(cur_kw.keys()):
        val = "\n".join(cur_kw[cat])
        new = tabs[i].text_area(cat, value=val, height=200, key=f"kw_{cat}")
        cur_kw[cat] = [w.strip() for w in new.splitlines() if w.strip()]
    if st.button("Save keywords"):
        set_setting("keywords", cur_kw)
        st.success("Saved.")
    if st.button("Reset to seed"):
        set_setting("keywords", SEED_KEYWORDS)
        st.success("Reset.")

def page_hiring_areas():
    st.subheader("Hiring Areas (Blocked counties)")
    with connect() as con:
        cur = con.cursor()
        add = st.text_input("Add county")
        if st.button("Add"):
            if add.strip():
                try:
                    cur.execute("INSERT OR IGNORE INTO blocked_counties(county) VALUES(?)", (add.strip(),))
                    st.success("Added.")
                except Exception as e:
                    st.error(str(e))
        with connect() as con2:
            df = pd.read_sql_query("SELECT county FROM blocked_counties ORDER BY county", con2)
    st.dataframe(df, use_container_width=True)
    if st.button("Apply rule to candidates"):
        n = apply_dnc_blocked_counties()
        st.success(f"Applied DNC to {n} candidate(s).")

def page_compliance():
    st.subheader("Compliance")
    st.markdown("""
**Purpose**  
This portal stores and processes recruitment data to manage candidate pipelines for Your Company. It complies with GDPR and internal security standards.

**Lawful basis**  
Consent (where captured) and/or Legitimate Interests for recruitment.

**Data collected**  
Candidate identifiers; application responses; attachments (CV, visa, speed test, interview notes); assessments (TestGorilla); audit logs.

**Security & Access**  
Role-based access; audit logs; HTTPS; protected storage.

**Retention**  
Data retained **2 years**, auto-deleted weekly; manual **purge candidate** option; retention actions logged.

**Data subject rights**  
Access, rectification, erasure, restriction, objection, portability. Contact: privacy@yourcompany.com.

**Automated processing**  
Scoring is advisory only; **no automated rejection**.

**DNC / Exclusions**  
Do Not Call with reason; county-based auto-DNC with manual override; visa/campaign rules produce flags, not hard rejections.

*Last updated: 2025-08-20*
""")

def page_changelog():
    st.subheader("Changelog")
    st.write(f"Version {APP_VERSION}")
    st.markdown("""
- Initial PulseHire build per spec
- RBAC + pages + ingestion + scoring
""")

# ===== App flow =====
if "user" not in st.session_state:
    login_ui()
else:
    app_header()
    page = sidebar_nav()

    # RBAC guards (simple: all pages accessible; enforce edits by role where applicable)
    if page == "Dashboard": page_dashboard()
    elif page == "Campaigns":
        if require_role(["admin","recruiter"]): page_campaigns()
        else: st.warning("Insufficient permissions.")
    elif page == "Active recruitment":
        if require_role(["admin","recruiter"]): page_active_recruitment()
        else: st.warning("Insufficient permissions.")
    elif page == "Candidates":
        if require_role(["admin","recruiter","hr","viewer"]): page_candidates()
        else: st.warning("Insufficient permissions.")
    elif page == "Do Not Call":
        if require_role(["admin","recruiter"]): page_dnc()
        else: st.warning("Insufficient permissions.")
    elif page == "Keywords":
        if require_role(["admin"]): page_keywords()
        else: st.warning("Admin only.")
    elif page == "Hiring Areas":
        if require_role(["admin"]): page_hiring_areas()
        else: st.warning("Admin only.")
    elif page == "Compliance":
        page_compliance()
    elif page == "Changelog":
        page_changelog()
