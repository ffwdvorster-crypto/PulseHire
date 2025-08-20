# PulseHire — Full ATS (Login + ATS screens)

This repo contains PulseHire with:
- Login + Roles (admin, recruiter, hr, viewer)
- Dashboard, Campaigns, Active Recruitment
- Candidates (list, filters, candidate file view)
- CV upload + scoring (High/Medium/Low) + flags (reliability, previous employee)
- TestGorilla ingestion (Excel) — match by Email, fallback Name (fuzzy)
- Interview Notes ingestion (Excel) — match by Name (fuzzy), extract Pass/Notice/Leave, save PDF attachment
- Attachments store (uploads/)
- Do Not Call (blocked counties) + Apply rule
- Keywords editor
- Compliance panel
- Changelog (editable by admin)
- Retention purge (2 years) manual button

## Default Login
- Email: `admin@pulsehire.local`
- Password: `admin`

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy
- Push to GitHub
- Set entry point to `app.py`
- Replace `assets/pulsehire_logo.png` with your real logo file (same name)
