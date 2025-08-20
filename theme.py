import streamlit as st

def apply_theme():
    st.set_page_config(page_title="PulseHire", page_icon="💚", layout="wide")
    st.markdown(
        """
        <style>
        body {
            font-family: 'Nunito', sans-serif;
        }
        </style>
        """, unsafe_allow_html=True
    )
