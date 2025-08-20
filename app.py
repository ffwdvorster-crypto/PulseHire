from auth import verify_password, create_user, users_exist, seed_admin_if_empty, set_password
from db import init_db
import streamlit as st

# init + seed
init_db()
seed_admin_if_empty()

RESET_KEY = "PULSEHIRE_RESET"  # temporary guard for emergency reset

def first_admin_setup_ui():
    st.markdown("### First-time setup — create Admin")
    with st.form("first_admin"):
        email = st.text_input("Admin email", value="admin@pulsehire.local")
        name  = st.text_input("Name", value="Admin")
        pw1   = st.text_input("Password", type="password")
        pw2   = st.text_input("Confirm password", type="password")
        submit = st.form_submit_button("Create Admin", type="primary")
    if submit:
        if not email or not pw1:
            st.error("Email and password required.")
            return
        if pw1 != pw2:
            st.error("Passwords do not match.")
            return
        create_user(email, name or "Admin", "admin", pw1)
        st.success("Admin created. Please log in.")
        st.rerun()

def login_ui():
    st.markdown("### Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Sign in", type="primary", use_container_width=True):
        user = verify_password(email, password)
        if user:
            st.session_state["user"] = user.__dict__
            st.rerun()
        else:
            st.error("Invalid credentials")

    with st.expander("Troubleshoot"):
        st.caption("If default seeding failed or you forgot the admin password:")
        k = st.text_input("Reset key")
        new_pw = st.text_input("New admin password", type="password")
        if st.button("Reset admin password") and k == RESET_KEY and new_pw:
            updated = set_password("admin@pulsehire.local", new_pw)
            if updated:
                st.success("Admin password reset. Log in with the new password.")
            else:
                st.info("Admin user not found — create first admin below.")
        st.caption("Or create the first Admin if there are no users:")

        if not users_exist():
            first_admin_setup_ui()

# on load:
if "user" not in st.session_state:
    login_ui()
else:
    # ... your normal app
    pass
