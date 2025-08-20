# scoring.py — CV text extraction + keyword scoring + flags
import re
from datetime import datetime
from dateutil import parser as dtparse
from dateutil.relativedelta import relativedelta
from typing import Dict, Tuple, Set

# Optional parsers
try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None
try:
    import docx
except Exception:
    docx = None

SEED_KEYWORDS = {
    "Skills": [
        "Customer Service","Customer Support","Client Relations","Customer Satisfaction","Customer Experience",
        "Communication Skills","Verbal Communication","Written Communication","Active Listening","Interpersonal Skills",
        "Conflict Resolution","Problem-Solving Skills","Problem Resolution","Troubleshooting","Critical Thinking",
        "Decision Making","Analytical Skills"
    ],
    "Tools": [
        "CRM Software","Salesforce","Zendesk","Microsoft Office Suite","Word","Excel","PowerPoint",
        "Email Support","Live Chat Support","Technical Support"
    ],
    "Attributes": ["Patience","Empathy","Adaptability","Professionalism","Teamwork"],
    "Metrics": ["CSAT","Customer Satisfaction Score","NPS","Net Promoter Score","FCR","First Call Resolution","AHT","Average Handle Time","SLA","Service Level Agreement"],
    "Action Verbs": ["Assisted","Resolved","Managed","Handled","Supported"],
    "Employers (call centres, fuzzy)": [
        "Infosys","Eishtec","Concentrix","FIS","Abtran","Covalen","Voxpro","Call Centre Solutions",
        "RelateCare","Relate care","Rigney Dolphin","Rigneydolphin","RigneyDolphin"
    ]
}

PREV_EMPLOYER_VARIANTS = {"relatecare","relate care","rigney dolphin","rigneydolphin","rigneydolphin"}

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], start=1
)}
MONTHS_ABBR = {m[:3].lower(): MONTHS[m.lower()] for m in MONTHS}

DATE_RANGE_PATTERNS = [
    r"(?P<m1>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?P<y1>\d{4})\s*[-–—]\s*(?P<m2>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?)\s+(?P<y2>\d{4}|Present|Current)",
    r"(?P<m1n>\d{1,2})[\/\-](?P<y1n>\d{2,4})\s*[-–—]\s*(?P<m2n>\d{1,2})[\/\-](?P<y2n>\d{2,4}|Present|Current)",
    r"(?P<y_only_1>\d{4})\s*(?:to|[-–—])\s*(?P<y_only_2>\d{4}|Present|Current)"
]

def _norm_year(y):
    s = str(y)
    if len(s) == 2:
        v = int(s)
        return 2000 + v if v < 50 else 1900 + v
    return int(s)

def _parse_date(month_str, year_str):
    if month_str is None: return dtparse.parse(f"01/01/{_norm_year(year_str)}")
    m_lower = month_str.lower()
    m = MONTHS.get(m_lower) or MONTHS_ABBR.get(m_lower[:3], 1)
    return dtparse.parse(f"{m}/01/{_norm_year(year_str)}")

def _months_between(a: datetime, b: datetime | None) -> int:
    if b is None: b = datetime.today()
    if a > b: a, b = b, a
    r = relativedelta(b, a)
    return r.years*12 + r.months + (1 if r.days >= 15 else 0)

def _find_date_ranges(text: str):
    spans = []
    for pat in DATE_RANGE_PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            gd = m.groupdict()
            try:
                if "m1" in gd:
                    start = _parse_date(gd["m1"], gd["y1"])
                    end = None if gd["y2"].lower() in ("present","current") else _parse_date(gd["m2"], gd["y2"])
                elif "m1n" in gd:
                    start = dtparse.parse(f"{gd['m1n']}/01/{_norm_year(gd['y1n'])}")
                    end = None if str(gd["y2n"]).lower() in ("present","current") else dtparse.parse(f"{gd['m2n']}/01/{_norm_year(gd['y2n'])}")
                else:
                    start = _parse_date("Jan", gd["y_only_1"])
                    end = None if gd["y_only_2"].lower() in ("present","current") else _parse_date("Dec", gd["y_only_2"])
                spans.append((start, end))
            except Exception:
                continue
    uniq, seen = [], set()
    for s,e in spans:
        key = (s.strftime("%Y-%m"), e.strftime("%Y-%m") if e else "present")
        if key not in seen:
            uniq.append((s,e)); seen.add(key)
    return uniq

def extract_text(file) -> str:
    name = (getattr(file, "name", "") or "").lower()
    try:
        file.seek(0)
    except Exception:
        pass
    if name.endswith(".pdf"):
        if PdfReader is None: return ""
        try:
            reader = PdfReader(file)
            return "\n".join((p.extract_text() or "") for p in getattr(reader, "pages", []))
        except Exception:
            return ""
    if name.endswith(".docx"):
        if docx is None: return ""
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

def _kw_hits(text: str, kws: list[str]) -> Set[str]:
    T = " " + re.sub(r"\s+", " ", text.lower()) + " "
    hits = set()
    for kw in kws:
        k = kw.strip()
        if not k: continue
        rx = r"(?<!\w)" + re.escape(k.lower()) + r"(?!\w)"
        if re.search(rx, T): hits.add(k)
    return hits

def score_cv(cv_text: str, keywords: Dict[str, list[str]]) -> Tuple[str, Dict]:
    """
    Returns (score_tier_label, flags_dict)
    Score tiers:
      High >= 75%, Medium 40–74%, Low < 40%
    """
    cats = ["Skills","Tools","Attributes","Metrics","Action Verbs"]
    all_words = [w for c in cats for w in keywords.get(c, [])]
    total = len(all_words) or 1
    hits = _kw_hits(cv_text, all_words)
    pct = (len(hits) / total) * 100.0
    if pct >= 75: tier = "High"
    elif pct >= 40: tier = "Medium"
    else: tier = "Low"

    # Flags
    employers = keywords.get("Employers (call centres, fuzzy)", [])
    emp_hits = _kw_hits(cv_text, employers)
    callcentre_inferred = True if emp_hits else False

    prev_emp_flag = any(v in cv_text.lower() for v in PREV_EMPLOYER_VARIANTS)

    # reliability: ≥2 short stints (<6 months)
    ranges = _find_date_ranges(cv_text)
    short_months = 6
    short_count = sum(1 for s,e in ranges if _months_between(s, e) < short_months)
    reliability_flag = (short_count >= 2)

    flags = {
        "score_pct": round(pct,1),
        "reliability_caution": reliability_flag,
        "short_tenures_count": short_count,
        "call_centre_inferred": callcentre_inferred,
        "previous_employee": prev_emp_flag
    }
    return tier, flags
