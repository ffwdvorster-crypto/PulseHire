import os, io, json, sqlite3, datetime, re
import pandas as pd
import streamlit as st

# --- Local modules you already have ---
from theme import apply_theme
from auth import login_user, ensure_admin_exists, create_user, change_password, list_users
from db import init_db, get_db, get_setting, set_setting, purge_older_than_years
from scoring import SEED_KEYWORDS, extract_text, score_cv
from ingestion import ingest_applications, ingest_testgorilla, ingest_interview_notes
from compliance import compliance_text

# ---- Constants ----
UPLOAD_DIR = "uploads"
LOGO_PATH = "assets/pulsehire_logo.png"

# ---- One-time init ----
apply_theme()
init_db()
ensure_admin_exists()
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---- Lightweight migrations (safe if re-run) ----
with get_db() as con:
    con.execute("""CREATE TABLE IF NOT EXISTS campaign_keywords(
        campaign_id INTEGER,
        keyword TEXT,
        PRIMARY KEY (campaign_id, keyword)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS keywords(
        keyword TEXT PRIMARY KEY
    )""")
    # backfill global keywords table from settings if present
    try:
        existing = {r[0] for r in con.execute("SELECT keyword FROM keywords").fetchall()}
        seed = get_setting("keywords", None)
        if seed and isinstance(seed, dict):
            flat = set()
            for arr in seed.values():
                flat.update([str(x).strip() for x in arr if str(x).strip()])
            new = [(k,) for k in flat if k not in existing]
            if new:
                con.executemany("INSERT OR IGNORE INTO keywords(keyword) VALUES(?)", new)
    except Exception:
        pass

    # add is_test flags where useful
    try:
        con.execute("ALTER TABLE test_scores ADD COLUMN is_test INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE attachments ADD COLUMN is_test INTEGER DEFAULT 0")
    except Exception:
        pass

# ---- Session state ----
if "user" not in st.session_state:
    st.session_state["user"] = None
if "page" not in st.session_state:
    st.session_state["page"] = "Dashboard"

# ---- Header (logo left, larger) ----
c1, c2 = st.columns([1, 6])
with c1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=320)
st.divider()

# ---- Auth gate ----
if st.session_state["user"] is None:
    st.subheader("🔐 Login")
    email = st.text_input("Email")
    pwd = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        u = login_user(email, pwd)
        if u:
            st.session_state["user"] = u
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.caption("Default admin: admin@pulsehire.local / admin")
    st.stop()

user = st.session_state["user"]
def role_can_edit(): return user["role"] in ("admin", "recruiter", "hr")
def role_is_admin(): return user["role"] == "admin"

# ---- Sidebar nav (icon buttons) ----
def nav_button(label, page_key, emoji):
    active = (st.session_state["page"] == page_key)
    btn_type = "primary" if active else "secondary"
    st.sidebar.button(f"{emoji}  {label}", use_container_width=True,
                      type=btn_type,
                      key=f"nav_{page_key}",
                      on_click=lambda: st.session_state.update({"page": page_key}))

with st.sidebar:
    st.success(f"{user['name']} · {user['role'].title()}")
    st.markdown("#### Navigation")
    nav_button("Dashboard",          "Dashboard",          "🏠")
    nav_button("Campaigns",          "Campaigns",          "🎯")
    nav_button("Active recruitment", "Active recruitment", "🚀")
    nav_button("Candidates",         "Candidates",         "👥")
    nav_button("Do Not Call",        "Do Not Call",        "🚫")
    nav_button("Keywords",           "Keywords",           "🧩")
    nav_button("Hiring Areas",       "Hiring Areas",       "🗺️")
    nav_button("Compliance",         "Compliance",         "⚖️")
    nav_button("Changelog",          "Changelog",          "📜")
    if role_is_admin():
        nav_button("Admin",          "Admin",              "🛠️")
    nav_button("Account",            "Account",            "👤🔑")
    st.markdown("---")
    if st.button("Log out", use_container_width=True):
        st.session_state["user"] = None
        st.rerun()

# ---- Helpers ----
def business_days_before(date_str, days=7):
    d = datetime.datetime.strptime(str(date_str), "%Y-%m-%d").date()
    step = datetime.timedelta(days=1)
    n = 0
    while n < days:
        d -= step
        if d.weekday() < 5:
            n += 1
    return d.strftime("%Y-%m-%d")

def export_df_csv_button(df: pd.DataFrame, filename: str, label="Download CSV"):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, data=csv, file_name=filename, mime="text/csv")

def parse_multi(text: str):
    if not text: return []
    parts = re.split(r"[,\n;]+", text)
    return [p.strip() for p in parts if p.strip()]

# ---- Pages ----
def page_dashboard():
    st.markdown("### Dashboard")
    with get_db() as con:
        c = con.cursor()
        total = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        dnc   = c.execute("SELECT COUNT(*) FROM candidates WHERE dnc=1").fetchone()[0]
        ts    = c.execute("SELECT COUNT(*) FROM test_scores").fetchone()[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Candidates", total)
    m2.metric("Do Not Call", dnc)
    m3.metric("Test scores", ts)
    st.info("Use the sidebar to navigate between modules.")

def page_campaigns():
    st.markdown("### Campaigns")

    with get_db() as con:
        df = pd.read_sql_query("""
            SELECT c.id, c.name, c.requirements_text, c.req_need_weekends,
                   c.req_need_evenings, c.req_need_weekdays, c.req_remote_ok,
                   GROUP_CONCAT(k.keyword) AS keywords
            FROM campaigns c
            LEFT JOIN campaign_keywords k ON k.campaign_id = c.id
            GROUP BY c.id
            ORDER BY LOWER(c.name)
        """, con)
    st.dataframe(df, use_container_width=True, height=260)

    # Helper to ensure keywords exist in global pool
    def ensure_keywords(conn, kws):
        conn.executemany("INSERT OR IGNORE INTO keywords(keyword) VALUES(?)",
                         [(k,) for k in kws])

    # Add new campaign
    with st.expander("➕ Add New Campaign"):
        name = st.text_input("Campaign name")
        reqs = st.text_area("Requirements / Notes")
        col1, col2, col3, col4 = st.columns(4)
        weekends = col1.checkbox("Weekends")
        evenings = col2.checkbox("Evenings")
        weekdays = col3.checkbox("Weekdays", value=True)
        remote   = col4.checkbox("Remote OK")

        with get_db() as con:
            global_kws = [r[0] for r in con.execute("SELECT keyword FROM keywords ORDER BY keyword").fetchall()]
        selected = st.multiselect("Relevant keywords (from global pool)", global_kws)
        new_kws  = st.text_input("Add new keywords (comma/semicolon)")

        if role_can_edit() and st.button("Save campaign", type="primary"):
            if not name:
                st.warning("Campaign name required.")
            else:
                add_kws = parse_multi(new_kws)
                all_kws = sorted(set(selected + add_kws))
                with get_db() as con:
                    cur = con.execute("""INSERT INTO campaigns
                        (name, requirements_text, req_need_weekends, req_need_evenings, req_need_weekdays, req_remote_ok)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (name, reqs, int(weekends), int(evenings), int(weekdays), int(remote)))
                    cid = cur.lastrowid
                    ensure_keywords(con, all_kws)
                    con.executemany("INSERT INTO campaign_keywords(campaign_id, keyword) VALUES(?,?)",
                                    [(cid, k) for k in all_kws])
                st.success(f"Campaign '{name}' added.")
                st.rerun()

    # Edit/Delete
    with st.expander("✏️ Edit / Delete Campaigns"):
        if df.empty:
            st.info("No campaigns yet.")
        else:
            cid = st.selectbox("Select campaign", df["id"], format_func=lambda x: df[df["id"]==x]["name"].values[0])
            row = df[df["id"]==cid].iloc[0]
            new_name = st.text_input("Campaign name", row["name"])
            new_reqs = st.text_area("Requirements / Notes", row["requirements_text"] or "")
            col1, col2, col3, col4 = st.columns(4)
            weekends = col1.checkbox("Weekends", bool(row["req_need_weekends"]))
            evenings = col2.checkbox("Evenings", bool(row["req_need_evenings"]))
            weekdays = col3.checkbox("Weekdays", bool(row["req_need_weekdays"]))
            remote   = col4.checkbox("Remote OK", bool(row["req_remote_ok"]))

            with get_db() as con:
                global_kws = [r[0] for r in con.execute("SELECT keyword FROM keywords ORDER BY keyword").fetchall()]
            current = [k for k in (row["keywords"] or "").split(",") if k]
            chosen  = st.multiselect("Relevant keywords", global_kws, default=current)
            new_kws = st.text_input("Add new keywords to this campaign (comma/semicolon)")

            cols = st.columns(2)
            if cols[0].button("Update", type="primary"):
                add_kws = parse_multi(new_kws)
                all_kws = sorted(set(chosen + add_kws))
                with get_db() as con:
                    con.execute("""UPDATE campaigns SET
                                   name=?, requirements_text=?, req_need_weekends=?, req_need_evenings=?, req_need_weekdays=?, req_remote_ok=?
                                   WHERE id=?""",
                                (new_name, new_reqs, int(weekends), int(evenings), int(weekdays), int(remote), int(cid)))
                    con.execute("DELETE FROM campaign_keywords WHERE campaign_id=?", (int(cid),))
                    ensure_keywords(con, all_kws)
                    con.executemany("INSERT INTO campaign_keywords(campaign_id, keyword) VALUES(?,?)",
                                    [(int(cid), k) for k in all_kws])
                st.success("Updated.")
                st.rerun()

            if cols[1].button("🗑️ Delete", type="secondary"):
                with get_db() as con:
                    con.execute("DELETE FROM campaign_keywords WHERE campaign_id=?", (int(cid),))
                    con.execute("DELETE FROM campaigns WHERE id=?", (int(cid),))
                st.success("Deleted.")
                st.rerun()

    # Bulk upload / template
    with st.expander("📂 Bulk Upload / Download"):
        st.download_button(
            "Download CSV template",
            data="name,requirements_text,weekends,evenings,weekdays,remote,keywords\n",
            file_name="campaigns_template.csv",
            mime="text/csv"
        )
        up = st.file_uploader("Upload campaigns CSV", type=["csv"])
        if up and st.button("Import campaigns CSV"):
            dfc = pd.read_csv(up)
            required = ["name","requirements_text","weekends","evenings","weekdays","remote","keywords"]
            if not all(c in dfc.columns for c in required):
                st.error("Missing required headers.")
            else:
                with get_db() as con:
                    for _, r in dfc.iterrows():
                        cur = con.execute("""INSERT INTO campaigns(name,requirements_text,req_need_weekends,req_need_evenings,req_need_weekdays,req_remote_ok)
                                             VALUES(?,?,?,?,?,?)""",
                                          (r["name"], r["requirements_text"], int(r["weekends"]), int(r["evenings"]), int(r["weekdays"]), int(r["remote"])))
                        cid = cur.lastrowid
                        kws = [k.strip() for k in str(r["keywords"]).split(";") if k.strip()]
                        con.executemany("INSERT OR IGNORE INTO keywords(keyword) VALUES(?)", [(k,) for k in kws])
                        con.executemany("INSERT INTO campaign_keywords(campaign_id, keyword) VALUES(?,?)", [(cid,k) for k in kws])
                st.success("Imported campaigns.")
                st.rerun()

def page_active_recruitment():
    st.markdown("### Active recruitment")
    with get_db() as con:
        campaigns = pd.read_sql_query("SELECT id,name FROM campaigns ORDER BY name", con)
    cmap = {r["name"]: r["id"] for _, r in campaigns.iterrows()} if not campaigns.empty else {}

    if role_can_edit() and cmap:
        with st.form("ar_form"):
            cname = st.selectbox("Campaign", list(cmap.keys()))
            start = st.date_input("Start date")
            cutoff = business_days_before(start.strftime("%Y-%m-%d"), 7)
            st.write(f"Auto cutoff: **{cutoff}** (7 working days before start)")
            notes = st.text_input("Notes")
            ok = st.form_submit_button("Activate")
        if ok:
            with get_db() as con:
                con.execute("""INSERT INTO active_recruitment(campaign_id,start_date,cutoff_date,notes,is_active)
                               VALUES(?,?,?,?,1)""", (cmap[cname], start.strftime("%Y-%m-%d"), cutoff, notes))
            st.success("Active recruitment created.")

    with get_db() as con:
        df = pd.read_sql_query("""
            SELECT ar.id, c.name AS campaign, ar.start_date, ar.cutoff_date, ar.is_active, ar.notes
            FROM active_recruitment ar
            LEFT JOIN campaigns c ON c.id = ar.campaign_id
            ORDER BY ar.created_at DESC
        """, con)
    st.dataframe(df, use_container_width=True)
    if role_can_edit():
        deact = st.number_input("Deactivate ID", min_value=0, step=1)
        if st.button("Deactivate") and deact:
            with get_db() as con:
                con.execute("UPDATE active_recruitment SET is_active=0 WHERE id=?", (int(deact),))
            st.success("Deactivated.")

def page_candidates():
    st.markdown("### Candidates")

    # ---- Bulk imports ----
    with st.expander("📥 Bulk import — Applications (Excel)"):
        apps = st.file_uploader("Upload Application Excel (.xlsx)", type=["xlsx"], key="apps_xlsx")
        test_mode = st.checkbox("Upload as test data (candidates)", key="apps_test")
        if apps and st.button("Import applications", type="primary"):
            res = ingest_applications(apps)
            # mark as test if requested (add column exists in schema)
            if test_mode:
                with get_db() as con:
                    con.execute("UPDATE candidates SET is_test=1 WHERE is_test IS NULL OR is_test=0")
            st.success(f"Imported: {res['inserted']} inserted, {res['updated']} updated, {res.get('dnc_applied',0)} auto-DNC.")

    with st.expander("🧪 Bulk import — TestGorilla"):
        tg = st.file_uploader("Upload TestGorilla Excel (.xlsx)", type=["xlsx"], key="tg_xlsx")
        tg_test = st.checkbox("Upload as test data (TestGorilla)", key="tg_test")
        if tg and st.button("Import TestGorilla", type="primary"):
            n = ingest_testgorilla(tg)
            if tg_test:
                with get_db() as con:
                    con.execute("UPDATE test_scores SET is_test=1 WHERE is_test=0")  # mark all if flag present
            st.success(f"Imported {n} test score rows.")

    with st.expander("📝 Bulk import — Interview Notes"):
        inx = st.file_uploader("Upload Interview Notes Excel (.xlsx)", type=["xlsx"], key="in_xlsx")
        in_test = st.checkbox("Upload as test data (Interview Notes)", key="in_test")
        if inx and st.button("Import Interview Notes", type="primary"):
            n = ingest_interview_notes(inx)
            if in_test:
                with get_db() as con:
                    con.execute("UPDATE attachments SET is_test=1 WHERE doc_type='Interview Notes'")
            st.success(f"Processed {n} interview notes row(s).")

    # ---- Filters ----
    colf = st.columns(6)
    with colf[0]: f_status = st.selectbox("Status", ["Any","Applied","Interviewed","Hired","Rejected"])
    with colf[1]: f_dnc    = st.selectbox("DNC", ["Any","Only DNC","Only not DNC"])
    with colf[2]: f_tier   = st.selectbox("Score tier", ["Any","High","Medium","Low"])
    with colf[3]: f_search = st.text_input("Search")
    with colf[4]: f_camp   = st.text_input("Campaign")
    with colf[5]: f_test   = st.selectbox("Test data", ["All","Only test","Only live"])

    q = "SELECT id,name,email,phone,county,status,campaign,score_tier,dnc FROM candidates WHERE 1=1"
    params = []
    if f_status!="Any": q+=" AND status=?"; params.append(f_status)
    if f_dnc=="Only DNC": q+=" AND dnc=1"
    if f_dnc=="Only not DNC": q+=" AND dnc=0"
    if f_tier!="Any": q+=" AND score_tier=?"; params.append(f_tier)
    if f_camp: q+=" AND campaign LIKE ?"; params.append(f"%{f_camp}%")
    if f_search:
        q+=" AND (LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR phone LIKE ?)"
        s=f"%{f_search.lower()}%"; params += [s,s,f_search]
    if f_test=="Only test": q+=" AND COALESCE(is_test,0)=1"
    if f_test=="Only live": q+=" AND COALESCE(is_test,0)=0"
    q+=" ORDER BY LOWER(name)"

    with get_db() as con:
        df = pd.read_sql_query(q, con, params=params)

    left, right = st.columns([1, 2])
    with left:
        st.caption("Candidates (A–Z)")
        if df.empty:
            st.info("No candidates match your filters.")
            sel_id = None
        else:
            names = [f"{r['name'] or '—'}  •  {r['email'] or ''}  (#{r['id']})" for _, r in df.iterrows()]
            selected = st.selectbox("Pick", names, index=0)
            sel_id = int(selected.split('#')[-1][:-1])

        # Bulk actions
        if role_can_edit() and not df.empty:
            st.subheader("Bulk actions")
            ids_text = st.text_area("Enter candidate IDs (comma-separated)")
            if st.button("Bulk DNC"):
                ids = [int(x) for x in ids_text.split(",") if x.strip().isdigit()]
                with get_db() as con:
                    con.executemany("UPDATE candidates SET dnc=1, dnc_reason='Bulk action' WHERE id=?", [(i,) for i in ids])
                st.success("Bulk DNC applied.")
            if st.button("Bulk un-DNC"):
                ids = [int(x) for x in ids_text.split(",") if x.strip().isdigit()]
                with get_db() as con:
                    con.executemany("UPDATE candidates SET dnc=0, dnc_reason=NULL WHERE id=?", [(i,) for i in ids])
                st.success("Bulk un-DNC applied.")
            camp = st.text_input("Assign campaign")
            if st.button("Bulk assign campaign"):
                ids = [int(x) for x in ids_text.split(",") if x.strip().isdigit()]
                with get_db() as con:
                    con.executemany("UPDATE candidates SET campaign=? WHERE id=?", [(camp, i) for i in ids])
                st.success("Campaign assigned.")

        if not df.empty:
            export_df_csv_button(df, "candidates_filtered.csv", "Export filtered CSV")

    with right:
        if sel_id:
            render_candidate(sel_id)

def render_candidate(cid: int):
    conn = get_db(); conn.row_factory = sqlite3.Row; cur = conn.cursor()
    cur.execute("SELECT * FROM candidates WHERE id=?", (cid,))
    cand = cur.fetchone()
    if not cand:
        st.warning("Candidate not found"); return

    st.markdown(f"#### {cand['name'] or '—'}  (#{cid})")
    info = st.columns(4)
    info[0].write(f"Email: {cand['email'] or '—'}")
    info[1].write(f"Phone: {cand['phone'] or '—'}")
    info[2].write(f"County: {cand['county'] or '—'}")
    info[3].write(f"Status: {cand['status'] or '—'}")

    tabs = st.tabs(["Details","CV","TestGorilla","Interview Notes","Attachments","Notes","Audit Trail","Compliance"])

    # Details
    with tabs[0]:
        col = st.columns(3)
        notice = col[0].text_input("Notice period", value=cand["notice_period"] or "")
        leave  = col[1].text_input("Leave", value=cand["planned_leave"] or "")
        status = col[2].selectbox("Status", ["Applied","Interviewed","Hired","Rejected"],
                                  index=["Applied","Interviewed","Hired","Rejected"].index(cand["status"]) if cand["status"] in ["Applied","Interviewed","Hired","Rejected"] else 0)
        avail  = st.text_input("Availability", value=cand["availability"] or "")
        src    = st.text_input("Source", value=cand["source"] or "")
        notesv = st.text_area("Notes", value=cand["notes"] or "")

        d1, d2, d3 = st.columns(3)
        dnc_val = d1.checkbox("Do Not Call", value=bool(cand["dnc"]))
        dnc_reason = d2.text_input("DNC reason", value=cand["dnc_reason"] or "")
        is_test = d3.checkbox("Marked as test data", value=bool(cand["is_test"] or 0))

        if role_can_edit() and st.button("Save details"):
            with get_db() as con:
                con.execute("""UPDATE candidates SET
                               notice_period=?, planned_leave=?, status=?, availability=?, source=?, notes=?,
                               dnc=?, dnc_reason=?, is_test=?, updated_at=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (notice or None, leave or None, status, avail or None, src or None, notesv or None,
                             int(dnc_val), dnc_reason or None, int(is_test), cid))
            st.success("Saved.")
            st.rerun()

        st.markdown("---")
        st.write(f"Score tier: **{cand['score_tier'] or '—'}**")
        try:
            flags = json.loads(cand["flags_json"]) if cand["flags_json"] else {}
            st.json(flags)
        except Exception:
            st.caption("(no flags)")

    # CV
    with tabs[1]:
        cv = st.file_uploader("Upload CV (PDF/DOCX/TXT)", type=["pdf","docx","txt"], key=f"cv_{cid}")
        if role_can_edit() and cv and st.button("Upload & score"):
            raw = cv.read()
            text = extract_text(io.BytesIO(raw))
            path = os.path.join(UPLOAD_DIR, f"cv_{cid}_{cv.name}")
            with open(path, "wb") as f: f.write(raw)
            keywords = get_setting("keywords", SEED_KEYWORDS) or SEED_KEYWORDS
            tier, flags = score_cv(text, keywords)
            with get_db() as con:
                con.execute("UPDATE candidates SET score_tier=?, flags_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (tier, json.dumps(flags), cid))
                con.execute("INSERT INTO attachments(candidate_id,filename,path,doc_type) VALUES(?,?,?,?)",
                            (cid, cv.name, path, "CV"))
            st.success(f"Scored: {tier} ({flags.get('score_pct','?')}%)")
            st.rerun()

    # TestGorilla
    with tabs[2]:
        up = st.file_uploader("Upload TestGorilla Excel", type=["xlsx"])
        tg_test = st.checkbox("Mark imported as test data", key=f"tg_test_{cid}")
        if role_can_edit() and up and st.button("Import TestGorilla"):
            n = ingest_testgorilla(up)
            if tg_test:
                with get_db() as con:
                    con.execute("UPDATE test_scores SET is_test=1 WHERE candidate_id=?", (cid,))
            st.success(f"Imported {n} row(s).")
        with get_db() as con:
            df = pd.read_sql_query("SELECT test_name, score_raw, score_pct, imported_at FROM test_scores WHERE candidate_id=? ORDER BY imported_at DESC", con, params=(cid,))
        st.dataframe(df, use_container_width=True)

    # Interview Notes
    with tabs[3]:
        up = st.file_uploader("Upload Interview Notes Excel (.xlsx)", type=["xlsx"])
        in_test = st.checkbox("Mark imported as test data", key=f"in_test_{cid}")
        if role_can_edit() and up and st.button("Import Interview Notes"):
            n = ingest_interview_notes(up)
            if in_test:
                with get_db() as con:
                    con.execute("UPDATE attachments SET is_test=1 WHERE candidate_id=? AND doc_type='Interview Notes'", (cid,))
            st.success(f"Processed {n} row(s).")
            st.rerun()
        with get_db() as con:
            df = pd.read_sql_query("""SELECT id, filename, uploaded_at FROM attachments
                                      WHERE candidate_id=? AND doc_type='Interview Notes'
                                      ORDER BY uploaded_at DESC""", con, params=(cid,))
        st.dataframe(df, use_container_width=True)

    # Attachments
    with tabs[4]:
        up = st.file_uploader("Add attachment", key=f"att_{cid}")
        dtype = st.selectbox("Type", ["CV","Visa","Speed Test","Interview Notes","Other"], key=f"dtype_{cid}")
        mark_test = st.checkbox("Mark as test data", key=f"att_test_{cid}")
        if role_can_edit() and up and st.button("Upload attachment"):
            raw = up.read(); path = os.path.join(UPLOAD_DIR, up.name)
            with open(path, "wb") as f: f.write(raw)
            with get_db() as con:
                con.execute("INSERT INTO attachments(candidate_id,filename,path,doc_type,is_test) VALUES(?,?,?,?,?)",
                            (cid, up.name, path, dtype, int(mark_test)))
            st.success("Saved."); st.rerun()
        with get_db() as con:
            df = pd.read_sql_query("SELECT id,filename,doc_type,is_test,uploaded_at FROM attachments WHERE candidate_id=? ORDER BY uploaded_at DESC", con, params=(cid,))
        st.dataframe(df, use_container_width=True)

    # Notes
    with tabs[5]:
        st.text_area("Notes", value=cand["notes"] or "", key=f"notes_{cid}")
        if role_can_edit() and st.button("Save notes"):
            with get_db() as con:
                con.execute("UPDATE candidates SET notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (st.session_state[f'notes_{cid}'], cid))
            st.success("Saved.")

    # Audit
    with tabs[6]:
        with get_db() as con:
            df = pd.read_sql_query("SELECT action, target, meta_json, at FROM audit_logs WHERE target=? ORDER BY at DESC", con, params=(f'candidate:{cid}',))
        st.dataframe(df, use_container_width=True)

    # Compliance
    with tabs[7]:
        st.markdown(compliance_text())

def page_dnc():
    st.markdown("### Do Not Call")
    with get_db() as con:
        df = pd.read_sql_query("SELECT id,name,email,county,dnc_reason,updated_at FROM candidates WHERE dnc=1 ORDER BY updated_at DESC", con)
    st.dataframe(df, use_container_width=True)
    if role_can_edit():
        cid = st.number_input("Restore candidate ID", min_value=0, step=1)
        if st.button("Restore") and cid:
            with get_db() as con:
                con.execute("UPDATE candidates SET dnc=0, dnc_reason=NULL WHERE id=?", (int(cid),))
            st.success("Restored.")

def page_keywords():
    st.markdown("### Keywords")
    # Show editable global keywords (from table)
    with get_db() as con:
        df = pd.read_sql_query("SELECT keyword FROM keywords ORDER BY keyword", con)
    st.dataframe(df, use_container_width=True, height=260)
    if role_is_admin():
        add_text = st.text_input("Add keywords (comma/semicolon/newline)")
        if st.button("Add keywords"):
            kws = parse_multi(add_text)
            if kws:
                with get_db() as con:
                    con.executemany("INSERT OR IGNORE INTO keywords(keyword) VALUES(?)", [(k,) for k in kws])
                st.success(f"Added {len(kws)} keyword(s).")
                st.rerun()

def page_hiring_areas():
    st.markdown("### Hiring Areas (blocked counties)")
    with get_db() as con:
        df = pd.read_sql_query("SELECT county FROM blocked_counties ORDER BY LOWER(county)", con)
    st.dataframe(df, use_container_width=True, height=260)

    if role_is_admin():
        st.markdown("#### Add multiple")
        add_text = st.text_area("Paste counties (comma/semicolon/newline)", placeholder="Cork, Kerry; Waterford\nGalway")
        if st.button("Add counties", type="primary"):
            items = parse_multi(add_text)
            if not items:
                st.warning("No counties detected.")
            else:
                with get_db() as con:
                    con.executemany("INSERT OR IGNORE INTO blocked_counties(county) VALUES(?)", [(c,) for c in items])
                st.success(f"Added {len(items)} item(s).")
                st.rerun()

        st.markdown("#### Remove multiple")
        rem_text = st.text_area("Counties to remove", placeholder="Tipperary; Limerick\nMayo")
        if st.button("Remove counties", type="secondary"):
            items = parse_multi(rem_text)
            if not items:
                st.warning("No counties detected.")
            else:
                with get_db() as con:
                    con.executemany("DELETE FROM blocked_counties WHERE LOWER(county)=LOWER(?)", [(c,) for c in items])
                st.success(f"Removed {len(items)} item(s) (where present).")
                st.rerun()

        st.markdown("---")
        if st.button("Apply blocked counties to candidates"):
            with get_db() as con:
                blocked = [r[0].strip().lower() for r in con.execute("SELECT county FROM blocked_counties").fetchall()]
                rows = con.execute("SELECT id,county,dnc_override FROM candidates").fetchall()
                n=0
                for cid, county, override in rows:
                    if (county or '').strip().lower() in blocked and not (override or 0):
                        con.execute("UPDATE candidates SET dnc=1, dnc_reason='Outside hiring area' WHERE id=?", (cid,))
                        n+=1
                con.commit()
            st.success(f"Applied to {n} candidate(s).")

def page_compliance():
    st.markdown("### Compliance")
    st.markdown(compliance_text())

def page_changelog():
    st.markdown("### Changelog")
    path = "changelog.md"
    if not os.path.exists(path):
        with open(path, "w") as f: f.write("## Changelog\n- Initial release\n")
    with open(path, "r") as f:
        content = f.read()
    if role_is_admin():
        new = st.text_area("Edit changelog", value=content, height=200)
        if st.button("Save changelog"):
            with open(path, "w") as f: f.write(new)
            st.success("Saved.")
    else:
        st.code(content, language="markdown")

def page_admin():
    if not role_is_admin():
        st.warning("Admin only."); return
    st.markdown("### Admin")
    st.subheader("Create user")
    with st.form("create_user"):
        em = st.text_input("Email")
        nm = st.text_input("Name")
        rl = st.selectbox("Role", ["recruiter","hr","viewer","admin"])
        pw1 = st.text_input("Password", type="password")
        pw2 = st.text_input("Confirm password", type="password")
        ok = st.form_submit_button("Create")
    if ok:
        if not em or not pw1 or pw1!=pw2:
            st.error("Check inputs.")
        else:
            try:
                create_user(em, nm, pw1, rl); st.success("User created.")
            except Exception as e:
                st.error(str(e))
    st.subheader("Users")
    st.dataframe(list_users(), use_container_width=True)
    st.subheader("Retention")
    if st.button("Purge candidates older than 2 years"):
        n = purge_older_than_years(2); st.success(f"Purged {n} candidate(s).")

def page_account():
    st.markdown("### Account")
    with st.form("pw"):
        p1 = st.text_input("New password", type="password")
        p2 = st.text_input("Confirm", type="password")
        ok = st.form_submit_button("Update password")
    if ok:
        if not p1 or p1!=p2: st.error("Check passwords.")
        else:
            n = change_password(user['id'], p1); st.success("Updated." if n else "No change.")

# ---- Router ----
page = st.session_state["page"]
if page == "Dashboard": page_dashboard()
elif page == "Campaigns": page_campaigns()
elif page == "Active recruitment": page_active_recruitment()
elif page == "Candidates": page_candidates()
elif page == "Do Not Call": page_dnc()
elif page == "Keywords": page_keywords()
elif page == "Hiring Areas": page_hiring_areas()
elif page == "Compliance": page_compliance()
elif page == "Changelog": page_changelog()
elif page == "Admin": page_admin()
elif page == "Account": page_account()
