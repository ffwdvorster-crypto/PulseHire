import io, json, os
import pandas as pd
from rapidfuzz import fuzz, process
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from db import get_db
from scoring import fuzzy_match_name

# ---- TestGorilla ingestion ----
def ingest_testgorilla(xls_file):
    df = pd.read_excel(xls_file)
    cols = {c.lower(): c for c in df.columns}

    # Best-effort column picks
    c_email = next((cols[k] for k in cols if "email" in k), None)
    c_name  = next((cols[k] for k in cols if "name" in k and "test" not in k), None)
    c_tname = next((cols[k] for k in cols if "test" in k and "name" in k), None) or next((cols[k] for k in cols if "assessment" in k), None)
    c_score = next((cols[k] for k in cols if "%score" in k or "score %" in k or "score"==k), None)
    c_pct   = next((cols[k] for k in cols if "percentile" in k), None)

    matched, created = 0, 0
    with get_db() as con:
        cur = con.cursor()
        for _, row in df.iterrows():
            email = str(row.get(c_email, "")).strip().lower() if c_email else ""
            name = str(row.get(c_name, "")).strip()
            # find candidate
            cand_id = None
            if email:
                cur.execute("SELECT id FROM candidates WHERE lower(email)=?", (email,))
                r = cur.fetchone()
                if r: cand_id = r[0]
            if not cand_id and name:
                cur.execute("SELECT id,name FROM candidates")
                allc = cur.fetchall()
                # pick best fuzzy
                best = None; best_score = 0
                for cid, cname in allc:
                    sc = fuzzy_match_name(name, cname)
                    if sc > best_score:
                        best_score = sc; best = cid
                if best_score >= 85:
                    cand_id = best
            if not cand_id:
                continue

            tname = str(row.get(c_tname, "")).strip() if c_tname else ""
            score_raw = str(row.get(c_score, "")).strip() if c_score else ""
            score_pct = None
            try:
                score_pct = float(score_raw)
            except Exception:
                # try to parse like "78%"
                if score_raw.endswith("%"):
                    try: score_pct = float(score_raw[:-1])
                    except Exception: score_pct = None
            percentile = str(row.get(c_pct, "")).strip() if c_pct else ""

            cur.execute("INSERT INTO test_scores(candidate_id,provider,test_name,score_raw,score_pct) VALUES(?,?,?,?,?)",
                        (cand_id,"TestGorilla", tname or None, score_raw or None, score_pct))
            matched += 1
        con.commit()
    return matched

# ---- Interview Notes ingestion ----
def save_row_pdf(filename, row_dict):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 14); c.drawString(50, y, "Interview Notes")
    y -= 20
    c.setFont("Helvetica", 10)
    for k, v in row_dict.items():
        text = f"{k}: {v}"
        for line in wrap_text(text, 100):
            y -= 14
            if y < 60:
                c.showPage(); y = height - 50; c.setFont("Helvetica", 10)
            c.drawString(50, y, line)
    c.save()
    buf.seek(0)
    with open(filename, "wb") as f:
        f.write(buf.read())

def wrap_text(s, width):
    import textwrap
    return textwrap.wrap(s or "", width=width)

def ingest_interview_notes(xls_file):
    df = pd.read_excel(xls_file)
    cols = {c.lower(): c for c in df.columns}
    c_name = next((cols[k] for k in cols if "name" in k), None)

    # heuristics for fields
    key_yes = next((cols[k] for k in cols if "final" in k and ("yes" in k or "decision" in k or "outcome" in k)), None)
    key_notice = next((cols[k] for k in cols if "notice" in k or "how soon" in k or "start" in k), None)
    key_leave  = next((cols[k] for k in cols if "leave" in k or "days off" in k), None)

    updated = 0
    with get_db() as con:
        cur = con.cursor()
        for _, row in df.iterrows():
            name = str(row.get(c_name, "")).strip()
            if not name: continue
            # fuzzy match candidate
            cur.execute("SELECT id,name FROM candidates")
            allc = cur.fetchall()
            best = None; best_score = 0
            for cid, cname in allc:
                sc = fuzz.token_set_ratio(name, cname or "")
                if sc > best_score:
                    best_score = sc; best = cid
            if best_score < 85 or not best:
                continue
            cid = best

            passed = str(row.get(key_yes, "")).strip().lower() if key_yes else ""
            notice = str(row.get(key_notice, "")).strip() if key_notice else ""
            leave  = str(row.get(key_leave, "")).strip() if key_leave else ""

            # save PDF attachment of whole row
            outdir = "uploads"
            os.makedirs(outdir, exist_ok=True)
            pdf_path = os.path.join(outdir, f"interview_notes_{cid}.pdf")
            save_row_pdf(pdf_path, {c:str(row[c]) for c in df.columns})

            cur.execute("INSERT INTO attachments(candidate_id,filename,path,doc_type) VALUES(?,?,?,?)",
                        (cid, f"InterviewNotes_{cid}.pdf", pdf_path, "Interview Notes"))

            # update candidate fields
            # status Interviewed
            cur.execute("UPDATE candidates SET status=?, notice_period=?, planned_leave=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        ("Interviewed", notice or None, leave or None, cid))
            updated += 1
        con.commit()
    return updated
