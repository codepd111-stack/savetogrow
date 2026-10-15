"""Rule-based quick entry: '450 dinner upi' or '+50000 acme salary'. No AI, no network."""
from __future__ import annotations

import datetime as dt
import re

METHOD_WORDS = {
    "upi": "UPI", "gpay": "UPI", "phonepe": "UPI", "paytm": "UPI", "bhim": "UPI",
    "cash": "Cash", "card": "Card", "credit": "Card", "debit": "Card",
    "neft": "Bank", "imps": "Bank", "netbanking": "Bank", "bank": "Bank", "wallet": "Wallet",
}
AMOUNT_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)*)\s*(k)?(?![\w])", re.I)
DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$")


def parse(text: str, categories, sources, today: dt.date | None = None) -> dict:
    """
    Returns {"kind": "expense"|"income", "amount": float|None, "category_id": int|None, "source_id": int|None,
             "note": str, "method": str, "date": "YYYY-MM-DD", "matched": bool}
    `categories` and `sources` are sequences of rows/dicts with "id" and "name".
    """
    today = today or dt.date.today()
    t = text.strip()
    kind = "expense"
    if t.startswith("+"):
        kind, t = "income", t[1:].strip()
    amount = None
    m = AMOUNT_RE.search(t)
    if m:
        amount = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        t = (t[: m.start()] + " " + t[m.end():]).strip()
    words = t.split()
    method, date, kept = "", today, []
    for w in words:
        lw = w.lower().strip(",.")
        dm = DATE_RE.match(lw)
        if lw in METHOD_WORDS and not method:
            method = METHOD_WORDS[lw]
        elif lw == "yesterday":
            date = today - dt.timedelta(days=1)
        elif lw == "today":
            date = today
        elif dm:
            try:
                d, mo = int(dm.group(1)), int(dm.group(2))
                y = int(dm.group(3)) if dm.group(3) else today.year
                if y < 100:
                    y += 2000
                date = dt.date(y, mo, d)
            except ValueError:
                kept.append(w)
        else:
            kept.append(w)
    lowered = " ".join(kept).lower()
    target = sources if kind == "income" else categories
    best, best_len = None, 0
    for row in target:
        name = row["name"].lower()
        hit = name in lowered or any(len(p) > 2 and p in lowered.split() for p in name.split())
        if hit and len(name) > best_len:
            best, best_len = row, len(name)
    note = " ".join(kept).strip()
    if best:
        # drop the matched name from the note so "450 food dinner" keeps just "dinner"
        pattern = re.compile(r"\b" + r"\b|\b".join(re.escape(p) for p in best["name"].lower().split()) + r"\b", re.I)
        note = re.sub(r"\s+", " ", pattern.sub("", note)).strip(" ,.-")
    return {
        "kind": kind, "amount": amount, "note": note[:120], "method": method, "date": date.isoformat(),
        "category_id": best["id"] if (best and kind == "expense") else None,
        "source_id": best["id"] if (best and kind == "income") else None,
        "matched": best is not None,
    }
