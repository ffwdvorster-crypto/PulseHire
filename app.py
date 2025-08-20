# Mini ATS – Pretty + Functional + Editable
# Streamlit one-file app
# Features:
# - Upload multiple CVs (PDF/DOCX/TXT)
# - Editable keyword groups + weights in sidebar
# - Tiered labels (Strong / Potential / Low) with thresholds
# - Caution flag for multiple short tenures (< 6 months)
# - Auto-extract Name/Email/Phone (best-effort)
# - Highlights matched keywords
# - Download results as CSV and config as JSON

import io
import re
import json
import math
import base64
from datetime import datetime
from dateutil import parser as dtparse
from dateutil.relativedelta import relativedelta

import pandas as pd
import streamlit as st

# ---- Optional imports (PDF/DOCX) ------------------------------------------------
from PyPDF2 import PdfReader
import docx  # python-docx

# ---- Page config ----------------------------------------------------------------
st.set_page_config(
    page_title="Mini ATS (Pretty + Functional)",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Minimal theming / CSS ------------------------------------------------------
STYLES = """
<style>
/* Global */
:root { --bg:#0b1016; --card:#111827; --muted:#94a3b8; --accent:#22d3ee; --ok:#10b981; --warn:#f59e0b; --bad:#ef4444; }
.main, .block-container { padding-top: 1rem !important; }

/* Cards */
.card {
  background: var(--card);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 16px;
  padding: 18px 18px 14px 18px;
  box-shadow: 0 4px 18px rgba(0,0,0,0.28);
}
.card h3 { margin: 0 0 8px 0; font-weight: 700; }

/* Badges */
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.80rem;
  font-weight: 700;
  letter-spacing: 0.2px;
  border: 1px solid rgba(255,255,255,0.12);
}
.badge-strong { background: rgba(16,185,129,0.15); color: #a7f3d0; }
.badge-potential { background: rgba(245,158,11,0.12); color: #fde68a; }
.badge-low { background: rgba(239,68,68,0.12); color: #fecaca; }
.badge-warn { background: rgba(245,158,11,0.18); color: #fbbf24; }

/* Pills for keyword categories */
.pill { display:inline-block; margin:2px 6px 2px 0; padding:4px 10px; border-radius:999px; background:rgba(255,255,255,0.06); font-size:.80rem; }
.pill b { opacity:.85 }

/* Keyword highlighting */
.hl { background: rgba(34,211,238,0.2); padding: 0 2px; border-radius: 4px; }

/* Dataframe tweaks */
[data-testid="stTable"] td, [data-testid="stTable"] th { font-size: 0.92rem; }
</style>
"""
st.markdown(STYLES, unsafe_allow_html=True)

# ---- Defaults (from your list; fully editable in the UI) ------------------------
DEFAULT_CONFIG = {
    "categories": {
        "Core Skills": [
            "Customer Service",
            "Customer Support",
            "Client Relations",
            "Customer Satisfaction",
            "Customer Experience",
            "Communication Skills",
            "Verbal Communication",
            "Written Communication",
            "Active Listening",
            "Interpersonal Skills",
            "Conflict Resolution",
            "Problem-Solving Skills",
            "Problem Resolution",
            "Troubleshooting",
            "Critical Thinking",
            "Decision Making",
            "Analytical Skills",
        ],
        "Technical Skills": [
            "CRM Software",
            "Salesforce",
            "Zendesk",
            "Microsoft Office",
            "Word",
            "Excel",
            "PowerPoint",
            "Email Support",
            "Live Chat Support",
            "Technical Support",
        ],
        "Personal Attributes": [
            "Patience",
            "Empathy",
            "Adaptability",
            "Professionalism",
            "Teamwork",
        ],
        "Performance Metrics": [
            "Customer Satisfaction Score",
            "CSAT",
            "Net Promoter Score",
            "NPS",
            "First Call Resolution",
            "FCR",
            "Average Handle Time",
            "AHT",
            "Service Level Agreement",
            "SLA",
        ],
    },
    # weights per category (sum normalised in code)
    "weights": {
        "Core Skills": 40,
        "Technical Skills": 30,
        "Personal Attributes": 15,
        "Performance Metrics": 15,
    },
    # Tier thresholds (>= strong, >= potential, else low)
    "tiers": {
        "strong_min": 70,
        "potential_min": 40
    },
    # Caution rule: flag if jobs < 6 months count >= 2
    "short_tenure_months": 6,
    "short_tenure_threshold": 2,
}

def load_config():
    if "config" not in st.session_state:
        st.session_state["config"] = DEFAULT_CONFIG
    return st.session_state["config"]

def save_config(cfg):
    st.session_state["config"] = cfg

cfg = load_config()

# ---- Sidebar (Editable Controls) ------------------------------------------------
with st.sidebar:
    st.header("⚙️ Scoring Settings")

    # Category weights
    st.caption("Category Weights (relative)")
    new_weights = {}
    for cat, val in cfg["weights"].items():
        new_weights[cat] = st.slider(f"{cat}", 0, 100, int(val), help="Relative weight")
    cfg["weights"] = new_weights

    # Tier thresholds
    st.markdown("---")
    st.caption("Tier thresholds (by total score)")
    strong_min = st.slider("Strong Fit minimum", 0, 100, int(cfg["tiers"]["strong_min"]))
    potential_min = st.slider("Potential minimum", 0, 100, int(cfg["tiers"]["potential_min"]))
    if potential_min > strong_min:
        st.info("Note: Potential min is higher than Strong min; this is allowed but unusual.")
    cfg["tiers"]["strong_min"] = strong_min
    cfg["tiers"]["potential_min"] = potential_min

    # Caution settings
    st.markdown("---")
    st.caption("Reliability Caution (short tenures)")
    short_months = st.number_input("Short tenure = under X months", 1, 24, int(cfg["short_tenure_months"]))
    short_threshold = st.number_input("Flag if there are ≥ X short tenures", 1, 10, int(cfg["short_tenure_threshold"]))
    cfg["short_tenure_months"] = int(short_months)
    cfg["short_tenure_threshold"] = int(short_threshold)

    # Editable keywords
    st.markdown("---")
    st.caption("Keyword Categories (editable; one per line)")
    new_categories = {}
    for cat, words in cfg["categories"].items():
        text = "\n".join(words)
        edited = st.text_area(f"{cat}", value=text, height=150)
        new_categories[cat] = [w.strip() for w in edited.split("\n") if w.strip()]
    cfg["categories"] = new_categories

    # Config IO
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save Config to Session"):
            save_config(cfg)
            st.success("Config saved to session.")
    with c2:
        cfg_json = json.dumps(cfg, indent=2)
        st.download_button("⬇️ Download Config JSON", cfg_json, file_name="mini_ats_config.json", mime="application/json")

    uploaded_cfg = st.file_uploader("⬆️ Load Config JSON", type=["json"], accept_multiple_files=False, label_visibility="collapsed")
    if uploaded_cfg is not None:
        try:
            loaded = json.loads(uploaded_cfg.read().decode("utf-8"))
            save_config(loaded)
            st.success("Config loaded.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to load config: {e}")

# ---- Helpers -------------------------------------------------------------------
MONTHS = {
    m.lower(): i for i, m in enumerate(
        ["January","February","March","April","May","June","July","August","September","October","November","December"], start=1
    )
}
MONTHS_ABBR = {
    m[:3].lower(): MONTHS[m.lower()] for m in MONTHS
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-.]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{7,}\d")
NAME_LINE_RE = re.compile(r"^\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s*$")

DATE_RANGE_PATTERNS = [
    # Jan 2021 - May 2022
    r"(?P<m1>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"(?P<y1>\d{4})\s*[-–—]\s*"
    r"(?P<m2>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"(?P<y2>\d{4}|Present|Current)",
    # 01/2020 - 06/2020 or 2020-01 to 2020-06
    r"(?P<m1n>\d{1,2})[\/\-](?P<y1n>\d{2,4})\s*[-–—]\s*(?P<m2n>\d{1,2})[\/\-](?P<y2n>\d{2,4}|Present|Current)",
    # 2020 to 2021 (year only)
    r"(?P<y_only_1>\d{4})\s*(?:to|[-–—])\s*(?P<y_only_2>\d{4}|Present|Current)"
]

def normalise_year(y):
    # Handle 2-digit years
    y = str(y)
    if len(y) == 2:
        yr = int(y)
        return 2000 + yr if yr < 50 else 1900 + yr
    return int(y)

def parse_date_str(month_str, year_str):
    if month_str is None:
        # Year-only
        return dtparse.parse(f"01/01/{normalise_year(year_str)}")
    m_lower = month_str.lower()
    if m_lower in MONTHS:
        m = MONTHS[m_lower]
    else:
        m = MONTHS_ABBR.get(m_lower[:3], 1)
    return dtparse.parse(f"{m}/01/{normalise_year(year_str)}")

def extract_text(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        text = []
        for page in reader.pages:
            try:
                text.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(text)
    elif name.endswith(".docx"):
        doc = docx.Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    elif name.endswith(".txt"):
        return file.read().decode("utf-8", errors="ignore")
    else:
        # try to read as text
        try:
            return file.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

def extract_contact_info(text):
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    # naive name guess: top 5 non-empty lines, pick first capitalized line
    possible_name = None
    for line in text.splitlines()[:8]:
        if len(line.strip()) < 3:
            continue
        if NAME_LINE_RE.match(line.strip()):
            possible_name = line.strip()
            break
    return (possible_name or ""), (email.group(0) if email else ""), (phone.group(0) if phone else "")

def find_date_ranges(text):
    ranges = []
    for pat in DATE_RANGE_PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            gd = m.groupdict()
            try:
                if "m1" in gd:
                    start = parse_date_str(gd["m1"], gd["y1"])
                    end = None if gd["y2"].lower() in ("present","current") else parse_date_str(gd["m2"], gd["y2"])
                elif "m1n" in gd:
                    start = dtparse.parse(f"{gd['m1n']}/01/{normalise_year(gd['y1n'])}")
                    end = None if str(gd["y2n"]).lower() in ("present","current") else dtparse.parse(f"{gd['m2n']}/01/{normalise_year(gd['y2n'])}")
                else:
                    start = parse_date_str("Jan", gd["y_only_1"])
                    end = None if gd["y_only_2"].lower() in ("present","current") else parse_date_str("Dec", gd["y_only_2"])
                ranges.append((start, end))
            except Exception:
                continue
    # Deduplicate rough equivalents
    uniq = []
    seen = set()
    for s,e in ranges:
        key = (s.strftime("%Y-%m"), e.strftime("%Y-%m") if e else "present")
        if key not in seen:
            uniq.append((s,e))
            seen.add(key)
    return uniq

def months_between(a: datetime, b: datetime) -> int:
    if b is None:
        b = datetime.today()
    if a > b:
        a, b = b, a
    r = relativedelta(b, a)
    return r.years * 12 + r.months + (1 if r.days >= 15 else 0)

def count_short_stints(ranges, short_months=6):
    count = 0
    for s,e in ranges:
        dur = months_between(s, e)
        if dur < short_months:
            count += 1
    return count

def keyword_hits(text, keywords):
    """Return set of matched keywords (case-insensitive, whole-word-ish search for phrases)."""
    t = " " + re.sub(r"\s+", " ", text.lower()) + " "
    hits = set()
    for kw in keywords:
        k = kw.strip()
        if not k:
            continue
        # build regex for phrase with word boundaries on ends
        rx = r"(?<!\w)" + re.escape(k.lower()) + r"(?!\w)"
        if re.search(rx, t):
            hits.add(k)
    return hits

def score_candidate(text, cfg):
    cat_hits = {}
    total_possible = 0
    # normalise weights
    weights = cfg["weights"]
    w_sum = sum(max(0, v) for v in weights.values()) or 1
    w_norm = {k: max(0, v)/w_sum for k,v in weights.items()}

    # collect hits and weighted score
    score = 0.0
    for cat, words in cfg["categories"].items():
        words = [w for w in words if w]
        total_possible += len(words)
        hits = keyword_hits(text, words)
        cat_hits[cat] = {"hits": hits, "total": len(words)}
        frac = (len(hits) / len(words)) if words else 0
        score += frac * (w_norm.get(cat, 0) * 100.0)

    # clamp
    score = max(0.0, min(100.0, score))
    return score, cat_hits

def tier_label(score, tiers):
    if score >= tiers["strong_min"]:
        return "Strong Fit", "badge-strong"
    elif score >= tiers["potential_min"]:
        return "Potential", "badge-potential"
    return "Low Fit", "badge-low"

def highlight_keywords(text, all_keywords):
    # light touch highlighter (limit output size)
    t = text
    # Limit to first 2000 chars to avoid heavy HTML
    snippet = t[:2000]
    for kw in sorted(set(all_keywords), key=len, reverse=True):
        if not kw:
            continue
        pattern = re.compile(r"(?i)(?<!\w)(" + re.escape(kw) + r")(?!\w)")
        snippet = pattern.sub(r'<span class="hl">\1</span>', snippet)
    if len(t) > 2000:
        snippet += " …"
    return snippet

def make_badge(text, cls):
    return f'<span class="badge {cls}">{text}</span>'

# ---- Header --------------------------------------------------------------------
title_col, ctrl_col = st.columns([0.75, 0.25])
with title_col:
    st.markdown(
        """
        <div class="card">
          <h3>🧠 Mini ATS – Keyword Scoring & Tenure Caution</h3>
          <div style="opacity:.8">Upload CVs, tweak keywords/weights, get tiered scores, and auto-flag short tenures.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with ctrl_col:
    st.write("")
    st.write("")
    st.info("Tip: Edit everything in the sidebar.\nDownload CSV below results.")

# ---- Uploads -------------------------------------------------------------------
uploaded = st.file_uploader(
    "Upload CVs (PDF, DOCX, or TXT)",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True
)

if not uploaded:
    st.caption("No files yet. Add some CVs to get scores.")
else:
    rows = []
    details_sections = []
    for f in uploaded:
        raw_text = extract_text(f)
        text = raw_text if raw_text else ""
        # Basic contact info
        name, email, phone = extract_contact_info(text)

        # Scoring
        score, cat_hits = score_candidate(text, cfg)
        label, badge_cls = tier_label(score, cfg["tiers"])

        # Tenure analysis
        ranges = find_date_ranges(text)
        short_count = count_short_stints(ranges, cfg["short_tenure_months"])
        caution = short_count >= cfg["short_tenure_threshold"]
        caution_badge = make_badge(f"Short tenures: {short_count}", "badge-warn") if caution else ""

        # Prepare row
        rows.append({
            "File": f.name,
            "Candidate": name,
            "Email": email,
            "Phone": phone,
            "Score": round(score, 1),
            "Tier": label,
            "ShortTenures(<{}m)".format(cfg["short_tenure_months"]): short_count,
            "Caution": "Yes" if caution else "No",
        })

        # Details card (per candidate)
        all_keywords = []
        pill_html = []
        for cat, data in cat_hits.items():
            hits = sorted(list(data["hits"]))
            all_keywords.extend(hits)
            pill_html.append(
                f'<span class="pill"><b>{cat}:</b> {len(hits)}/{data["total"]}</span>'
            )

        highlight_html = highlight_keywords(text, all_keywords)

        details_sections.append(
            f"""
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
                <div>
                  <h3 style="margin-bottom:0">{name or f.name}</h3>
                  <div style="opacity:.75">{email or "—"} · {phone or "—"}</div>
                </div>
                <div>
                  {make_badge(f"{label} · {round(score,1)}", badge_cls)}
                  {' ' + caution_badge if caution else ''}
                </div>
              </div>
              <div style="margin-top:8px">{' '.join(pill_html)}</div>
              <div style="margin-top:10px;font-size:.92rem;line-height:1.5;max-height:280px;overflow:auto;border-top:1px dashed rgba(255,255,255,.08);padding-top:10px;">
                {highlight_html}
              </div>
            </div>
            """
        )

    # ---- Summary table ----------------------------------------------------------
    df = pd.DataFrame(rows)
    # Sort by Score desc
    df = df.sort_values(by="Score", ascending=False).reset_index(drop=True)

    st.subheader("📊 Ranked Candidates")
    st.dataframe(
        df.style.format(precision=1),
        use_container_width=True,
        height=min(500, 120 + 35 * len(df))
    )

    # ---- Download CSV -----------------------------------------------------------
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Results (CSV)",
        data=csv,
        file_name="mini_ats_results.csv",
        mime="text/csv",
    )

    # ---- Details cards ----------------------------------------------------------
    st.subheader("🔍 Details & Keyword Highlights")
    for html in details_sections:
        st.markdown(html, unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ---- Footer note ---------------------------------------------------------------
st.caption("Built for quick screening. Always review CVs holistically before decisions.")
