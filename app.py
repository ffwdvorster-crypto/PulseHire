import streamlit as st
from auth import login_screen, require_login
from db import init_db, get_connection
import pandas as pd
import os
import base64
from datetime import datetime

# ========== INIT ==========
init_db()

# ========== LOGO HEADER ==========
def show_logo():
    logo_path = os.path.join("assets", "pulsehire_logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=200)
    else:
        st.markdown("### PulseHire")

# ========== SIDEBAR NAV ==========
PAGES = {
    "Dashboard": "📊",
    "Candidates": "👥",
    "Campaigns": "🎯",
    "Do Not Call": "🚫",
    "Keywords": "📝",
    "Hiring Areas": "🗺️",
    "Compliance": "⚖️",
    "Changelog": "📜",
}

def sidebar_nav():
    st.sidebar.title("Navigation")
    choice = st.sidebar.radio(
        "", list(PAGES.keys()), format_func=lambda x: f"{PAGES[x]} {x}"
    )
    return choice

# ========== BULK UPLOAD HELPERS ==========
def handle_bulk_upload(file, filetype, test_mode=False):
    conn = get_connection()
    if filetype == "candidates":
        df = pd.read_excel(file)
        df["is_test"] = 1 if test_mode else 0
        df.to_sql("candidates", conn, if_exists="append", index=False)
        st.success(f"{len(df)} candidates uploaded ({'TEST' if test_mode else 'LIVE'})")
    elif filetype == "testgorilla":
        df = pd.read_excel(file)
        df["is_test"] = 1 if test_mode else 0
        df.to_sql("test_scores", conn, if_exists="append", index=False)
        st.success(f"{len(df)} TestGorilla results uploaded ({'TEST' if test_mode else 'LIVE'})")
    elif filetype == "interview_notes":
        df = pd.read_excel(file)
        df["is_test"] = 1 if test_mode else 0
        df.to_sql("interview_notes", conn, if_exists="append", index=False)
        st.success(f"{len(df)} Interview Notes uploaded ({'TEST' if test_mode else 'LIVE'})")

# ========== PAGE HANDLERS ==========
def dashboard():
    st.subheader("📊 Dashboard")
    st.write("Quick stats and summaries will appear here.")

def candidates():
    st.subheader("👥 Candidates")

    # Bulk upload section
    st.markdown("#### Bulk Upload Candidates")
    test_mode = st.checkbox("Upload as Test Data")
    file = st.file_uploader("Upload Application Excel", type=["xlsx"])
    if file:
        if st.button("Upload"):
            handle_bulk_upload(file, "candidates", test_mode)

    # Candidate table
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM candidates", conn)
    st.dataframe(df)

    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv, file_name="candidates.csv", mime="text/csv")

def campaigns():
    st.subheader("🎯 Campaigns")
    conn = get_connection()

    # Upload campaigns by CSV
    st.markdown("#### Bulk Import Campaigns")
    file = st.file_uploader("Upload Campaigns CSV", type=["csv"], key="campaigns_upload")
    if file:
        df = pd.read_csv(file)
        df.to_sql("campaigns", conn, if_exists="append", index=False)
        st.success(f"{len(df)} campaigns uploaded")

    # List campaigns
    df = pd.read_sql("SELECT * FROM campaigns", conn)
    st.dataframe(df)

def dnc_page():
    st.subheader("🚫 Do Not Call List")
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM candidates WHERE dnc=1", conn)
    st.dataframe(df)

def keywords_page():
    st.subheader("📝 Keywords")
    st.write("Editable keyword list will be here.")

def hiring_areas_page():
    st.subheader("🗺️ Hiring Areas")
    st.markdown("#### Bulk Add / Remove Counties")
    conn = get_connection()

    add_input = st.text_area("Add multiple counties (comma or newline separated)")
    if st.button("Add Counties"):
        counties = [c.strip() for c in add_input.replace("\n", ",").split(",") if c.strip()]
        for c in counties:
            conn.execute("INSERT OR IGNORE INTO blocked_counties (county) VALUES (?)", (c,))
        conn.commit()
        st.success(f"Added {len(counties)} counties")

    remove_input = st.text_area("Remove multiple counties (comma or newline separated)")
    if st.button("Remove Counties"):
        counties = [c.strip() for c in remove_input.replace("\n", ",").split(",") if c.strip()]
        for c in counties:
            conn.execute("DELETE FROM blocked_counties WHERE county=?", (c,))
        conn.commit()
        st.success(f"Removed {len(counties)} counties")

    df = pd.read_sql("SELECT * FROM blocked_counties", conn)
    st.dataframe(df)

def compliance_page():
    st.subheader("⚖️ Compliance")
    st.markdown("""
    **Purpose**  
    This portal stores and processes recruitment data to manage candidate pipelines.  

    **Lawful basis**  
    Consent (where captured) and/or Legitimate Interests for recruitment.  

    **Retention**  
    Data retained 2 years, auto-deleted weekly; manual purge option.  
    """)

def changelog_page():
    st.subheader("📜 Changelog")
    st.markdown("- Initial ATS prototype with login, sidebar nav, bulk uploads, campaigns, keywords, and DNC.")

# ========== ROUTER ==========
def main():
    if not require_login():
        return

    show_logo()
    page = sidebar_nav()

    if page == "Dashboard":
        dashboard()
    elif page == "Candidates":
        candidates()
    elif page == "Campaigns":
        campaigns()
    elif page == "Do Not Call":
        dnc_page()
    elif page == "Keywords":
        keywords_page()
    elif page == "Hiring Areas":
        hiring_areas_page()
    elif page == "Compliance":
        compliance_page()
    elif page == "Changelog":
        changelog_page()

if __name__ == "__main__":
    main()
