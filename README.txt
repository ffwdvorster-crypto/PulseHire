PSR Recruitment Portal (Streamlit + SQLite)
===========================================

Run:
  pip install -r requirements.txt
  streamlit run app.py

Highlights:
- **Campaigns**: create once (name, hours of operation, requirements text + checkboxes).
- **Recruitment Drives**: for each campaign, set start/cutoff dates and FTE target when hiring.
- **Candidates**: upload MS Forms Excel; de-duplicate and persist. Click a candidate to open their "file".
- **Candidate File**: status, notes, interview datetime, requirement checkboxes, attach files, mark DNC.
- **Bulk Emails**: copy-paste addresses from filters.
- **Do Not Call**: central list respected across views.

All data lives in `portal.db` and attachments under `./uploads`.