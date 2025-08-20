import os
import streamlit as st
from auth import login_user, ensure_admin_exists
import db

# ----- Page + init -----
st.set_page_config(page_title="PulseHire", page_icon="💚", layout="wide")

db.init_db()
ensure_admin_exists()  # seeds admin@pulsehire.local / admin if missing

# ----- Header with left-aligned logo -----
col1, col2 = st.columns([1, 5])
with col1:
    logo_path = "assets/pulsehire_logo.png"
    if os.path.exists(logo_path):
        st.image(logo_path, width=160)
with col2:
    st.markdown("<h1 style='margin-top:20px;'>PulseHire</h1>", unsafe_allow_html=True)

st.divider()

# ----- Session user -----
if "user" not in st.session_state:
    st.session_state["user"] = None

# ----- Auth flow -----
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
    st.sidebar.success(f"Logged in as {st.session_state['user']['name']}")
    st.title("🎉 PulseHire")
    st.write("You are logged in. ATS features will go here.")
    if st.button("Logout"):
        st.session_state["user"] = None
        st.rerun()
