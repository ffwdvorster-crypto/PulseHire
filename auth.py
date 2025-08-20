import streamlit as st

# Always-available default admin account
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"

def require_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "username" not in st.session_state:
        st.session_state.username = None

    if not st.session_state.logged_in:
        st.title("🔑 PulseHire Login")

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Login successful ✅")
                st.rerun()
            else:
                st.error("Invalid username or password")

        return False

    # Already logged in
    st.sidebar.success(f"Logged in as {st.session_state.username}")
    return True
