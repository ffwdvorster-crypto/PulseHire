import os
import io
import pandas as pd
import streamlit as st
from datetime import datetime
import db
import auth
import ingestion
import scoring
import toml

# --- Load theme.toml manually (avoids needing .streamlit/config.toml) ---
theme_file = os.path.join(os.path.dirname(__file__), "theme.toml")
if os.path.exists(theme_file):
    theme = toml.load(theme_file).get("theme", {})
    st.set_page_config(
        page_title="PulseHire ATS",
        page_icon="💙",
        layout="wide",
        initial_sidebar_state="expanded"
    )
else:
    st.set_page_config(page_title="PulseHire ATS", page_icon="💙", layout="wide")

# Ensure DB + seed keywords + admin
db.init_db(seed=True, seed_keywords=scoring.DEFAULT_KEYWORDS, seed_admin=True)
auth.ensure_seed_admin()

# --- Utilities ---
def _exists_assets_file(*parts):
    path = os.path.join("assets", *parts)
    return os.path.exists(path), path

# --- Sidebar styling ---
SIDEBAR_CSS = """
<style>
div[data-testid="stSidebar"] .sidebar-btn {
  display:block;width:100%;padding:10px 14px;margin:6px 0;
  background:#1f2630;border:1px solid #2a3340;border-radius:10px;
  color:#e6f5ff;text-decoration:none;cursor:pointer;
  transition:background .15s ease,border-color .15s ease;font-weight:600;
}
div[data-testid="stSidebar"] .sidebar-btn:hover { background:#26303c;border-color:#334154; }
div[data-testid="stSidebar"] .sidebar-btn.active { background:#0e7490;border-color:#0ea5b7;color:#fff; }
.logo-wrap img { max-width:240px; }
</style>
"""
st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)

NAV_ITEMS = [
    ("📊 Dashboard", "dashboard"),
    ("🎯 Campaigns", "campaigns"),
    ("🚀 Active recruitment", "active"),
    ("👥 Candidates", "candidates_upload"),
    ("📥 Ingestion", "ingestion"),
    ("✨ Keywords", "scoring"),
    ("🗺️ Hiring Areas", "counties"),
    ("⚖️ Compliance", "compliance"),
    ("🧾 Changelog", "changelog"),
    ("🛠️ Admin", "admin"),
    ("🔑 Account", "account"),
]

if "nav" not in st.session_state:
    st.session_state.nav = "dashboard"

def sidebar_nav():
    with st.sidebar:
        has_logo, logo_path = _exists_assets_file("logo.png")
        if has_logo:
            st.image(logo_path, use_column_width=False, width=240)
        else:
            st.markdown("### PulseHire")

        st.markdown("---")
        for label, key in NAV_ITEMS:
            if st.button(label, key=f"nav-{key}", use_container_width=True):
                st.session_state.nav = key
                st.rerun()
        st.markdown("---")
        if st.button("Log out", type="secondary", use_container_width=True):
            st.session_state.user = None
            st.rerun()

# --- Pages ---
def dashboard_ui():
    st.title("PulseHire ATS")
    st.subheader("📊 Dashboard")
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        total_candidates = cur.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        total_campaigns = cur.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
        total_tests = cur.execute("SELECT COUNT(*) FROM test_scores").fetchone()[0]
    finally:
        conn.close()
    c1, c2, c3 = st.columns(3)
    c1.metric("Candidates", total_candidates)
    c2.metric("Campaigns", total_campaigns)
    c3.metric("Assessments", total_tests)
    st.caption("Tip: Upload applications in **Candidates**, assessments/notes in **Ingestion**, and manage jobs in **Campaigns**.")

def account_ui():
    st.subheader("👤 Account")
    st.write(f"Signed in as **{st.session_state.user['email']}** (role: {st.session_state.user['role']})")
    with st.form("change_pw"):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        ok = st.form_submit_button("Update Password")
        if ok:
            if auth.change_password(st.session_state.user["email"], old, new):
                st.success("Password updated.")
            else:
                st.error("Password change failed.")

    if st.session_state.user["role"] == "admin":
        st.markdown("---")
        st.subheader("➕ Create user (admin only)")
        with st.form("create_user"):
            e = st.text_input("Email")
            p = st.text_input("Password", type="password")
            r = st.selectbox("Role", ["admin", "user"])
            go = st.form_submit_button("Create")
            if go:
                if auth.user_exists(e):
                    st.warning("User already exists.")
                else:
                    auth.create_user(e, p, role=r)
                    st.success(f"Created user {e}")

def campaigns_ui():
    st.subheader("🎯 Campaigns")
    st.caption("Manage campaigns, hours, keyword focus, and notes.")

    with st.expander("➕ Add campaign"):
        with st.form("add_campaign"):
            name = st.text_input("Campaign name", help="e.g., Telehealth Nurse, Customer Support, etc.")
            hours = st.text_input("Hours", help="e.g., Mon-Fri 09:00-17:00; Weekends 11:00-19:00")
            kws = [k["term"] for k in db.list_keywords()]
            selected = st.multiselect("Keywords (optional)", options=kws, help="Hold CTRL/CMD to select multiple")
            notes = st.text_area("Notes", placeholder="Hiring manager notes, shift exceptions, etc.")
            ok = st.form_submit_button("Add")
            if ok:
                db.add_campaign(name=name, hours=hours, keywords="; ".join(selected) if selected else None, notes=notes)
                st.success("Campaign added.")

    colL, colR = st.columns([1,1])
    with colL:
        st.markdown("**Campaign CSV template**")
        has_tpl, tpl_path = _exists_assets_file("campaigns_template.csv")
        if has_tpl:
            with open(tpl_path, "rb") as f:
                st.download_button("Download campaigns_template.csv", f, file_name="campaigns_template.csv")
        else:
            sample = "name,hours,keywords,notes\nTelehealth Nurse,Mon-Fri 09:00-17:00,\"Customer Service; CRM Software\",Urgent backfill\n"
            st.download_button("Generate template", data=sample.encode("utf-8"),
                               file_name="campaigns_template.csv", mime="text/csv")
    with colR:
        st.markdown("**Import campaigns CSV**")
        up = st.file_uploader("Upload campaigns CSV", type=["csv"], key="campaigns_csv")
        if up is not None:
            try:
                df = pd.read_csv(up)
                required = {"name","hours","keywords","notes"}
                missing = required - set(c.lower() for c in df.columns)
                if missing:
                    st.error(f"Missing columns: {', '.join(sorted(missing))}")
                else:
                    cnt = 0
                    for _, row in df.iterrows():
                        db.add_campaign(
                            name=str(row["name"]) if pd.notna(row["name"]) else None,
                            hours=str(row["hours"]) if pd.notna(row["hours"]) else None,
                            keywords=str(row["keywords"]) if pd.notna(row["keywords"]) else None,
                            notes=str(row["notes"]) if pd.notna(row["notes"]) else None
                        )
                        cnt += 1
                    st.success(f"Imported {cnt} campaign(s).")
            except Exception as e:
                st.error(f"Failed to import: {e}")

    st.markdown("---")
    st.write("**Existing campaigns**")
    rows = db.list_campaigns()
    if rows:
        st.dataframe(pd.DataFrame(rows))
    else:
        st.info("No campaigns yet.")

def active_recruitment_ui():
    st.subheader("🚀 Active recruitment")
    st.caption("Quick view of campaigns for day-to-day use.")
    rows = db.list_campaigns()
    if not rows:
        st.info("No campaigns yet. Add some in **Campaigns**.")
        return
    df = pd.DataFrame(rows)
    q = st.text_input("Filter by name/keywords")
    if q:
        ql = q.lower()
        df = df[df.apply(lambda r: ql in str(r.get("name","")).lower() or ql in str(r.get("keywords","")).lower(), axis=1)]
    st.dataframe(df[["name","hours","keywords","notes","created_at"]].sort_values("created_at", ascending=False))

def counties_ui():
    st.subheader("🗺️ Hiring Areas (Counties)")
    st.caption("Add/remove Irish counties. Multi-add supports commas, semicolons, and new lines.")

    existing = db.list_counties()
    st.write(f"Currently stored: {len(existing)} counties")
    st.dataframe(pd.DataFrame({"County": existing}))

    with st.form("add_counties"):
        block = st.text_area("Add multiple counties",
                             placeholder="Wexford, Dublin; Cork\nSligo",
                             help="Use commas, semicolons, or new lines as delimiters.")
        ok = st.form_submit_button("Add")
        if ok:
            raw = block or ""
            parts = []
            for line in raw.splitlines():
                parts.extend(line.replace(";",",").split(","))
            cleaned = [p.strip() for p in parts if p.strip()]
            db.add_counties(cleaned)
            st.success(f"Added {len(cleaned)} counties (existing duplicates ignored).")

    with st.form("remove_county"):
        to_remove = st.selectbox("Remove a county", options=[""] + existing)
        rem = st.form_submit_button("Remove")
        if rem and to_remove:
            db.remove_county(to_remove)
            st.success(f"Removed {to_remove}")

def candidates_upload_ui():
    st.subheader("👥 Candidates (Applications)")
    st.caption("Bulk upload candidates/applications as CSV.")

    test_flag = st.toggle("Upload as Test", value=False, help="Store uploaded data as test-only.")
    f = st.file_uploader("Upload applications CSV", type=["csv"])
    if f is not None:
        df = pd.read_csv(f)
        st.write("Preview:")
        st.dataframe(df.head(20))
        if st.button("Ingest applications"):
            n = ingestion.ingest_applications(df, is_test=test_flag)
            st.success(f"Ingested {n} application rows.")

def ingestion_ui():
    st.subheader("📥 Ingestion")
    st.caption("Upload TestGorilla results and interview notes.")
    test_flag = st.toggle("Upload as Test", value=False, help="Store uploaded data as test-only.")

    tab1, tab2 = st.tabs(["TestGorilla", "Interview Notes"])

    with tab1:
        tg = st.file_uploader("Upload TestGorilla CSV", type=["csv"], key="tg")
        if tg:
            df = pd.read_csv(tg)
            st.dataframe(df.head(20))
            if st.button("Ingest TestGorilla"):
                n = ingestion.ingest_testgorilla(df, is_test=test_flag)
                st.success(f"Ingested {n} TestGorilla rows.")

    with tab2:
        inv = st.file_uploader("Upload Interview Notes CSV", type=["csv"], key="inv")
        if inv:
            df = pd.read_csv(inv)
            st.dataframe(df.head(20))
            if st.button("Ingest Interview Notes"):
                n = ingestion.ingest_interview_notes(df, is_test=test_flag)
                st.success(f"Ingested {n} interview note rows.")

def scoring_ui():
    st.subheader("✨ Keywords & Scoring")
    st.caption("Fuzzy match resume text against tiered keywords. Add new keywords and rescore.")

    with st.expander("➕ Add keyword"):
        col1, col2 = st.columns([2,1])
        with col1:
            term = st.text_input("Keyword/phrase")
        with col2:
            tier = st.selectbox("Tier", [1,2,3],
                                help="1 = must-have (weight 3), 2 = important (weight 2), 3 = nice (weight 1)")
        notes = st.text_input("Notes (optional)")
        if st.button("Add keyword"):
            if term.strip():
                scoring.add_new_keyword(term.strip(), tier=int(tier), notes=notes or None)
                st.success(f"Added keyword '{term}' (tier {tier}).")

    st.markdown("**Current keywords**")
    st.dataframe(pd.DataFrame(db.list_keywords()))

    st.markdown("---")
    st.subheader("Score candidates")
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, source, resume_text, is_test, created_at FROM candidates ORDER BY id DESC LIMIT 500")
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()

    if not rows:
        st.info("No candidates. Upload some in **Candidates** or via **Ingestion**.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df[["id","name","email","source","is_test","created_at"]])

    to_score = st.multiselect("Select candidates to score", options=df["id"].tolist())
    threshold = st.slider("Match threshold", min_value=70, max_value=100, value=85, step=1)

    if st.button("Run scoring") and to_score:
        results = []
        for cid in to_score:
            text = df.loc[df["id"] == cid, "resume_text"].values[0]
            total, hits = scoring.score_text(text or "", threshold=threshold)
            results.append({"candidate_id": cid, "score": total, "hits": ", ".join([h['term'] for h in hits])})
        st.success("Scoring complete.")
        st.dataframe(pd.DataFrame(results).sort_values("score", ascending=False))

def compliance_ui():
    st.subheader("⚖️ Compliance")
    st.info("Placeholder — you can implement your checks here.")

def changelog_ui():
    st.subheader("🧾 Changelog")
    st.info("Placeholder — document your changes here.")

def login_ui():
    st.title("🔐 PulseHire Login")
    with st.form("login"):
        email = st.text_input("Email", value="")
        pw = st.text_input("Password", type="password", value="")
        submitted = st.form_submit_button("Sign In")
    if submitted:
        u = auth.verify_user(email, pw)
        if u:
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Invalid email or password.")
    with st.expander("Admin note"):
        st.info("Seeded admin: **admin@pulsehire.local / admin123**")

# --- Auth gate ---
if "user" not in st.session_state:
    st.session_state.user = None
if st.session_state.user is None:
    login_ui()
    st.stop()

# --- Sidebar + router ---
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
elif page == "ingestion":
    ingestion_ui()
elif page == "scoring":
    scoring_ui()
elif page == "counties":
    counties_ui()
elif page == "compliance":
    compliance_ui()
elif page == "changelog":
    changelog_ui()
elif page == "admin":
    st.subheader("🛠️ Admin")
    st.caption("Admin actions are available in the Account page below.")
    st.info("Use **Account → Create user** to add users and **Change password** to rotate credentials.")
elif page == "account":
    account_ui()
