import io, json, os
import pandas as pd
from rapidfuzz import fuzz
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from db import get_db

# ---------- Applications (MS Forms export) ----------
def _pick(cols, *keys):
    """Find first column name that contains any of the keys (case-insensitive)."""
    for key in keys:
        k = key.lower()
        for c in cols:
            if k in c:
                return cols[c]
    return None

def ingest_applications(xls_file):
    """
    Reads Application Excel and upserts candidates.
    Columns it tries to detect (case-insensitive, partial match):
      - name, email, phone, county
      - availability, source, completion time, notes
      - notice (start soon), leave (upcoming days off)
    Auto-sets status = Applied.
    Applies auto-DNC if county in blocked_counties (no override).
    """
    df = pd.read_excel(xls_file)
    # Map lowercase -> actual column
    cols = {str(c).lower(): c for c in df.columns}

    c_name   = _pick(cols, "name")
    c_email  = _pick(cols, "email")
    c_phone  = _pick(cols, "phone", "mobile")
    c_county = _pick(cols, "county", "location")
    c_avail  = _pick(cols, "availability")
    c_source = _pick(cols, "source")
    c_ctime  = _pick(cols, "completion", "submitted")
    c_notes  = _pick(cols, "notes", "comments")
    c_notice = _pick(cols, "notice", "how soon", "start")
    c_leave  = _pick(cols, "leave", "days off")

    inserted = updated = skipped = dnc_applied = 0

    with get_db() as con:
        cur = con.cursor()

        # Build blocked counties set
        cur.execute("SELECT county FROM blocked_counties")
        blocked = { (r[0] or "").strip().lower() for r in cur.fetchall() }

        for _, row in df.iterrows():
            name  = str(row.get(c_name, "")).strip() if c_name else ""
            email = str(row.get(c_email, "")).strip().lower() if c_email else ""
            phone = str(row.get(c_phone, "")).strip() if c_phone else ""
            county= str(row.get(c_county, "")).strip() if c_county else ""
            avail = str(row.get(c_avail, "")).strip() if c_avail else ""
            source= str(row.get(c_source, "")).strip() if c_source else ""
            ctime = str(row.get(c_ctime, "")).strip() if c_ctime else ""
            notes = str(row.get(c_notes, "")).strip() if c_notes else ""
            notice= str(row.get(c_notice, "")).strip() if c_notice else ""
            leave = str(row.get(c_leave, "")).strip() if c_leave else ""

            if not name and not email:
                skipped += 1
                continue

            # Does a candidate exist (email preferred)?
            cand_id = None
            if email:
                cur.execute("SELECT id FROM candidates WHERE lower(email)=?", (email,))
                r = cur.fetchone()
                if r: cand_id = r[0]

            if cand_id:  # update basics
                cur.execute("""UPDATE candidates SET
                               name=COALESCE(?,name),
                               phone=COALESCE(?,phone),
                               county=COALESCE(?,county),
                               availability=COALESCE(?,availability),
                               source=COALESCE(?,source),
                               completion_time=COALESCE(?,completion_time),
                               notes=CASE WHEN ?='' THEN notes ELSE ? END,
                               notice_period=COALESCE(?,notice_period),
                               planned_leave=COALESCE(?,planned_leave),
                               status=COALESCE(?,status),
                               updated_at=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (name or None, phone or None, county or None, avail or None, source or None,
                             ctime or None, notes, notes or None, notice or None, leave or None, "Applied", cand_id))
                updated += 1
            else:         # insert new
                # Auto-DNC by county
                is_dnc = 1 if ((county or "").strip().lower() in blocked) else 0
                reason = "Outside hiring area" if is_dnc else None
                if is_dnc: dnc_applied += 1

                cur.execute("""INSERT INTO candidates
                               (name,email,phone,county,availability,source,completion_time,notes,notice_period,planned_leave,status,dnc,dnc_reason)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (name or None, email or None, phone or None, county or None, avail or None, source or None,
                             ctime or None, notes or None, notice or None, leave or None, "Applied", is_dnc, reason))
                inserted += 1

        con.commit()

    return {"inserted": inserted, "updated": updated, "skipped": skipped, "dnc_applied": dnc_applied}

# ---------- TestGorilla ingestion ----------
def ingest_testgorilla(xls_file):
    df = pd.read_excel(xls_file)
    cols = {c.lower(): c for c in df.columns}

    # Best-effort column picks
    c_email = next((cols[k] for k in cols if "email" in k), None)
    c_name  = next((cols[k] for k in cols if "name" in k and "test" not in k), None)
    c_tname = next((cols[k] for k in cols if "test" in k and "name" in k), None) or next((cols[k] for k in cols if "assessment" in k), None)
    c_score = next((cols[k] for k in cols if "%score" in k or "score %" in k or "score"==k), None)
    c_pct   = next((cols[k] for k in cols if "percentile" in k), None)

    matched = 0
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
                best = None; best_score = 0
                for cid, cname in cur.fetchall():
                    sc = fuzz.token_set_ratio(name, cname or "")
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
                if score_raw.endswith("%"):
                    try: score_pct = float(score_raw[:-1])
                    except Exception: score_pct = None

            cur.execute("INSERT INTO test_scores(candidate_id,provider,test_name,score_raw,score_pct) VALUES(?,?,?,?,?)",
                        (cand_id,"TestGorilla", tname or None, score_raw or None, score_pct))
            matched += 1
        con.commit()
    return matched

# ---------- Interview Notes ingestion ----------
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
        cur.execute("SELECT id,name FROM candidates")
        allc = cur.fetchall()
        for _, row in df.iterrows():
            name = str(row.get(c_name, "")).strip()
            if not name: continue
            # fuzzy match candidate
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
            cur.execute("UPDATE candidates SET status=?, notice_period=?, planned_leave=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        ("Interviewed", notice or None, leave or None, cid))
            updated += 1
        con.commit()
    return updated
