import os
import io
import pandas as pd
import streamlit as st
from datetime import datetime
import db
import auth
import ingestion
import scoring

st.set_page_config(page_title="PulseHire ATS", page_icon="💙", layout="wide")

# Ensure DB + seed keywords + admin
db.init_db(seed=True, seed_keywords=scoring.DEFAULT_KEYWORDS, seed_admin=True)
auth.ensure_seed_admin()

# Sidebar logo
with st.sidebar:
    st.image(os.path.join("assets","logo.png"), use_column_width=False, width=240)  # ~2x
    st.markdown("---")

# --- Session auth ---
if "user" not in st.session_state:
    st.session_state.user = None

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

def account_ui():
    st.subheader("👤 Account")
    st.write(f"Signed in as **{st.session_state.user['email']}** (role: {st.session_state.user['role']})")
    with st.form("change_pw"):
        st.write("Change password")
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        ok = st.form_submit_button("Update Password")
        if ok:
            if auth.change_password(st.session_state.user["email"], old, new):
                st.success("Password updated.")
            else:
                st.error("Password change failed. Check your current password.")

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

    if st.button("Sign out", type="secondary"):
        st.session_state.user = None
        st.rerun()

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

    st.markdown("**Download CSV template**")
    with open(os.path.join("assets","campaigns_template.csv"), "rb") as f:
        st.download_button("Download campaigns_template.csv", f, file_name="campaigns_template.csv")

    st.markdown("---")
    st.write("**Existing campaigns**")
    rows = db.list_campaigns()
    if rows:
        st.dataframe(pd.DataFrame(rows))
    else:
        st.info("No campaigns yet.")

def counties_ui():
    st.subheader("🗺️ Counties")
    st.caption("Add/remove Irish counties. Multi-add supports commas, semicolons, and new lines.")

    existing = db.list_counties()
    st.write(f"Currently stored: {len(existing)} counties")
    st.dataframe(pd.DataFrame({"County": existing}))

    with st.form("add_counties"):
        block = st.text_area("Add multiple counties", placeholder="Wexford, Dublin; Cork\nSligo", help="Use commas, semicolons, or new lines as delimiters.")
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
    st.subheader("👥 Candidates Upload")
    st.caption("Bulk upload candidates/applications as CSV.")

    test_flag = st.toggle("Upload as Test", value=False, help="Store uploaded data as test-only.")
    f = st.file_uploader("Upload CSV", type=["csv"])
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
    st.subheader("📊 Scoring")
    st.caption("Fuzzy match resume text against tiered keywords. Add new keywords and rescore.")

    # Keyword management
    with st.expander("➕ Add keyword"):
        col1, col2 = st.columns([2,1])
        with col1:
            term = st.text_input("Keyword/phrase")
        with col2:
            tier = st.selectbox("Tier", [1,2,3], help="1 = must-have (weight 3), 2 = important (weight 2), 3 = nice (weight 1)")
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
        st.info("No candidates. Upload some in 'Candidates Upload' or via 'Ingestion'.")
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
    st.subheader("📜 Compliance")
    st.info("Placeholder — you can implement your checks here.")

def changelog_ui():
    st.subheader("🧾 Changelog")
    st.info("Placeholder — document your changes here.")

# --- Navigation ---
if st.session_state.user is None:
    login_ui()
    st.stop()

with st.sidebar:
    section = st.radio("Navigate", [
        "🎯 Campaigns",
        "🗺️ Counties",
        "👥 Candidates Upload",
        "📥 Ingestion",
        "📊 Scoring",
        "📜 Compliance",
        "🧾 Changelog",
        "👤 Account",
    ], label_visibility="collapsed")

st.title("PulseHire ATS")

if section == "🎯 Campaigns":
    campaigns_ui()
elif section == "🗺️ Counties":
    counties_ui()
elif section == "👥 Candidates Upload":
    candidates_upload_ui()
elif section == "📥 Ingestion":
    ingestion_ui()
elif section == "📊 Scoring":
    scoring_ui()
elif section == "📜 Compliance":
    compliance_ui()
elif section == "🧾 Changelog":
    changelog_ui()
elif section == "👤 Account":
    account_ui()