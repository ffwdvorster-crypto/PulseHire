import os
import streamlit as st
import db
from auth import (
    login_user,
    ensure_admin_exists,
    create_user,
    change_password,
    list_users,
)

# ----- Page setup & init -----
st.set_page_config(page_title="PulseHire", page_icon="💚", layout="wide")
db.init_db()
ensure_admin_exists()  # seeds admin@pulsehire.local / admin if missing

# ----- Header: logo only (left-aligned, ~2× bigger) -----
logo_path = "assets/pulsehire_logo.png"
col_logo, _ = st.columns([1, 5])
with col_logo:
    if os.path.exists(logo_path):
        st.image(logo_path, width=320)  # bigger logo
    else:
        st.info("Upload your logo to assets/pulsehire_logo.png")

st.divider()

# ----- Session user -----
if "user" not in st.session_state:
    st.session_state["user"] = None

# ----- Login flow -----
if st.session_state["user"] is None:
    st.subheader("🔐 Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login", type="primary"):
        user = login_user(email, password)
        if user:
            st.session_state["user"] = user
            st.success(f"Welcome {user['name']}!")
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.caption("Default admin: **admin@pulsehire.local** / **admin**")
else:
    user = st.session_state["user"]

    # Sidebar: show who is logged in + logout
    with st.sidebar:
        st.success(f"Logged in as {user['name']} ({user['role']})")
        if st.button("Log out"):
            st.session_state["user"] = None
            st.rerun()

    # Main tabs
    tabs = st.tabs(["Dashboard", "Account", "Admin" if user["role"] == "admin" else "—"])

    # Dashboard (placeholder)
    with tabs[0]:
        st.markdown("### 🎉 PulseHire")
        st.write("Auth is working. We’ll plug the ATS screens here next.")

    # Account: change own password
    with tabs[1]:
        st.markdown("### Account")
        st.write("Change your password")
        with st.form("change_pw"):
            new1 = st.text_input("New password", type="password")
            new2 = st.text_input("Confirm new password", type="password")
            submitted = st.form_submit_button("Update password")
        if submitted:
            if not new1:
                st.error("Password cannot be empty.")
            elif new1 != new2:
                st.error("Passwords do not match.")
            else:
                rows = change_password(user_id=user["id"], new_password=new1)
                if rows:
                    st.success("Password updated. Please use the new password next time you log in.")
                else:
                    st.error("Failed to update password.")

    # Admin: create users + view list (admin only)
    if user["role"] == "admin":
        with tabs[2]:
            st.markdown("### Admin")
            st.subheader("Create a new user")
            with st.form("create_user"):
                n_email = st.text_input("Email")
                n_name = st.text_input("Name")
                n_role = st.selectbox("Role", ["recruiter","hr","viewer","admin"], index=0)
                n_pw1 = st.text_input("Password", type="password")
                n_pw2 = st.text_input("Confirm password", type="password")
                create_submitted = st.form_submit_button("Create user")
            if create_submitted:
                try:
                    if not n_email or not n_pw1:
                        st.error("Email and password are required.")
                    elif n_pw1 != n_pw2:
                        st.error("Passwords do not match.")
                    else:
                        create_user(n_email, n_name, n_pw1, n_role)
                        st.success(f"User {n_email} created with role '{n_role}'.")
                except Exception as e:
                    st.error(str(e))

            st.markdown("---")
            st.subheader("Existing users")
            users = list_users()
            if users:
                st.dataframe(users, use_container_width=True)
            else:
                st.info("No users found.")
