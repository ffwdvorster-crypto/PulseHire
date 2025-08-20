# theme.py — brand + CSS

BRAND = {
    "name": "PulseHire",
    "font_google": "Nunito:wght@400;600;700",
    "logo_path": "assets/pulsehire-logo.png",  # replace with your actual file
    "colors": {
        "primary": "#00b89f",
        "primaryDark": "#1a6f49",
        "accent": "#ffc600",
        "danger": "#ef4444",
        "ok": "#10b981",
        "darkBg": "#0f172a",
        "darkPanel": "#111827",
        "lightBg": "#ffffff",
        "lightPanel": "#f8fafc",
        "textLight": "#111827",
        "textDark": "#e5e7eb",
    }
}

CSS_BASE = """
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --primary: %(primary)s;
  --primaryDark: %(primaryDark)s;
  --accent: %(accent)s;
  --danger: %(danger)s;
  --ok: %(ok)s;
  --darkBg: %(darkBg)s;
  --darkPanel: %(darkPanel)s;
  --lightBg: %(lightBg)s;
  --lightPanel: %(lightPanel)s;
  --textLight: %(textLight)s;
  --textDark: %(textDark)s;
}
html, body, [class^="stApp"] { font-family: 'Nunito', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
.badge { display:inline-block;padding:4px 10px;border-radius:999px;font-size:.8rem;font-weight:700;border:1px solid rgba(0,0,0,0.08); }
.chip { display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:.8rem;font-weight:700; }
.row { display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
.card { border-radius:16px; padding:16px; border:1px solid rgba(0,0,0,.06); }
</style>
""" % BRAND["colors"]

def inject_css(st, dark=False):
    bg = "var(--darkBg)" if dark else "var(--lightBg)"
    panel = "var(--darkPanel)" if dark else "var(--lightPanel)"
    fg = "var(--textDark)" if dark else "var(--textLight)"
    st.markdown(CSS_BASE, unsafe_allow_html=True)
    st.markdown(f"""
<style>
.stApp {{ background:{bg}; color:{fg}; }}
section[data-testid="stSidebar"] > div:first-child {{ background:{panel}; }}
.block-container {{ padding-top: 1rem; }}
</style>
""", unsafe_allow_html=True)
