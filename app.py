import streamlit as st
from auth import login_user, ensure_admin_exists
from theme import apply_theme
import db

# Initialize DB and ensure admin exists
db.init_db()
ensure_admin_exists()

# Apply branding/theme
apply_theme()

st.sidebar.image("assets/pulsehire_logo.png", caption="PulseHire", use_column_width=True)

# Session state for login
if "user" not in st.session_state:
    st.session_state["user"] = None

if st.session_state["user"] is None:
    st.title("🔐 PulseHire Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = login_user(email, password)
        if user:
            st.session_state["user"] = user
            st.success(f"Welcome {user['name']}!")
            st.experimental_rerun()
        else:
            st.error("Invalid credentials")
else:
    st.sidebar.success(f"Logged in as {st.session_state['user']['name']}")
    st.title("🎉 PulseHire")
    st.write("You are logged in. ATS features will go here.")
    if st.button("Logout"):
        st.session_state["user"] = None
        st.experimental_rerun()
