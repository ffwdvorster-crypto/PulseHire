from rapidfuzz import fuzz, process
import re
from db import list_keywords, add_keyword

DEFAULT_KEYWORDS = [
    {"term":"Customer Service", "tier":1, "notes":"Core competency"},
    {"term":"Customer Support", "tier":1},
    {"term":"Client Relations", "tier":2},
    {"term":"Customer Satisfaction", "tier":2},
    {"term":"Customer Experience", "tier":2},
    {"term":"Communication Skills", "tier":1},
    {"term":"Verbal Communication", "tier":2},
    {"term":"Written Communication", "tier":2},
    {"term":"Active Listening", "tier":2},
    {"term":"Interpersonal Skills", "tier":3},
    {"term":"Conflict Resolution", "tier":2},
    {"term":"Problem-Solving Skills", "tier":1},
    {"term":"Problem Resolution", "tier":2},
    {"term":"Troubleshooting", "tier":2},
    {"term":"Critical Thinking", "tier":2},
    {"term":"Decision Making", "tier":2},
    {"term":"Analytical Skills", "tier":2},

    {"term":"Technical Skills", "tier":2},
    {"term":"CRM Software", "tier":1, "notes":"e.g., Salesforce, Zendesk, Freshdesk"},
    {"term":"Salesforce", "tier":1},
    {"term":"Zendesk", "tier":1},
    {"term":"Freshdesk", "tier":2},
    {"term":"Microsoft Office", "tier":2},
    {"term":"Excel", "tier":2},
    {"term":"Outlook", "tier":3},
    {"term":"PowerPoint", "tier":3},

    {"term":"Bilingual", "tier":1},
    {"term":"English", "tier":2},
    {"term":"Spanish", "tier":2},
    {"term":"Irish", "tier":2},
    {"term":"Finnish", "tier":3},
    {"term":"C1", "tier":1, "notes":"CEFR level"},
    {"term":"C2", "tier":1},
    {"term":"B2", "tier":2},

    {"term":"Healthcare", "tier":2},
    {"term":"Telehealth", "tier":2},
    {"term":"HIPAA", "tier":1},
    {"term":"GDPR", "tier":1},
]

TIER_WEIGHTS = {1: 3.0, 2: 2.0, 3: 1.0}

def normalize_text(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return text

def build_keyword_index():
    kws = list_keywords()
    return [(k["term"], int(k["tier"])) for k in kws]

def score_text(text: str, threshold: int = 85):
    txt = normalize_text(text)
    if not txt.strip():
        return 0.0, []

    idx = build_keyword_index()
    total_weight = 0.0
    hits = []
    for term, tier in idx:
        weight = TIER_WEIGHTS.get(tier, 1.0)
        score = fuzz.partial_ratio(term.lower(), txt)
        if score >= threshold:
            total_weight += weight
            hits.append({"term": term, "tier": tier, "match": score, "weight": weight})
    return total_weight, hits

def add_new_keyword(term: str, tier: int = 2, notes: str = None):
    add_keyword(term, tier, notes)