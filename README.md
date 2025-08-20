# PulseHire ATS (Streamlit)

A lightweight ATS prototype with login, campaigns, counties, candidate ingestion, scoring,
and placeholders for compliance & changelog.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

**Admin login:** `admin@pulsehire.local` / `admin123`

## Notes
- SQLite DB auto-creates at `data/pulsehire.db` on first run, with seeded keywords and counties.
- Dark theme configured via `.streamlit/config.toml` (and `theme.toml` included as requested).
- Logo is left-aligned in the sidebar (2x size) from `assets/logo.png`.
- "Upload as Test" toggles are available for application/TestGorilla/interview notes ingestion.
- Scoring uses fuzzy matching (RapidFuzz) with tiered weighting (1:3.0, 2:2.0, 3:1.0).