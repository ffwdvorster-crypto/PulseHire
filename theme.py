import streamlit as st

BRAND = {
    "name": "PulseHire",
    "logo_path": "assets/pulsehire_logo.png"
}

def apply_theme():
    st.set_page_config(page_title="PulseHire", page_icon="💚", layout="wide")
    st.markdown(
        """
        <style>
        html, body, [class*="css"]  { font-family: 'Nunito', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
        .block-container { padding-top: 1rem; }
        </style>
        """, unsafe_allow_html=True
    )
