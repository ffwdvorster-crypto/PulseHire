import streamlit as st
import pandas as pd
import db, auth, ingestion, scoring

st.set_page_config(page_title="PulseHire ATS", layout="wide")
import db, auth, ingestion, scoring
db.init_db()
auth.ensure_seed_admin()

# Initialize DB schema first, then seed admin
db.init_db()
auth.ensure_seed_admin()

# --- Navigation ---
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

# --- Session state init ---
if "page" not in st.session_state:
    st.session_state.page = "dashboard"
if "user" not in st.session_state:
    st.session_state.user = None

# --- Sidebar ---
st.sidebar.image("assets/logo.png", width=180)
st.sidebar.title("PulseHire ATS")

if st.session_state.user:
    st.sidebar.markdown(f"**Logged in as {st.session_state.user['email']}**")
    for label, key in NAV_ITEMS:
        if st.sidebar.button(label, key=f"nav_{key}"):
            st.session_state.page = key
    if st.sidebar.button("🚪 Logout"):
        st.session_state.user = None
        st.session_state.page = "dashboard"
else:
    st.sidebar.info("Please login below.")

# --- Pages ---
def dashboard_ui():
    st.title("📊 Dashboard")
    st.write("Welcome to PulseHire ATS! Use the sidebar to navigate.")

def campaigns_ui():
    st.title("🎯 Campaigns")
    st.caption("Manage recruitment campaigns, hours, keywords, and notes.")
    st.download_button("Download CSV Template", data="name,hours,keywords,notes\n", file_name="campaigns_template.csv")

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

def active_ui():
    st.title("🚀 Active Recruitment")
    st.write("View and manage active recruitment projects.")

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
    scoring.show_scoring_ui()

def counties_ui():
    st.title("🗺️ Hiring Areas (Counties)")
    st.caption("Add or remove counties.")
    new = st.text_input("Add counties (comma or ; delimited):")
    if st.button("Add County", key="counties_add"):
        for c in [x.strip() for x in new.replace(";", ",").split(",") if x.strip()]:
            db.add_county(c)
        st.success("Counties added.")
    st.write("**Existing Counties:**")
    st.table(db.get_counties())
    rem = st.selectbox("Remove county:", [c[0] for c in db.get_counties()], key="counties_remove_sel")
    if st.button("Remove Selected County", key="counties_remove_btn"):
        db.remove_county(rem)
        st.success(f"Removed {rem}")

def compliance_ui():
    st.title("⚖️ Compliance")
    st.markdown("""
### Data Protection & Compliance  
At RelateCare we are committed to ensuring compliance with all relevant data protection regulations (including GDPR).  

- Candidate and employee data is stored securely.  
- Access is restricted to authorized personnel only.  
- Data is retained only as long as necessary for recruitment and business needs.  
- You may request access to, correction of, or deletion of your data.  

📩 For any compliance queries, please contact:  
**[compliance@relatecare.com](mailto:compliance@relatecare.com)**
    """)

def changelog_ui():
    st.title("🧾 Changelog")
    st.info("This page will show system updates and changes. (Placeholder)")

def admin_ui():
    st.title("🛠️ Admin")
    st.write("Admin functions for managing users and settings.")

def account_ui():
    st.title("🔑 Account Settings")
    st.write("Change your password here.")
    if st.session_state.user:
        new_pw = st.text_input("New password", type="password", key="pw1")
        if st.button("Change Password", key="pw_change_btn"):
            auth.change_password(st.session_state.user["email"], new_pw)
            st.success("Password changed.")

# --- Routing ---
if not st.session_state.user:
    st.title("Login")
    email = st.text_input("Email", key="login_email")
    pw = st.text_input("Password", type="password", key="login_pw")
    if st.button("Login", key="login_btn"):
        user = auth.login(email, pw)
        if user:
            st.session_state.user = user
            st.success("Logged in!")
            st.rerun()
        else:
            st.error("Invalid credentials")
else:
    page = st.session_state.page
    if page == "dashboard": dashboard_ui()
    elif page == "campaigns": campaigns_ui()
    elif page == "active": active_ui()
    elif page == "candidates_upload": candidates_upload_ui()
    elif page == "imports": imports_ui()
    elif page == "scoring": scoring_ui()
    elif page == "counties": counties_ui()
    elif page == "compliance": compliance_ui()
    elif page == "changelog": changelog_ui()
    elif page == "admin": admin_ui()
    elif page == "account": account_ui()
