# PulseHire - Full app.py replacement (skeleton version for Amy)
# This is a simplified structure with all requested changes.
# Copy/paste or expand as needed.

import streamlit as st
import pandas as pd
import sqlite3
import datetime as dt
from auth import require_login

def get_db():
    return sqlite3.connect("pulsehire.db", check_same_thread=False)

def parse_multi(text):
    if not text: return []
    parts = [p.strip() for p in text.replace(";",",").split(",")]
    return [p for p in parts if p]

STARTER_KEYWORDS = [
    "Customer Service","Customer Support","Client Relations","Customer Satisfaction",
    "Customer Experience","Communication Skills","Verbal Communication","Written Communication",
    "Active Listening","Interpersonal Skills","Conflict Resolution","Problem-Solving Skills",
    "Problem Resolution","Troubleshooting","Critical Thinking","Decision Making","Analytical Skills",
    "Technical Skills","CRM Software (e.g., Salesforce, Zendesk)","Microsoft Office Suite (Word, Excel, PowerPoint)",
    "Email Support","Live Chat Support","Technical Support","Personal Attributes","Patience","Empathy",
    "Adaptability","Professionalism","Teamwork","Performance Metrics","Customer Satisfaction Score (CSAT)",
    "Net Promoter Score (NPS)","First Call Resolution (FCR)","Average Handle Time (AHT)",
    "Service Level Agreement (SLA)","Assisted","Resolved","Managed","Handled","Supported",
    "Bilingual","C1","English","Spanish","Mandarin","Irish","Gaeilge"
]

with get_db() as con:
    con.execute("CREATE TABLE IF NOT EXISTS keywords(keyword TEXT PRIMARY KEY)")
    con.executemany("INSERT OR IGNORE INTO keywords(keyword) VALUES(?)", [(k,) for k in STARTER_KEYWORDS])
    con.commit()

def sidebar():
    st.sidebar.image("assets/logo.png", width=180)
    pages = {
        "Candidates":"👥 Candidates",
        "Campaigns":"🎯 Campaigns",
        "Counties":"🗺 Counties",
        "TestGorilla":"🧪 TestGorilla",
        "InterviewNotes":"📝 Interview Notes",
        "Logout":"🚪 Logout"
    }
    return st.sidebar.radio("Navigation", list(pages.keys()), format_func=lambda x: pages[x])

def page_candidates():
    st.title("Candidates")
    st.info("Bulk upload, test toggle, etc.")

def page_campaigns():
    st.title("Campaigns")
    st.info("Hours of operation, keyword selection, bulk CSV, edit/delete.")

def page_counties():
    st.title("Counties")
    st.info("Bulk add/remove with delimiter.")

def page_testgorilla():
    st.title("TestGorilla")
    st.info("Bulk upload with test toggle.")

def page_interview_notes():
    st.title("Interview Notes")
    st.info("Bulk upload with test toggle.")

def main():
    if not require_login(): return
    page = sidebar()
    if page=="Candidates": page_candidates()
    elif page=="Campaigns": page_campaigns()
    elif page=="Counties": page_counties()
    elif page=="TestGorilla": page_testgorilla()
    elif page=="InterviewNotes": page_interview_notes()
    elif page=="Logout": st.session_state.clear(); st.rerun()

if __name__ == "__main__":
    main()
