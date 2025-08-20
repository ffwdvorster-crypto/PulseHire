import re, json, math
from rapidfuzz import fuzz
try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None
try:
    import docx
except Exception:
    docx = None

SEED_KEYWORDS = {
  "Skills":[
    "Customer Service","Customer Support","Client Relations","Customer Satisfaction","Customer Experience",
    "Communication Skills","Verbal Communication","Written Communication","Active Listening","Interpersonal Skills",
    "Conflict Resolution","Problem-Solving Skills","Problem Resolution","Troubleshooting","Critical Thinking",
    "Decision Making","Analytical Skills"
  ],
  "Tools":[
    "CRM Software","Salesforce","Zendesk","Microsoft Office Suite","Word","Excel","PowerPoint",
    "Email Support","Live Chat Support","Technical Support"
  ],
  "Attributes":["Patience","Empathy","Adaptability","Professionalism","Teamwork"],
  "Metrics":["CSAT","Customer Satisfaction Score","NPS","Net Promoter Score","FCR","First Call Resolution","AHT","Average Handle Time","SLA","Service Level Agreement"],
  "Action Verbs":["Assisted","Resolved","Managed","Handled","Supported"],
  "Employers (call centres, fuzzy)":[
    "Infosys","Eishtec","Concentrix","FIS","Abtran","Covalen","Voxpro","Call Centre Solutions",
    "RelateCare","Relate care","Rigney Dolphin","Rigneydolphin","RigneyDolphin"
  ]
}

def extract_text(file):
    name = (getattr(file, "name", "") or "").lower()
    try:
        file.seek(0)
    except Exception:
        pass
    if name.endswith(".pdf") and PdfReader:
        try:
            reader = PdfReader(file)
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            return ""
    if name.endswith(".docx") and docx:
        try:
            d = docx.Document(file)
            return "\n".join(p.text for p in d.paragraphs)
        except Exception:
            return ""
    try:
        file.seek(0)
        return file.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

def _kw_hits(text, kws):
    T = " " + re.sub(r"\s+", " ", text.lower()) + " "
    hits=set()
    for kw in kws:
        k = kw.strip()
        if not k: continue
        rx = r"(?<!\w)"+re.escape(k.lower())+r"(?!\w)"
        if re.search(rx, T): hits.add(k)
    return hits

def score_cv(cv_text, keywords):
    cats = ["Skills","Tools","Attributes","Metrics","Action Verbs"]
    words = [w for c in cats for w in keywords.get(c, [])]
    total = len(words) or 1
    hits = _kw_hits(cv_text, words)
    pct = (len(hits)/total)*100.0
    if pct >= 75: tier="High"
    elif pct >= 40: tier="Medium"
    else: tier="Low"
    prev_emp = any(k in cv_text.lower() for k in ["relatecare","relate care","rigney dolphin","rigneydolphin"])
    flags = {"score_pct": round(pct,1), "previous_employee": prev_emp}
    return tier, flags

def fuzzy_match_name(a, b):
    return fuzz.token_set_ratio(a or "", b or "")
