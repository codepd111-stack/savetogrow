"""Turns a month's numbers into plain text. No charts, no AI: just arithmetic and sentences."""
from __future__ import annotations

import datetime as dt

from .store import Store, days_in, shift_month

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def rs(x: float, sym: str = "₹") -> str:
    """₹1,23,456 with Indian grouping; decimals only when needed."""
    return _rs(x, sym)


def _rs(x: float, sym: str) -> str:
    neg = x < 0
    x = abs(x)
    whole = int(x)
    frac = round(x - whole, 2)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    if frac >= 0.005:
        s += f".{int(round(frac * 100)):02d}"
    return ("-" if neg else "") + sym + s


def month_label(month: str) -> str:
    y, m = month.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def month_short(month: str) -> str:
    y, m = month.split("-")
    return f"{MONTHS[int(m) - 1][:3].upper()} {y}"


def summarize(store: Store, month: str, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    n = days_in(month)
    cur = today.strftime("%Y-%m")
    if month == cur:
        day_no, phase = today.day, "current"
    elif month < cur:
        day_no, phase = n, "past"
    else:
        day_no, phase = 0, "future"
    days_left = n - day_no

    by_source = store.income_by_source(month)
    sources = store.sources()
    income_rows = []
    pending = []
    for s in sources:
        amt = by_source.get(s["id"], 0.0)
        income_rows.append({"id": s["id"], "name": s["name"], "amount": amt, "pay_day": s["pay_day"]})
        if amt <= 0 and s["pay_day"]:
            due_day = min(int(s["pay_day"]), n)
            if phase == "past":
                status = "not received"
            elif phase == "future":
                status = f"expected on {due_day}"
            else:
                status = "due now" if today.day >= due_day else f"expected on {due_day}"
            pending.append({"name": s["name"], "day": due_day, "status": status})
    # income from hidden sources still counts
    income_total = sum(by_source.values())

    spent_by = store.spent_by_category(month)
    cats = []
    for c in store.categories(active_only=False):
        spent = spent_by.get(c["id"], 0.0)
        if not c["active"] and spent <= 0:
            continue
        if c["kind"] == "percent":
            limit = income_total * float(c["value"]) / 100.0
            rule = f"{float(c['value']):g}% of income"
        else:
            limit = float(c["value"])
            rule = "fixed"
        left = limit - spent
        pct = (spent / limit * 100.0) if limit > 0 else (100.0 if spent > 0 else 0.0)
        status = "over" if left < -0.005 else ("near" if pct >= 80 else "ok")
        cats.append({"id": c["id"], "name": c["name"], "kind": c["kind"], "value": float(c["value"]), "rule": rule,
                     "limit": limit, "spent": spent, "left": left, "pct": pct, "status": status,
                     "active": bool(c["active"])})

    budget_total = sum(c["limit"] for c in cats if c["active"])
    spent_total = sum(c["spent"] for c in cats)
    prev_month = shift_month(month, -1)
    prev_spent = sum(store.spent_by_category(prev_month).values())
    prev_income = sum(store.income_by_source(prev_month).values())
    methods = {}
    for e in store.expenses(month):
        key = (e["method"] or "unspecified").strip().upper()
        methods[key] = methods.get(key, 0.0) + float(e["amount"])

    return {
        "month": month, "label": month_label(month), "phase": phase,
        "day_no": day_no, "days": n, "days_left": days_left,
        "income": income_total, "sources": income_rows, "pending": pending,
        "categories": cats, "budget": budget_total, "spent": spent_total,
        "left": income_total - spent_total, "budget_left": budget_total - spent_total,
        "prev_spent": prev_spent, "prev_income": prev_income, "methods": methods,
        "count": store.conn.execute("SELECT COUNT(*) FROM expenses WHERE substr(date,1,7)=?", (month,)).fetchone()[0],
    }


def notes(s: dict, sym: str = "₹") -> list[str]:
    """Short observations about the month, most useful first."""
    def rs(x):  # noqa: A001 - local currency formatter honouring the caller's symbol
        return _rs(x, sym)

    out: list[str] = []
    cats = [c for c in s["categories"]]
    spent_cats = sorted((c for c in cats if c["spent"] > 0), key=lambda c: -c["spent"])
    if not s["income"] and not s["spent"]:
        return ["Nothing recorded yet. Add this month's income and your first expense."]
    if s["budget"] > s["income"] + 0.005 and s["income"] > 0:
        out.append(f"Your category budgets add up to {rs(s['budget'])}, which is {rs(s['budget'] - s['income'])} more than this month's income.")
    over = [c for c in cats if c["status"] == "over"]
    if over:
        out.append("Over budget: " + ", ".join(f"{c['name']} by {rs(-c['left'])}" for c in over) + ".")
    near = [c for c in cats if c["status"] == "near"]
    if near:
        out.append("Close to the limit: " + ", ".join(f"{c['name']} ({c['pct']:.0f}%)" for c in near) + ".")
    if spent_cats:
        big = spent_cats[0]
        share = big["spent"] / s["spent"] * 100 if s["spent"] else 0
        out.append(f"Biggest category: {big['name']} at {rs(big['spent'])} ({share:.0f}% of spending).")
    if s["phase"] == "current" and s["day_no"] > 0 and s["spent"] > 0:
        per_day = round(s["spent"] / s["day_no"])  # estimates are rounded to whole rupees
        projected = round(per_day * s["days"])
        verdict = (f"{rs(s['budget'] - projected)} under budget" if projected <= s["budget"]
                   else f"{rs(projected - s['budget'])} over budget")
        out.append(f"Pace: about {rs(per_day)} a day so far. At this rate the month ends near {rs(projected)}, {verdict}.")
        if s["days_left"] > 0:
            room = max(0.0, s["budget_left"])
            out.append(f"To stay within budget, spend at most {rs(round(room / s['days_left']))} a day for the remaining {s['days_left']} days.")
    if s["pending"]:
        out.append("Income still expected: " + ", ".join(f"{p['name']} ({p['status']})" for p in s["pending"]) + ".")
    if s["income"] > 0:
        kept = s["income"] - s["spent"]
        pct = kept / s["income"] * 100
        if kept >= 0:
            out.append(f"You have kept {rs(kept)} of your income so far ({pct:.0f}%).")
        else:
            out.append(f"Spending has passed income by {rs(-kept)}.")
    if s["prev_spent"] > 0 and s["spent"] > 0:
        change = (s["spent"] - s["prev_spent"]) / s["prev_spent"] * 100
        direction = "more" if change > 0 else "less"
        out.append(f"Compared with last month you have spent {abs(change):.0f}% {direction} ({rs(s['spent'])} vs {rs(s['prev_spent'])}).")
    if s["methods"] and s["spent"] > 0:
        top = max(s["methods"].items(), key=lambda kv: kv[1])
        if len(s["methods"]) > 1:
            out.append(f"Most payments went through {top[0]} ({top[1] / s['spent'] * 100:.0f}%).")
    unplanned = [c for c in cats if not c["active"] and c["spent"] > 0]
    if unplanned:
        out.append("Hidden categories still carrying spending this month: " + ", ".join(c["name"] for c in unplanned) + ".")
    return out


def report_lines(s: dict, sym: str = "₹") -> list[str]:
    """The full text report shown in the app and written to the PDF."""
    def m(x):
        return rs(x, sym)

    head = s["label"].upper()
    if s["phase"] == "current":
        head += f"  ·  DAY {s['day_no']} OF {s['days']}  ·  {s['days_left']} LEFT"
    elif s["phase"] == "past":
        head += "  ·  CLOSED"
    else:
        head += "  ·  NOT STARTED"
    lines = [head, ""]
    lines.append(f"{'INCOME':<10}{m(s['income']):>14}")
    for src in s["sources"]:
        if src["amount"] > 0:
            lines.append(f"  {src['name'][:22]:<22}{m(src['amount']):>14}")
    for p in s["pending"]:
        lines.append(f"  {p['name'][:22]:<22}{'(' + p['status'] + ')':>14}")
    lines.append(f"{'BUDGETED':<10}{m(s['budget']):>14}")
    lines.append(f"{'SPENT':<10}{m(s['spent']):>14}   {s['count']} entries")
    lines.append(f"{'KEPT':<10}{m(s['left']):>14}   income minus spending")
    lines.append("")
    lines.append("CATEGORIES")
    lines.append(f"  {'name':<12}{'spent':>9}{'limit':>9}{'used':>5}  status")
    for c in s["categories"]:
        if c["status"] == "over":
            status = f"OVER by {m(-c['left'])}"
        elif c["limit"] <= 0:
            status = "no budget"
        else:
            status = f"{m(c['left'])} left"
            if c["status"] == "near":
                status += " (near)"
        name = c["name"][:11] + ("*" if not c["active"] else "")
        lines.append(f"  {name:<12}{m(c['spent']):>9}{m(c['limit']):>9}{c['pct']:>4.0f}%  {status}")
    percent_cats = [c for c in s["categories"] if c["kind"] == "percent" and c["active"]]
    if percent_cats:
        lines.extend(wrap(", ".join(f"{c['name']} = {c['value']:g}% of income" for c in percent_cats), WIDTH, "  ", "  "))
    if any(not c["active"] for c in s["categories"]):
        lines.append("  * hidden category")
    lines.append("")
    lines.append("NOTES")
    for n in notes(s, sym):
        lines.extend(wrap(n, WIDTH, "  - ", "    "))
    return lines


WIDTH = 56  # columns visible in the app's text panel; the PDF has room for more but stays consistent


def wrap(text: str, width: int, first: str, rest: str) -> list[str]:
    words = text.split()
    lines, cur, prefix = [], "", first
    for w in words:
        if len(prefix) + len(cur) + len(w) + (1 if cur else 0) > width and cur:
            lines.append(prefix + cur)
            cur, prefix = w, rest
        else:
            cur = (cur + " " + w) if cur else w
    if cur:
        lines.append(prefix + cur)
    return lines
