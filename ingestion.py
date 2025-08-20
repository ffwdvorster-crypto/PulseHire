import pandas as pd
from typing import Optional
from db import add_candidate, add_test_score, add_interview_note, find_candidate_by_email, get_connection, _exec

def ingest_applications(df: pd.DataFrame, is_test: bool = False):
    expected_cols = {"name","email","phone","source","resume_text","notes"}
    # Attempt to normalize columns
    df_cols = {c.strip().lower(): c for c in df.columns}
    def col(name): return df_cols.get(name, None)
    created = 0
    for _, row in df.iterrows():
        name = row.get(col("name")) if col("name") else row.get("name")
        email = row.get(col("email")) if col("email") else row.get("email")
        phone = row.get(col("phone")) if col("phone") else row.get("phone")
        source = row.get(col("source")) if col("source") else row.get("source")
        resume_text = row.get(col("resume_text")) if col("resume_text") else row.get("resume_text")
        notes = row.get(col("notes")) if col("notes") else row.get("notes")
        add_candidate(name=name, email=email, phone=phone, source=source, resume_text=resume_text, notes=notes, is_test=int(is_test))
        created += 1
    return created

def ingest_testgorilla(df: pd.DataFrame, is_test: bool = False):
    # Expect columns: email, score (or assessment_score)
    df_cols = {c.strip().lower(): c for c in df.columns}
    email_col = df_cols.get("email")
    score_col = df_cols.get("score", df_cols.get("assessment_score"))
    count = 0
    for _, row in df.iterrows():
        email = row.get(email_col) if email_col else None
        score = row.get(score_col) if score_col else None
        if not email:
            continue
        cand = find_candidate_by_email(str(email).strip().lower())
        if not cand:
            # create bare candidate
            cid = add_candidate(name=None, email=str(email).strip().lower(), is_test=int(is_test))
        else:
            cid = cand["id"]
        try:
            sc = float(score) if score is not None and str(score).strip() != "" else None
        except Exception:
            sc = None
        add_test_score(cid, source="TestGorilla", score=sc, is_test=int(is_test))
        count += 1
    return count

def ingest_interview_notes(df: pd.DataFrame, is_test: bool = False):
    # Expect columns: email, notes, date (optional)
    df_cols = {c.strip().lower(): c for c in df.columns}
    email_col = df_cols.get("email")
    notes_col = df_cols.get("notes")
    date_col = df_cols.get("date")
    count = 0
    for _, row in df.iterrows():
        email = row.get(email_col) if email_col else None
        notes = row.get(notes_col) if notes_col else None
        date = row.get(date_col) if date_col else None
        if not email or not notes:
            continue
        cand = find_candidate_by_email(str(email).strip().lower())
        if not cand:
            cid = add_candidate(name=None, email=str(email).strip().lower(), is_test=int(is_test))
        else:
            cid = cand["id"]
        add_interview_note(cid, notes=notes, date=date, is_test=int(is_test))
        count += 1
    return count