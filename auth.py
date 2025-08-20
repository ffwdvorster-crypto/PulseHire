import streamlit as st
from werkzeug.security import check_password_hash
from db import get_user_by_email

SESSION_KEY = "pulsehire_user"

def login_screen():
    st.subheader("🔑 Login to PulseHire")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        user = get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            st.session_state[SESSION_KEY] = {k: user[k] for k in ("id","email","name","role")}
            st.rerun()
        else:
            st.error("❌ Invalid credentials")

def get_current_user():
    return st.session_state.get(SESSION_KEY)

def sign_out_button():
    if st.button("Sign out"):
        st.session_state.pop(SESSION_KEY, None)
        st.rerun()
