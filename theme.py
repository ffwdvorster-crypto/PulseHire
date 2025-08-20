# theme.py
import streamlit as st
from db import get_setting

BRAND = {"name": "PulseHire", "logo_path": "assets/pulsehire_logo.png"}

def apply_theme():
    st.set_page_config(page_title="PulseHire", page_icon="💚", layout="wide")
    st.markdown("""<style>html,body,[class*='css']{font-family:'Nunito',sans-serif}</style>""",
                unsafe_allow_html=True)

def render_logo():
    # Prefer logo stored in DB (base64), fallback to file, fallback to text
    logo_b64 = get_setting("logo_b64")
    if logo_b64:
        import base64
        st.image(base64.b64decode(logo_b64), width=140)
        return
    import os
    if os.path.exists(BRAND["logo_path"]):
        st.image(BRAND["logo_path"], width=140)
    else:
        st.markdown(f"### {BRAND['name']}")
