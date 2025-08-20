
import os
from datetime import datetime, time

import pandas as pd
import streamlit as st

import db
import auth
import ingestion
import scoring

# --------------------------------------------------------------------------------------
# Page config
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="PulseHire ATS", page_icon="💙", layout="wide", initial_sidebar_state="expanded")

# Ensure DB + seed admin (safe if already exists)
try:
    db.init_db()
except Exception:
    pass
try:
    auth.ensure_seed_admin()
except Exception:
    pass

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _assets_path(filename: str) -> str:
    return os.path.join("assets", filename)

def _has_asset(filename: str) -> bool:
    return os.path.exists(_assets_path(filename))

# --------------------------------------------------------------------------------------
# Sidebar navigation (edge-to-edge buttons + centered logo)
# --------------------------------------------------------------------------------------
SIDEBAR_CSS = """
<style>
/* Sidebar tweaks */
[data-testid="stSidebar"] .ph-logo-wrap {
  display:flex;
  justify-content:center;
  align-items:center;
  padding: 12px 8px 16px 8px;
}
[data-testid="stSidebar"] .ph-logo-wrap img {
  display:block;
  max-width: 320px; /* ~2x typical logo */
  width: 100%;
  height: auto;
}

/* Edge-to-edge buttons with equal sizes */
[data-testid="stSidebar"] .ph-nav button {
  width: 100% !important;
  border-radius: 12px;
  padding: 10px 14px;
  margin: 6px 0;
  border: 1px solid #2a3340;
  background: #1f2630;
  color: #e6f5ff;
  font-weight: 600;
}
[data-testid="stSidebar"] .ph-nav button:hover {
  background: #26303c;
  border-color: #334154;
}
</style>
"""
st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)

NAV_ITEMS = [
    ("📊 Dashboard", "dashboard"),
    ("🎯 Campaigns", "campaigns"),
    ("🚀 Active recruitment", "active"),
    ("👥 Candidates", "candidates_upload"),
    ("📥 Imports", "imports"),
    ("✨ Keywords", "scoring"),
    ("🗺️ Hiring Areas", "counties"),
    ("⚖️ Compliance", "compliance"),
    ("🧾 Changelog", "changelog"),
    ("🛠️ Admin", "admin"),
    ("🔑 Account", "account"),
]

if "nav" not in st.session_state:
    st.session_state.nav = "dashboard"
if "user" not in st.session_state:
    st.session_state.user = None

def sidebar_nav():
    with st.sidebar:
        # Centered logo (transparent background recommended in your file)
        st.markdown('<div class="ph-logo-wrap">', unsafe_allow_html=True)
        if _has_asset("logo.png"):
            st.image(_assets_path("logo.png"), use_column_width=True)
        else:
            st.markdown("### PulseHire")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="ph-nav">', unsafe_allow_html=True)
        for label, key in NAV_ITEMS:
            if st.button(label, key=f"nav_{key}", use_container_width=True):
                st.session_state.nav = key
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.divider()
        if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
            st.session_state.user = None
            st.session_state.nav = "dashboard"
            st.rerun()

# --------------------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------------------
def dashboard_ui():
    st.title("📊 Dashboard")
    conn = db.get_conn()
    cur = conn.cursor()
    try:
        total_candidates = cur.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        total_campaigns  = cur.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
        total_tests      = cur.execute("SELECT COUNT(*) FROM test_scores").fetchone()[0]
    finally:
        conn.close()
    c1, c2, c3 = st.columns(3)
    c1.metric("Candidates", total_candidates)
    c2.metric("Campaigns", total_campaigns)
    c3.metric("Assessments", total_tests)
    st.caption("Use **Candidates** for applications, **Imports** for TestGorilla & Interview Notes, and **Campaigns** to manage jobs.")

def campaigns_ui():
    st.title("🎯 Campaigns")
    st.caption("Create single campaigns or bulk import from CSV.")

    # --- Create single campaign ---
    with st.expander("➕ Create campaign", expanded=True):
        with st.form("create_campaign_form"):
            name   = st.text_input("Campaign name", key="camp_name")
            notes  = st.text_area("Notes", key="camp_notes", placeholder="Hiring manager notes, shift exceptions, etc.")
            # Day selection + time pickers -> hours string
            days = st.multiselect(
                "Days",
                ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
                default=["Mon","Tue","Wed","Thu","Fri"],
                key="camp_days"
            )
            col1, col2 = st.columns(2)
            with col1:
                start_t = st.time_input("Start time", value=time(9,0), key="camp_start")
            with col2:
                end_t   = st.time_input("End time", value=time(17,0), key="camp_end")
            # Keywords list (optional)
            kw_options = [k["term"] for k in db.list_keywords()] if hasattr(db, "list_keywords") else []
            sel_kws = st.multiselect("Keywords (optional)", options=kw_options, key="camp_kws")

            submitted = st.form_submit_button("Create campaign", use_container_width=True)
            if submitted:
                hours = f"{'-'.join(days)} {start_t.strftime('%H:%M')}-{end_t.strftime('%H:%M')}" if days else f"{start_t.strftime('%H:%M')}-{end_t.strftime('%H:%M')}"
                db.add_campaign(name=name, hours=hours, keywords="; ".join(sel_kws) if sel_kws else None, notes=notes)
                st.success(f"Campaign '{name}' created.")

    st.divider()

    # --- Template & Import ---
    colL, colR = st.columns([1,1])
    with colL:
        st.markdown("**Campaign CSV template**")
        sample = "name,hours,keywords,notes\nTelehealth Nurse,Mon-Fri 09:00-17:00,\"Customer Service; CRM Software\",Urgent backfill\n"
        st.download_button("Download template", data=sample.encode("utf-8"),
                           file_name="campaigns_template.csv", mime="text/csv", key="camp_dl_tpl")

    with colR:
        st.markdown("**Import from CSV**")
        up = st.file_uploader("Upload campaigns CSV", type=["csv"], key="campaigns_csv_file")
        if up is not None:
            try:
                df = pd.read_csv(up)
                required = {"name","hours","keywords","notes"}
                cols_lower = {c.lower(): c for c in df.columns}
                missing = required - set(cols_lower.keys())
                if missing:
                    st.error(f"Missing columns: {', '.join(sorted(missing))}")
                else:
                    cnt = 0
                    for _, row in df.iterrows():
                        db.add_campaign(
                            name=str(row[cols_lower["name"]]) if pd.notna(row[cols_lower["name"]]) else None,
                            hours=str(row[cols_lower["hours"]]) if pd.notna(row[cols_lower["hours"]]) else None,
                            keywords=str(row[cols_lower["keywords"]]) if pd.notna(row[cols_lower["keywords"]]) else None,
                            notes=str(row[cols_lower["notes"]]) if pd.notna(row[cols_lower["notes"]]) else None
                        )
                        cnt += 1
                    st.success(f"Imported {cnt} campaign(s).")
            except Exception as e:
                st.error(f"Failed to import: {e}")

    st.markdown("**Existing campaigns**")
    try:
        rows = db.list_campaigns()
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No campaigns yet.")
    except Exception:
        # If list_campaigns not available, display raw query
        conn = db.get_conn()
        df = pd.read_sql_query("SELECT id, name, hours, keywords, notes, created_at FROM campaigns ORDER BY created_at DESC", conn)
        conn.close()
        if df.empty:
            st.info("No campaigns yet.")
        else:
            st.dataframe(df, use_container_width=True)

def active_recruitment_ui():
    st.title("🚀 Active recruitment")
    st.caption("Quick view of campaigns for day-to-day use.")
    try:
        rows = db.list_campaigns()
    except Exception:
        conn = db.get_conn()
        rows = pd.read_sql_query("SELECT id, name, hours, keywords, notes, created_at FROM campaigns ORDER BY created_at DESC", conn).to_dict(orient="records")
        conn.close()
    if not rows:
        st.info("No campaigns yet. Add some in **Campaigns**.")
        return
    df = pd.DataFrame(rows)
    q = st.text_input("Filter by name/keywords", key="active_filter")
    if q:
        ql = q.lower()
        df = df[df.apply(lambda r: ql in str(r.get("name","")).lower() or ql in str(r.get("keywords","")).lower(), axis=1)]
    st.dataframe(df[["name","hours","keywords","notes","created_at"]].sort_values("created_at", ascending=False), use_container_width=True)

def candidates_upload_ui():
    st.title("👥 Candidates (Applications)")
    st.caption("Bulk upload candidates/applications as CSV.")
    test_flag = st.toggle("Upload as Test", value=False, help="Store uploaded data as test-only.", key="apps_test_toggle")
    f = st.file_uploader("Upload applications CSV", type=["csv"], key="apps_file")
    if f is not None:
        df = pd.read_csv(f)
        st.write("Preview:")
        st.dataframe(df.head(20), use_container_width=True)
        if st.button("Ingest applications", key="apps_ingest_btn"):
            n = ingestion.ingest_applications(df, is_test=test_flag)
            st.success(f"Ingested {n} application rows.")

def imports_ui():
    st.title("📥 Imports")
    st.caption("Upload TestGorilla results and interview notes.")
    test_flag = st.toggle("Upload as Test", value=False, help="Store uploaded data as test-only.", key="imports_test_toggle")

    tab1, tab2 = st.tabs(["TestGorilla", "Interview Notes"])

    with tab1:
        tg = st.file_uploader("Upload TestGorilla CSV", type=["csv"], key="imports_tg_file")
        if tg:
            df = pd.read_csv(tg)
            st.dataframe(df.head(20), use_container_width=True)
            if st.button("Import TestGorilla", key="imports_tg_btn"):
                n = ingestion.ingest_testgorilla(df, is_test=test_flag)
                st.success(f"Imported {n} TestGorilla rows.")

    with tab2:
        inv = st.file_uploader("Upload Interview Notes CSV", type=["csv"], key="imports_inv_file")
        if inv:
            df = pd.read_csv(inv)
            st.dataframe(df.head(20), use_container_width=True)
            if st.button("Import Interview Notes", key="imports_inv_btn"):
                n = ingestion.ingest_interview_notes(df, is_test=test_flag)
                st.success(f"Imported {n} interview note rows.")

def scoring_ui():
    st.title("✨ Keywords & Scoring")
    st.caption("Manage keywords and scoring logic.")

    # Keyword management
    with st.expander("➕ Add keyword"):
        col1, col2 = st.columns([2,1])
        with col1:
            term = st.text_input("Keyword/phrase", key="kw_term")
        with col2:
            tier = st.selectbox("Tier", [1,2,3], index=1, key="kw_tier",
                                help="1 = must-have (weight 3), 2 = important (weight 2), 3 = nice (weight 1)")
        notes = st.text_input("Notes (optional)", key="kw_notes")
        if st.button("Add keyword", key="kw_add_btn"):
            term_s = (term or "").strip()
            if term_s:
                if hasattr(scoring, "add_new_keyword"):
                    scoring.add_new_keyword(term_s, tier=int(tier), notes=notes or None)
                elif hasattr(db, "add_keyword"):
                    db.add_keyword(term_s, int(tier), notes or None)
                st.success(f"Added keyword '{term_s}' (tier {tier}).")
            else:
                st.error("Please enter a keyword.")

    # Current keywords
    try:
        kws = db.list_keywords()
    except Exception:
        kws = []
    if kws:
        st.dataframe(pd.DataFrame(kws), use_container_width=True)
    else:
        st.info("No keywords yet (they will seed on first run if your scoring module adds them).")

    # Score candidates
    st.divider()
    st.subheader("Score candidates")
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, source, resume_text, is_test, created_at FROM candidates ORDER BY id DESC LIMIT 500")
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()

    if not rows:
        st.info("No candidates. Upload some in **Candidates** or via **Imports**.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df[["id","name","email","source","is_test","created_at"]], use_container_width=True)

    to_score = st.multiselect("Select candidates to score", options=df["id"].tolist(), key="score_sel")
    threshold = st.slider("Match threshold", min_value=70, max_value=100, value=85, step=1, key="score_thresh")

    if st.button("Run scoring", key="score_btn") and to_score:
        results = []
        for cid in to_score:
            text = df.loc[df["id"] == cid, "resume_text"].values[0]
            total, hits = scoring.score_text(text or "", threshold=threshold)
            results.append({"candidate_id": cid, "score": total, "hits": ", ".join([h['term'] for h in hits])})
        st.success("Scoring complete.")
        st.dataframe(pd.DataFrame(results).sort_values("score", ascending=False), use_container_width=True)

def counties_ui():
    st.title("🗺️ Hiring Areas (Counties)")
    st.caption("Add/remove Irish counties. Multi-add supports commas, semicolons, and new lines.")

    # Existing
    rows = db.get_counties()
    existing = [r[0] if isinstance(r, (list, tuple)) else r for r in rows]
    st.write(f"Currently stored: {len(existing)} counties")
    st.dataframe(pd.DataFrame({"County": existing}), use_container_width=True)

    with st.form("add_counties"):
        block = st.text_area("Add multiple counties", key="counties_block",
                             placeholder="Wexford, Dublin; Cork\nSligo",
                             help="Use commas, semicolons, or new lines as delimiters.")
        ok = st.form_submit_button("Add")
        if ok:
            raw = block or ""
            parts = []
            for line in raw.splitlines():
                parts.extend(line.replace(";",",").split(","))
            cleaned = [p.strip() for p in parts if p.strip()]
            if hasattr(db, "add_counties"):
                db.add_counties(cleaned)
            else:
                for c in cleaned:
                    db.add_county(c)
            st.success(f"Added {len(cleaned)} counties (existing duplicates ignored).")

    with st.form("remove_county"):
        to_remove = st.selectbox("Remove a county", options=[""] + existing, key="counties_rm_sel")
        rem = st.form_submit_button("Remove")
        if rem and to_remove:
            db.remove_county(to_remove)
            st.success(f"Removed {to_remove}")

def compliance_ui():
    st.title("⚖️ Compliance")
    st.markdown("""
## Compliance

**Purpose**  
This portal stores and processes recruitment data to manage candidate pipelines for your organization. It complies with GDPR and internal security standards.

**Lawful basis**  
Consent (where captured) and/or Legitimate Interests for recruitment.

**Data collected**  
Candidate identifiers; application responses; attachments (CV, visa, speed test, interview notes); assessments (TestGorilla); audit logs.

**Security & Access**  
Role‑based access; audit logs; HTTPS; protected storage.

**Retention**  
Data retained **2 years**, auto-deleted weekly; manual purge candidate option; retention actions logged.

**Data subject rights**  
Access, rectification, erasure, restriction, objection, portability. Contact: **compliance@relatecare.com**.

**Automated processing**  
Scoring is advisory only; **no automated rejection**.

**DNC / Exclusions**  
Do Not Call with reason; county-based auto‑DNC with manual override; visa/campaign rules produce flags, not hard rejections.

_Last updated: {}
""".format(datetime.utcnow().date().isoformat()))

def changelog_ui():
    st.title("🧾 Changelog")
    st.info("This page will show system updates and changes. (Placeholder)")

def admin_ui():
    st.title("🛠️ Admin")
    st.caption("Admin actions are available in the Account page below.")
    st.info("Use **Account → Create user** to add users and **Change password** to rotate credentials.")

def account_ui():
    st.title("🔑 Account Settings")
    if not st.session_state.user:
        st.warning("Not signed in.")
        return

    with st.form("pw_change_form"):
        new1 = st.text_input("New password", type="password", key="pw_new_1")
        new2 = st.text_input("Confirm new password", type="password", key="pw_new_2")
        ok = st.form_submit_button("Change Password", use_container_width=True)
        if ok:
            if not new1:
                st.error("Please enter a new password.")
            elif new1 != new2:
                st.error("Passwords do not match.")
            else:
                try:
                    auth.change_password(st.session_state.user["email"], new1)
                    st.success("Password changed.")
                except Exception as e:
                    st.error(f"Password change failed: {e}")

    # Admin create user
    st.divider()
    st.subheader("Create user (admin only)")
    with st.form("create_user_form"):
        e = st.text_input("Email", key="admin_new_email")
        p1 = st.text_input("Password", type="password", key="admin_new_pw1")
        p2 = st.text_input("Confirm password", type="password", key="admin_new_pw2")
        role = st.selectbox("Role", ["admin", "user"], key="admin_new_role")
        go = st.form_submit_button("Create", use_container_width=True)
        if go:
            if p1 != p2:
                st.error("Passwords do not match.")
            elif not e:
                st.error("Email is required.")
            else:
                try:
                    auth.create_user(e, p1)
                    st.success(f"Created user {e}")
                except Exception as ex:
                    st.error(f"Failed to create user: {ex}")

# --------------------------------------------------------------------------------------
# Auth gate
# --------------------------------------------------------------------------------------
def login_ui():
    st.title("🔐 PulseHire Login")
    with st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        pw    = st.text_input("Password", type="password", key="login_pw")
        submitted = st.form_submit_button("Sign In", use_container_width=True)
    if submitted:
        user = auth.login(email, pw)
        if user:
            st.session_state.user = user
            st.success("Logged in.")
            st.rerun()
        else:
            st.error("Invalid credentials.")

if st.session_state.user is None:
    login_ui()
    st.stop()

# --------------------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------------------
sidebar_nav()

page = st.session_state.nav
if page == "dashboard":
    dashboard_ui()
elif page == "campaigns":
    campaigns_ui()
elif page == "active":
    active_recruitment_ui()
elif page == "candidates_upload":
    candidates_upload_ui()
elif page == "imports":
    imports_ui()
elif page == "scoring":
    scoring_ui()
elif page == "counties":
    counties_ui()
elif page == "compliance":
    compliance_ui()
elif page == "changelog":
    changelog_ui()
elif page == "admin":
    admin_ui()
elif page == "account":
    account_ui()
