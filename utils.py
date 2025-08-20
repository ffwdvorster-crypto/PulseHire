# utils.py — helpers (working days, filters, DNC apply)
from datetime import date, timedelta
from db import connect

def subtract_workdays(start_date: date, days: int) -> date:
    d = start_date
    count = 0
    while count < days:
        d = d - timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            count += 1
    return d

def apply_dnc_blocked_counties():
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT county FROM blocked_counties")
        blocked = {r["county"].strip().lower() for r in cur.fetchall()}
        if not blocked: return 0
        cur.execute("SELECT id, county, dnc_override FROM candidates")
        n = 0
        for r in cur.fetchall():
            county = (r["county"] or "").strip().lower()
            if county in blocked and not r["dnc_override"]:
                cur.execute("UPDATE candidates SET dnc=1, dnc_reason='Outside hiring area' WHERE id=?", (r["id"],))
                n += 1
        return n
