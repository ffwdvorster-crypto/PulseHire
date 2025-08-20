import os, json, io, sqlite3, datetime
import pandas as pd
import streamlit as st
from theme import apply_theme
import db
from auth import login_user, ensure_admin_exists, create_user, change_password, list_users
from scoring import SEED_KEYWORDS, extract_text, score_cv
from ingestion import ingest_testgorilla, ingest_interview_notes
from compliance import compliance_text

UPLOAD_DIR = "uploads"
LOGO_PATH = "assets/pulsehire_logo.png"

# ---------- Setup ----------
apply_theme()
db.init_db(); ensure_admin_exists()
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- Header (logo only, larger) ----------
c1, c2 = st.columns([1,6])
with c1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=320)
st.divider()

# ---------- Session & Auth ----------
if "user" not in st.session_state: st.session_state["user"]=None
if "page" not in st.session_state: st.session_state["page"]="Dashboard"

if st.session_state["user"] is None:
    st.subheader("🔐 Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        user = login_user(email, password)
        if user:
            st.session_state["user"] = user
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.caption("Default admin: admin@pulsehire.local / admin")
    st.stop()

user = st.session_state["user"]

# ---------- Sidebar Nav (selectbox, no radio) ----------
with st.sidebar:
    st.success(f"{user['name']} · {user['role'].title()}")
    pages = ["Dashboard","Campaigns","Active recruitment","Candidates","Do Not Call","Keywords","Hiring Areas","Compliance","Changelog"]
    if user["role"]=="admin":
        pages += ["Admin","Account"]
    else:
        pages += ["Account"]
    st.session_state["page"] = st.selectbox("Navigation", pages, index=pages.index(st.session_state["page"]) if st.session_state["page"] in pages else 0)
    if st.button("Log out"):
        st.session_state["user"]=None; st.rerun()

# ---------- Helpers ----------
def business_days_before(date_str, days=7):
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    step = datetime.timedelta(days=1)
    count=0
    while count < days:
        d = d - step
        if d.weekday() < 5:  # Mon-Fri
            count += 1
    return d.strftime("%Y-%m-%d")

def role_can_edit():
    return user["role"] in ("admin","recruiter","hr")

def role_is_admin():
    return user["role"]=="admin"

# ---------- Pages ----------
def page_dashboard():
    st.markdown("### Dashboard")
    with db.get_db() as con:
        c = con.cursor()
        c.execute("SELECT COUNT(*) FROM candidates"); total=c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM candidates WHERE dnc=1"); dnc=c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM test_scores"); ts=c.fetchone()[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Candidates", total); m2.metric("Do Not Call", dnc); m3.metric("Test scores", ts)
    st.info("Use the sidebar to navigate.")

def page_campaigns():
    st.markdown("### Campaigns")
    if role_can_edit():
        with st.form("add_campaign"):
            name = st.text_input("Name")
            hours_notes = st.text_area("Hours notes")
            requirements_text = st.text_area("Requirements text")
            req_weekends = st.checkbox("Needs weekends", value=False)
            req_evenings = st.checkbox("Needs evenings", value=False)
            req_weekdays = st.checkbox("Needs weekdays", value=True)
            req_remote = st.checkbox("Remote OK", value=False)
            ok = st.form_submit_button("Create campaign")
        if ok and name:
            with db.get_db() as con:
                con.execute("""INSERT INTO campaigns(name,hours_notes,requirements_text,
                    req_need_weekends,req_need_evenings,req_need_weekdays,req_remote_ok)
                    VALUES(?,?,?,?,?,?,?)""", (name,hours_notes,requirements_text,int(req_weekends),int(req_evenings),int(req_weekdays),int(req_remote)))
            st.success("Campaign created.")
    with db.get_db() as con:
        df = pd.read_sql_query("SELECT * FROM campaigns ORDER BY created_at DESC", con)
    st.dataframe(df, use_container_width=True)

def page_active_recruitment():
    st.markdown("### Active recruitment")
    with db.get_db() as con:
        campaigns = pd.read_sql_query("SELECT id,name FROM campaigns ORDER BY name", con)
    cmap = {r["name"]:r["id"] for _, r in campaigns.iterrows()} if not campaigns.empty else {}
    if role_can_edit() and cmap:
        with st.form("ar_form"):
            cname = st.selectbox("Campaign", list(cmap.keys()))
            start = st.date_input("Start date")
            cutoff = business_days_before(start.strftime("%Y-%m-%d"), 7)
            st.write(f"Auto cutoff: **{cutoff}** (7 working days before start)")
            notes = st.text_input("Notes")
            ok = st.form_submit_button("Activate")
        if ok:
            with db.get_db() as con:
                con.execute("INSERT INTO active_recruitment(campaign_id,start_date,cutoff_date,notes,is_active) VALUES(?,?,?,?,1)",
                            (cmap[cname], start.strftime("%Y-%m-%d"), cutoff, notes))
            st.success("Active recruitment created.")
    with db.get_db() as con:
        df = pd.read_sql_query("SELECT ar.id, c.name as campaign, ar.start_date, ar.cutoff_date, ar.is_active, ar.notes FROM active_recruitment ar LEFT JOIN campaigns c ON c.id=ar.campaign_id ORDER BY ar.created_at DESC", con)
    st.dataframe(df, use_container_width=True)
    if role_can_edit():
        deact = st.number_input("Deactivate ID", min_value=0, step=1)
        if st.button("Deactivate") and deact:
            with db.get_db() as con:
                con.execute("UPDATE active_recruitment SET is_active=0 WHERE id=?", (int(deact),))
            st.success("Deactivated.")

def page_candidates():
    st.markdown("### Candidates")
    # Filters
    colf = st.columns(5)
    with colf[0]:
        f_status = st.selectbox("Status", ["Any","Applied","Interviewed","Hired","Rejected"])
    with colf[1]:
        f_dnc = st.selectbox("DNC", ["Any","Only DNC","Only not DNC"])
    with colf[2]:
        f_tier = st.selectbox("Score tier", ["Any","High","Medium","Low"])
    with colf[3]:
        f_search = st.text_input("Search")
    with colf[4]:
        f_campaign = st.text_input("Campaign")

    # Query
    q = "SELECT id,name,email,phone,county,status,campaign,score_tier,dnc FROM candidates WHERE 1=1"
    params=[]
    if f_status!="Any": q+=" AND status=?"; params.append(f_status)
    if f_dnc=="Only DNC": q+=" AND dnc=1"
    if f_dnc=="Only not DNC": q+=" AND dnc=0"
    if f_tier!="Any": q+=" AND score_tier=?"; params.append(f_tier)
    if f_campaign: q+=" AND campaign LIKE ?"; params.append(f"%{f_campaign}%")
    if f_search:
        q+=" AND (LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR phone LIKE ?)"
        s=f"%{f_search.lower()}%"; params+= [s,s,f_search]
    q+=" ORDER BY LOWER(name)"
    with db.get_db() as con:
        df = pd.read_sql_query(q, con, params=params)
    left, right = st.columns([1,2])
    with left:
        st.caption("Candidates (A–Z)")
        names = [f"{r['name'] or '—'}  •  {r['email'] or ''}  (#{r['id']})" for _, r in df.iterrows()]
        selected = st.selectbox("Pick", names, index=0 if not df.empty else None, placeholder="No candidates")
        sel_id = int(selected.split("#")[-1][:-1]) if selected else None
        if role_can_edit():
            with st.form("add_cand"):
                st.subheader("Add candidate")
                nm = st.text_input("Name")
                em = st.text_input("Email")
                ph = st.text_input("Phone")
                co = st.text_input("County")
                ok = st.form_submit_button("Add")
            if ok:
                with db.get_db() as con:
                    con.execute("INSERT INTO candidates(name,email,phone,county,status) VALUES(?,?,?,?,?)",(nm or None, em or None, ph or None, co or None, "Applied"))
                st.success("Added."); st.rerun()
        # Bulk actions
        if role_can_edit() and not df.empty:
            st.subheader("Bulk actions")
            ids_text = st.text_area("Enter candidate IDs (comma-separated)")
            if st.button("Bulk DNC"):
                ids = [int(x) for x in ids_text.split(",") if x.strip().isdigit()]
                with db.get_db() as con:
                    con.executemany("UPDATE candidates SET dnc=1, dnc_reason='Bulk action' WHERE id=?", [(i,) for i in ids])
                st.success("Bulk DNC applied.")
            if st.button("Bulk un-DNC"):
                ids = [int(x) for x in ids_text.split(",") if x.strip().isdigit()]
                with db.get_db() as con:
                    con.executemany("UPDATE candidates SET dnc=0, dnc_reason=NULL WHERE id=?", [(i,) for i in ids])
                st.success("Bulk un-DNC applied.")
            camp = st.text_input("Assign campaign")
            if st.button("Bulk assign campaign"):
                ids = [int(x) for x in ids_text.split(",") if x.strip().isdigit()]
                with db.get_db() as con:
                    con.executemany("UPDATE candidates SET campaign=? WHERE id=?", [(camp, i) for i in ids])
                st.success("Campaign assigned.")
    with right:
        if sel_id:
            render_candidate(sel_id)

def render_candidate(cid:int):
    conn = db.get_db(); conn.row_factory = sqlite3.Row; cur = conn.cursor()
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
        status = col[2].selectbox("Status", ["Applied","Interviewed","Hired","Rejected"], index=["Applied","Interviewed","Hired","Rejected"].index(cand["status"]) if cand["status"] in ["Applied","Interviewed","Hired","Rejected"] else 0)
        avail  = st.text_input("Availability", value=cand["availability"] or "")
        src    = st.text_input("Source", value=cand["source"] or "")
        notes  = st.text_area("Notes", value=cand["notes"] or "")
        dnc_col = st.columns(3)
        dnc_val = dnc_col[0].checkbox("Do Not Call", value=bool(cand["dnc"]))
        dnc_reason = dnc_col[1].text_input("DNC reason", value=cand["dnc_reason"] or "")
        if role_can_edit() and st.button("Save details"):
            with db.get_db() as con:
                con.execute("""UPDATE candidates
                              SET notice_period=?, planned_leave=?, status=?, availability=?, source=?, notes=?,
                                  dnc=?, dnc_reason=?, updated_at=CURRENT_TIMESTAMP
                              WHERE id=?""", (notice or None, leave or None, status, avail or None, src or None, notes or None, int(dnc_val), dnc_reason or None, cid))
            st.success("Saved.")

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
            keywords = db.get_setting("keywords", SEED_KEYWORDS)
            tier, flags = score_cv(text, keywords)
            with db.get_db() as con:
                con.execute("UPDATE candidates SET score_tier=?, flags_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (tier, json.dumps(flags), cid))
                con.execute("INSERT INTO attachments(candidate_id,filename,path,doc_type) VALUES(?,?,?,?)",
                            (cid, cv.name, path, "CV"))
            st.success(f"Scored: {tier} ({flags.get('score_pct','?')}%)")
            st.rerun()

    # TestGorilla
    with tabs[2]:
        up = st.file_uploader("Upload TestGorilla Excel", type=["xlsx"])
        if role_can_edit() and up and st.button("Import TestGorilla"):
            n = ingest_testgorilla(up)
            st.success(f"Imported {n} rows (matched to candidates).")
        with db.get_db() as con:
            df = pd.read_sql_query("SELECT test_name, score_raw, score_pct, imported_at FROM test_scores WHERE candidate_id=? ORDER BY imported_at DESC", con, params=(cid,))
        st.dataframe(df, use_container_width=True)

    # Interview Notes
    with tabs[3]:
        up = st.file_uploader("Upload Interview Notes (MS Forms export .xlsx)", type=["xlsx"])
        if role_can_edit() and up and st.button("Import Interview Notes"):
            n = ingest_interview_notes(up)
            st.success(f"Processed {n} interview notes row(s).")
            st.rerun()
        with db.get_db() as con:
            df = pd.read_sql_query("""SELECT id, filename, uploaded_at FROM attachments
                                      WHERE candidate_id=? AND doc_type='Interview Notes'
                                      ORDER BY uploaded_at DESC""", con, params=(cid,))
        st.dataframe(df, use_container_width=True)

    # Attachments
    with tabs[4]:
        up = st.file_uploader("Add attachment", key=f"att_{cid}")
        dtype = st.selectbox("Type", ["CV","Visa","Speed Test","Interview Notes","Other"], key=f"dtype_{cid}")
        if role_can_edit() and up and st.button("Upload attachment"):
            raw = up.read(); path = os.path.join(UPLOAD_DIR, up.name)
            with open(path, "wb") as f: f.write(raw)
            with db.get_db() as con:
                con.execute("INSERT INTO attachments(candidate_id,filename,path,doc_type) VALUES(?,?,?,?)",
                            (cid, up.name, path, dtype))
            st.success("Saved."); st.rerun()
        with db.get_db() as con:
            df = pd.read_sql_query("SELECT id,filename,doc_type,uploaded_at FROM attachments WHERE candidate_id=? ORDER BY uploaded_at DESC", con, params=(cid,))
        st.dataframe(df, use_container_width=True)

    # Notes
    with tabs[5]:
        st.text_area("Notes", value=cand["notes"] or "", key=f"notes_{cid}")
        if role_can_edit() and st.button("Save notes"):
            with db.get_db() as con:
                con.execute("UPDATE candidates SET notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (st.session_state[f'notes_{cid}'], cid))
            st.success("Saved.")

    # Audit
    with tabs[6]:
        with db.get_db() as con:
            df = pd.read_sql_query("SELECT action, target, meta_json, at FROM audit_logs WHERE target=? ORDER BY at DESC", con, params=(f'candidate:{cid}',))
        st.dataframe(df, use_container_width=True)

    # Compliance
    with tabs[7]:
        st.markdown(compliance_text())

def page_dnc():
    st.markdown("### Do Not Call")
    with db.get_db() as con:
        df = pd.read_sql_query("SELECT id,name,email,county,dnc_reason,updated_at FROM candidates WHERE dnc=1 ORDER BY updated_at DESC", con)
    st.dataframe(df, use_container_width=True)
    if role_can_edit():
        cid = st.number_input("Restore candidate ID", min_value=0, step=1)
        if st.button("Restore") and cid:
            with db.get_db() as con:
                con.execute("UPDATE candidates SET dnc=0, dnc_reason=NULL WHERE id=?", (int(cid),))
            st.success("Restored.")

def page_keywords():
    st.markdown("### Keywords")
    cur = db.get_setting("keywords", None) or SEED_KEYWORDS
    tabs = st.tabs(list(cur.keys()))
    for i, k in enumerate(cur.keys()):
        v = "\n".join(cur[k])
        cur[k] = [w.strip() for w in tabs[i].text_area(k, v, height=200).splitlines() if w.strip()]
    if role_is_admin() and st.button("Save keywords"):
        db.set_setting("keywords", cur); st.success("Saved.")

def page_hiring_areas():
    st.markdown("### Hiring Areas (blocked counties)")
    with db.get_db() as con:
        df = pd.read_sql_query("SELECT county FROM blocked_counties ORDER BY county", con)
    st.dataframe(df, use_container_width=True)
    if role_is_admin():
        newc = st.text_input("Add county")
        c1, c2 = st.columns(2)
        if c1.button("Add") and newc:
            with db.get_db() as con:
                con.execute("INSERT OR IGNORE INTO blocked_counties(county) VALUES(?)", (newc.strip(),))
            st.success("Added."); st.rerun()
        if c2.button("Apply rule to candidates"):
            with db.get_db() as con:
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
        st.warning("Admin only.")
        return
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
        if not em or not pw1 or pw1!=pw2: st.error("Check inputs.")
        else:
            try:
                create_user(em, nm, pw1, rl); st.success("User created.")
            except Exception as e:
                st.error(str(e))
    st.subheader("Users")
    st.dataframe(list_users(), use_container_width=True)
    st.subheader("Retention")
    if st.button("Purge candidates older than 2 years"):
        n = db.purge_older_than_years(2); st.success(f"Purged {n} candidate(s).")

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

# ---------- Router ----------
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
