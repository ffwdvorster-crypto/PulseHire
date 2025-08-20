import streamlit as st

def apply_theme():
    st.set_page_config(page_title="PulseHire", page_icon="💚", layout="wide")
    st.markdown(
        """
        <style>
        :root { --brand-primary: #00b89f; --brand-accent: #ffc600; }
        body, [class*="css"] { font-family: 'Nunito', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
        .block-container { padding-top: 0.75rem; }
        </style>
        """, unsafe_allow_html=True
    )
