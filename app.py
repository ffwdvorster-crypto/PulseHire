import streamlit as st
from PIL import Image
from auth import login_screen

def main():
    st.set_page_config(page_title="PulseHire", page_icon="💚", layout="wide")

    # Top header with logo left aligned
    col1, col2 = st.columns([1, 5])
    with col1:
        try:
            logo = Image.open("assets/pulsehire_logo.png")
            st.image(logo, width=160)
        except FileNotFoundError:
            st.error("Logo not found. Please upload assets/pulsehire_logo.png")
    with col2:
        st.markdown("<h1 style='margin-top:20px;'>PulseHire</h1>", unsafe_allow_html=True)

    # Check login
    user = login_screen()

    if user:  # login successful
        st.success(f"Welcome, {user['name']} 👋")
        st.markdown("### Dashboard")
        st.info("This is where your candidate table, campaigns, and DNC will appear.")
    else:
        st.warning("Please log in to continue.")

if __name__ == "__main__":
    main()
