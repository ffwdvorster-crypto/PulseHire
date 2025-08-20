import os
import streamlit as st
from auth import login_screen, get_current_user, sign_out_button
from db import init_db, seed_admin_if_empty
from theme import apply_theme, BRAND

# --- Init DB and seed default admin
init_db()
seed_admin_if_empty()

# --- Theme
apply_theme()

# --- Header with logo + title + user
col1, col2, col3 = st.columns([0.15, 0.55, 0.30])
with col1:
    if os.path.exists(BRAND["logo_path"]):
        st.image(BRAND["logo_path"], width=120)
with col2:
    st.markdown(f"<h1 style='margin-bottom:0'>{BRAND['name']}</h1>", unsafe_allow_html=True)
with col3:
    user = get_current_user()
    if user:
        st.write(f"**{user['name']}** · {user['role'].title()}")
        sign_out_button()

st.divider()

# --- Auth / Routing
user = get_current_user()
if not user:
    login_screen()
else:
    st.success(f"Welcome {user['name']}! You are logged in as **{user['role']}**.")
    st.write("📋 Main navigation coming next (Candidates, Campaigns, Keywords, etc).")
    st.info("This is the minimal starter so you can deploy immediately.")

