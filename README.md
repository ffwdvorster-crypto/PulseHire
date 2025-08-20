# PulseHire — starter

This is a minimal, clean PulseHire starter with:
- Embedded theme + logo
- Working login (default admin seeded on first run)
  - Email: `admin@pulsehire.local`
  - Password: `admin`

## Deploy (Streamlit Cloud)
1. Create a new GitHub repo and upload all files from this zip.
2. In Streamlit, set the app entry point to `app.py`.
3. First run will auto-create the SQLite DB and seed the default admin.
4. Log in and you're good.

## Local run
```bash
pip install -r requirements.txt
streamlit run app.py
```

> Tip: keep `pulsehire.db` **out of git** (already in `.gitignore`). Delete it to reseed the default admin.
