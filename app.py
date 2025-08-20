# app.py — PulseHire main app with working login, first-run setup, and logo upload
import os
import base64
import streamlit as st

from db import init_db, get_setting, set_setting
from auth import (
    verify_password,
    create_user,
    users_exist,
    seed_admin_if_empty,
    set_password,
)
from theme import apply_theme, BRAND

# ---------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------
apply_theme()            # page config + basic CSS
init_db()                # ensure SQLite schema exists
seed_admin_if_empty()    # seeds admin@pulsehire.local / admin if no users

RESET_KEY = "PULSEHIRE_RESET"   # change after first login


# ---------------------------------------------------------------------
# Logo helpers (prefer DB-stored base64, else file, else text)
# ---------------------------------------------------------------------
def render_logo(width: int = 140):
    logo_b64 = get_setting("logo_b64")
    if logo_b64:
        try:
            st.image(base64.b64decode(logo_b64), width=width)
            return
        except Exception:
            pass
    # fallback to file on disk
    logo_path = BRAND.get("logo_path", "")
    if logo_path and os.path.exists(logo_path):
        st.image(logo_path, width=width)
    else:
        st.markdown(f"### {BRAND.get('name','PulseHire')}")


# ---------------------------------------------------------------------
# Auth UI (login + troubleshoot + first-time setup)
# ---------------------------------------------------------------------
def first_admin_setup_ui():
    st.markdown("### First-time setup — create Admin")
    with st.form("first_admin"):
        email = st.text_input("Admin email", value="admin@pulsehire.local")
        name = st.text_input("Name", value="Admin")
        pw1 = st.text_input("Password", type="password")
        pw2 = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create Admin", type="primary")
    if submitted:
        if not email or not pw1:
            st.error("Email and password are required.")
            return
        if pw1 != pw2:
            st.error("Passwords do not match.")
            return
        try:
            create_user(email, name or "Admin", "admin", pw1)
            st.success("Admin created. Please log in.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to create admin: {e}")


def login_ui():
    # Header
    c1, c2 = st.columns([0.2, 0.8])
    with c1:
        render_logo(140)
    with c2:
        st.markdown(f"## {BRAND.get('name','PulseHire')}")
        st.caption("Sign in with your email and password")

    # Login form
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Sign in", type="primary", use_container_width=True):
        user = verify_password(email, password)
        if user:
            st.session_state["user"] = user.__dict__
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.divider()

    # Troubleshooting tools (no login required)
    with st.expander("Troubleshoot / Setup"):
        st.caption("If default seeding failed or you forgot the admin password:")

        k = st.text_input("Reset key", help="Default is PULSEHIRE_RESET (change later)")
        new_pw = st.text_input("New admin password", type="password")
        if st.button("Reset admin password"):
            if k != RESET_KEY or not new_pw:
                st.error("Reset key incorrect or new password blank.")
            else:
                updated = set_password("admin@pulsehire.local", new_pw)
                if updated:
                    st.success("Admin password reset. Log in with the new password.")
                else:
                    st.info("Admin user not found — create the first admin below.")

        st.markdown("---")
        st.caption("Or create the first Admin (only appears if there are no users):")
        if not users_exist():
            first_admin_setup_ui()

        st.markdown("---")
        st.caption("Upload logo once (stored in app settings; no assets folder needed).")
        up = st.file_uploader("PNG/JPG logo", type=["png", "jpg", "jpeg"])
        if up and st.button("Save logo"):
            try:
                set_setting("logo_b64", base64.b64encode(up.read()).decode())
                st.success("Logo saved. Reload the page to see it.")
            except Exception as e:
                st.error(f"Failed to save logo: {e}")

    # Helper note
    st.caption(
        "Tip: default admin (if seeded) is **admin@pulsehire.local / admin**. "
        "If not working, use Troubleshoot → Reset admin password or create the first admin."
    )


# ---------------------------------------------------------------------
# Main App Shell (shown after login)
# ---------------------------------------------------------------------
def app_shell():
    # Header bar
    col1, col2, col3 = st.columns([0.15, 0.55, 0.30])
    with col1:
        render_logo(120)
    with col2:
        st.markdown(f"### {BRAND.get('name','PulseHire')}")
    with col3:
        user = st.session_state.get("user")
        if user:
            st.write(f"**{user['name']}** · {user['role'].title()}")
            if st.button("Sign out"):
                st.session_state.pop("user", None)
                st.rerun()

    st.divider()
    st.success("You’re logged in. Main navigation (Candidates, Campaigns, etc.) comes next.")
    st.info("This starter focuses on reliable login + logo so you can deploy right now.")


# ---------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------
if "user" not in st.session_state:
    login_ui()
else:
    app_shell()
