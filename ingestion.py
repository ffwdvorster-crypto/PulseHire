# ingestion.py — TestGorilla + Interview Notes ingest
import io
import pandas as pd
from datetime import datetime, UTC
from typing import Optional
from fpdf import FPDF
from db import connect

def _now(): return datetime.now(UTC).isoformat()

def _norm(s):
    if s is None: return ""
    return "".join(ch for ch in str(s).strip().lower() if ch.isalnum() or ch.isspace())

def _lev(a,b):
    # Levenshtein distance (tiny impl)
    a,b = _norm(a), _norm(b)
    if a==b: return 0
    if not a: return len(b)
    if not b: return len(a)
    dp = list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        prev, dp[0] = dp[0], i
        for j,cb in enumerate(b,1):
            cur = dp[j]
            cost = 0 if ca==cb else 1
            dp[j] = min(dp[j]+1, dp[j-1]+1, prev+cost)
            prev = cur
    return dp[-1]

def _find_candidate_by_email(email) -> Optional[int]:
    if not email: return None
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id FROM candidates WHERE LOWER(email)=LOWER(?)", (email,))
        row = cur.fetchone()
        return row["id"] if row else None

def _find_candidate_by_name(name) -> Optional[int]:
    if not name: return None
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM candidates")
        best = (None, 999)
        for row in cur.fetchall():
            d = _lev(name, row["name"])
            if d < best[1]:
                best = (row["id"], d)
        return best[0] if best[1] <= 2 else None

def import_testgorilla(xlsx_file):
    df = pd.read_excel(xlsx_file)
    # try common columns
    cols = df.columns.str.lower().tolist()
    # heuristics
    candidate_email_col = next((c for c in df.columns if "email" in c.lower()), None)
    candidate_name_col  = next((c for c in df.columns if "name" in c.lower()), None)
    test_name_col       = next((c for c in df.columns if "test" in c.lower() and "name" in c.lower()), None)
    score_pct_col       = next((c for c in df.columns if "%” in c or “percent" in c.lower() or "score" in c.lower()), None)
    percentile_col      = next((c for c in df.columns if "percentile" in c.lower()), None)

    imported = 0
    with connect() as con:
        cur = con.cursor()
        for _, r in df.iterrows():
            email = str(r.get(candidate_email_col, "")).strip()
            name  = str(r.get(candidate_name_col, "")).strip()
            cand_id = _find_candidate_by_email(email) or _find_candidate_by_name(name)
            if not cand_id:
                continue
            test_name = str(r.get(test_name_col, "")).strip() if test_name_col else "TestGorilla"
            score_pct = None
            if score_pct_col:
                try:
                    score_pct = float(str(r.get(score_pct_col)).replace("%","").strip())
                except Exception:
                    score_pct = None
            percentile = None
            if percentile_col:
                try:
                    percentile = float(str(r.get(percentile_col)).replace("%","").strip())
                except Exception:
                    percentile = None

            cur.execute("""INSERT INTO test_scores(candidate_id,provider,test_name,score_raw,score_pct,imported_at)
                           VALUES(?,?,?,?,?,?)""", (cand_id, "TestGorilla", test_name,
                                                    str(percentile) if percentile is not None else None,
                                                    score_pct, _now()))
            imported += 1
    return imported

def _row_to_pdf_bytes(title: str, series: pd.Series) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, title, ln=1)
    pdf.set_font("Arial", "", 11)
    for k, v in series.items():
        pdf.multi_cell(0, 7, f"{k}: {v}")
    out = pdf.output(dest="S").encode("latin-1")
    return out

def save_attachment(cand_id: int, filename: str, data: bytes, doc_type: str, upload_dir: str):
    import os
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, filename)
    with open(path, "wb") as f:
        f.write(data)
    with connect() as con:
        cur = con.cursor()
        cur.execute("INSERT INTO attachments(candidate_id,filename,path,uploaded_at,doc_type) VALUES(?,?,?,?,?)",
                    (cand_id, filename, path, _now(), doc_type))

def import_interview_notes(xlsx_file, upload_dir: str):
    df = pd.read_excel(xlsx_file)
    # Heuristics for columns
    name_col     = next((c for c in df.columns if "name" in c.lower()), None)
    yesno_col    = next((c for c in df.columns if ("final" in c.lower() or "recommend" in c.lower()) and ("yes" in c.lower() or "pass" in c.lower() or "result" in c.lower() or "outcome" in c.lower())), None)
    notice_col   = next((c for c in df.columns if "how soon" in c.lower() or "notice" in c.lower()), None)
    leave_col    = next((c for c in df.columns if "upcoming" in c.lower() or "leave" in c.lower() or "days off" in c.lower()), None)

    updated = 0
    with connect() as con:
        cur = con.cursor()
        for _, r in df.iterrows():
            name = str(r.get(name_col, "")).strip()
            cand_id = _find_candidate_by_name(name)
            if not cand_id:
                continue
            # interview pass?
            status = str(r.get(yesno_col, "")).strip().lower() if yesno_col else ""
            passed = ("yes" in status) or ("pass" in status)
            if passed:
                cur.execute("UPDATE candidates SET status=?, updated_at=? WHERE id=?",
                            ("Interviewed", _now(), cand_id))

            notice = str(r.get(notice_col, "")).strip() if notice_col else ""
            leave  = str(r.get(leave_col, "")).strip() if leave_col else ""
            if notice or leave:
                cur.execute("UPDATE candidates SET notice_period=?, planned_leave=?, updated_at=? WHERE id=?",
                            (notice or None, leave or None, _now(), cand_id))

            # Save PDF of full row to attachments
            pdf_bytes = _row_to_pdf_bytes("Interview Notes", r)
            filename = f"interview_notes_{cand_id}_{_._name if hasattr(_, '_name') else 'row'}.pdf"
            save_attachment(cand_id, filename, pdf_bytes, "Interview Notes", upload_dir)
            updated += 1
    return updated
