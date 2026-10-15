"""The PDF money report.

With reportlab (bundled into the exe) this is a proper document: header, summary tiles, income and category
tables with colour-coded status, notes, and every entry of the month, set in Arial from the Windows font folder
so the rupee sign prints. Without reportlab it falls back to the plain-text PDF writer in pdf.py.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from xml.sax.saxutils import escape

from .analysis import notes, report_lines, rs

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    HAVE_REPORTLAB = True
except ImportError:  # running from source without reportlab installed
    HAVE_REPORTLAB = False

INK, MUTED, GREEN, RED, AMBER = "#1F2937", "#6B7280", "#1E8F55", "#C0392B", "#B7791F"
GRID, ZEBRA, TILE, HEAD = "#E3E6EB", "#F6F7F9", "#EEF1F4", "#F0F7F3"

FONT_CANDIDATES = (("arial.ttf", "arialbd.ttf"), ("segoeui.ttf", "segoeuib.ttf"), ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"))
_fonts: tuple[str, str, bool] | None = None


def fonts() -> tuple[str, str, bool]:
    """(regular, bold, has_rupee_glyph). Registers a system TrueType font once; falls back to Helvetica."""
    global _fonts
    if _fonts:
        return _fonts
    dirs = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/Library/Fonts"),
    ]
    for regular, bold in FONT_CANDIDATES:
        for d in dirs:
            if (d / regular).is_file() and (d / bold).is_file():
                try:
                    pdfmetrics.registerFont(TTFont("Report", str(d / regular)))
                    pdfmetrics.registerFont(TTFont("Report-Bold", str(d / bold)))
                    _fonts = ("Report", "Report-Bold", 0x20B9 in pdfmetrics.getFont("Report").face.charToGlyph)
                    return _fonts
                except Exception:  # a broken font file must not stop the export
                    continue
    _fonts = ("Helvetica", "Helvetica-Bold", False)
    return _fonts


def write_report(path, s: dict, expenses, income, generated: dt.datetime | None = None) -> dict:
    """Write the report for summary `s` (from analysis.summarize). Returns details of what was used."""
    path = Path(path)
    if not HAVE_REPORTLAB:
        from .pdf import write_pdf

        write_pdf(path, f"Savetogrow report - {s['label']}", report_lines(s, sym="Rs "))
        return {"engine": "basic", "font": "Courier", "rupee": False}

    regular, bold, rupee = fonts()
    sym = "₹" if rupee else "Rs "
    generated = generated or dt.datetime.now()

    def m(x):
        return rs(x, sym)

    def col(text, color):
        return f'<font color="{color}">{escape(str(text))}</font>'

    st = {
        "brand": ParagraphStyle("brand", fontName=bold, fontSize=8, leading=10, textColor=colors.HexColor(GREEN)),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=21, leading=25, textColor=colors.HexColor(INK), spaceBefore=2),
        "sub": ParagraphStyle("sub", fontName=regular, fontSize=9, leading=12, textColor=colors.HexColor(MUTED)),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=11.5, leading=14, textColor=colors.HexColor(INK), spaceBefore=14, spaceAfter=5),
        "body": ParagraphStyle("body", fontName=regular, fontSize=9.5, leading=13, textColor=colors.HexColor(INK)),
        "muted": ParagraphStyle("muted", fontName=regular, fontSize=9, leading=12, textColor=colors.HexColor(MUTED)),
        "cell": ParagraphStyle("cell", fontName=regular, fontSize=9, leading=11, textColor=colors.HexColor(INK)),
        "cellr": ParagraphStyle("cellr", fontName=regular, fontSize=9, leading=11, textColor=colors.HexColor(INK), alignment=TA_RIGHT),
        "tile_l": ParagraphStyle("tile_l", fontName=bold, fontSize=7.5, leading=9, textColor=colors.HexColor(MUTED)),
        "tile_v": ParagraphStyle("tile_v", fontName=bold, fontSize=15, leading=18, textColor=colors.HexColor(INK)),
        "bullet": ParagraphStyle("bullet", fontName=regular, fontSize=9.5, leading=13, textColor=colors.HexColor(INK),
                                 leftIndent=12, bulletIndent=2, spaceAfter=3),
    }
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Savetogrow report - {s['label']}", author="Savetogrow",
                            subject="Monthly money report")
    W = doc.width
    story: list = []

    # ----- header -----
    if s["phase"] == "current":
        when = f"Day {s['day_no']} of {s['days']} · {s['days_left']} days left"
    elif s["phase"] == "past":
        when = "Month closed"
    else:
        when = "Month not started"
    story += [
        Paragraph("SAVETOGROW · MONEY REPORT", st["brand"]),
        Paragraph(escape(s["label"]), st["h1"]),
        Paragraph(f"{when} · generated {generated:%d %b %Y, %H:%M}", st["sub"]),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=1.2, color=colors.HexColor(GREEN), spaceAfter=10),
    ]

    # ----- summary tiles -----
    kept_color = RED if s["left"] < 0 else INK
    tiles = [("INCOME", m(s["income"]), INK), ("SPENT", m(s["spent"]), INK), ("BUDGET", m(s["budget"]), INK),
             ("KEPT (INCOME − SPENT)", m(s["left"]), kept_color)]
    tile_row = [[Paragraph(label, st["tile_l"]), Paragraph(col(value, color), st["tile_v"])] for label, value, color in tiles]
    tiles_table = Table([tile_row], colWidths=[W / 4] * 4, rowHeights=[17 * mm])
    tiles_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(TILE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEAFTER", (0, 0), (-2, -1), 3, colors.white),
    ]))
    story.append(tiles_table)

    # ----- income -----
    story.append(Paragraph("Income", st["h2"]))
    active_total = sum(src["amount"] for src in s["sources"])
    other = s["income"] - active_total
    if s["sources"] or other > 0:
        pending = {p["name"]: p["status"] for p in s["pending"]}
        rows = [["Source", "Amount", "Status"]]
        for src in s["sources"]:
            if src["amount"] > 0:
                rows.append([escape(src["name"]), m(src["amount"]), Paragraph(col("received", GREEN), st["cell"])])
            else:
                status = pending.get(src["name"], "nothing booked")
                color = AMBER if src["name"] in pending else MUTED
                rows.append([escape(src["name"]), "—", Paragraph(col(status, color), st["cell"])])
        if other > 0.005:
            rows.append(["Other (hidden sources)", m(other), Paragraph(col("received", GREEN), st["cell"])])
        rows.append(["Total", m(s["income"]), ""])
        t = Table(rows, colWidths=[W * 0.5, W * 0.22, W * 0.28], repeatRows=1)
        t.setStyle(_table_style(regular, bold, len(rows), numeric_cols=(1, 1), total_row=True))
        story.append(t)
    else:
        story.append(Paragraph("No income sources yet. Add your jobs under SOURCES and book income as it arrives.", st["muted"]))

    # ----- categories -----
    story.append(Paragraph("Categories", st["h2"]))
    cats = s["categories"]
    if cats:
        rows = [["Category", "Rule", "Spent", "Limit", "Used", "Status"]]
        for c in cats:
            rule = "fixed" if c["kind"] == "fixed" else f"{c['value']:g}% of income"
            if c["status"] == "over":
                status, color = f"over by {m(-c['left'])}", RED
            elif c["limit"] <= 0:
                status, color = "no budget", MUTED
            elif c["status"] == "near":
                status, color = f"{m(c['left'])} left · near limit", AMBER
            else:
                status, color = f"{m(c['left'])} left", GREEN
            name = escape(c["name"]) + ("  <font color='%s'>(hidden)</font>" % MUTED if not c["active"] else "")
            rows.append([Paragraph(name, st["cell"]), rule, m(c["spent"]), m(c["limit"]), f"{c['pct']:.0f}%",
                         Paragraph(col(status, color), st["cell"])])
        used_total = (s["spent"] / s["budget"] * 100) if s["budget"] > 0 else 0
        diff = s["budget"] - s["spent"]
        total_status = (col(f"{m(-diff)} over budget", RED) if diff < -0.005 else col(f"{m(diff)} under budget", GREEN))
        rows.append(["Total", "", m(s["spent"]), m(s["budget"]), f"{used_total:.0f}%", Paragraph(total_status, st["cell"])])
        t = Table(rows, colWidths=[W * 0.24, W * 0.15, W * 0.13, W * 0.13, W * 0.09, W * 0.26], repeatRows=1)
        t.setStyle(_table_style(regular, bold, len(rows), numeric_cols=(2, 4), total_row=True))
        story.append(t)
        if s["budget"] > s["income"] + 0.005 and s["income"] > 0:
            story.append(Spacer(1, 4))
            story.append(Paragraph(col(f"Budgets add up to {m(s['budget'])}, {m(s['budget'] - s['income'])} more than this month's income.", AMBER), st["muted"]))
    else:
        story.append(Paragraph("No categories yet.", st["muted"]))

    # ----- notes -----
    story.append(Paragraph("Notes", st["h2"]))
    for n in notes(s, sym):
        story.append(Paragraph(escape(n), st["bullet"], bulletText="•"))

    # ----- entries -----
    story.append(Paragraph(f"Expenses · {len(expenses)} {'entry' if len(expenses) == 1 else 'entries'}", st["h2"]))
    if expenses:
        rows = [["Date", "Category", "Note", "Method", "Amount"]]
        for e in sorted(expenses, key=lambda r: (r["date"], r["id"])):
            rows.append([_day(e["date"]), Paragraph(escape(e["category"]), st["cell"]), Paragraph(escape(e["note"] or ""), st["cell"]),
                         escape(e["method"] or ""), m(e["amount"])])
        rows.append(["Total", "", "", "", m(sum(float(e["amount"]) for e in expenses))])
        t = Table(rows, colWidths=[W * 0.11, W * 0.22, W * 0.37, W * 0.13, W * 0.17], repeatRows=1)
        t.setStyle(_table_style(regular, bold, len(rows), numeric_cols=(4, 4), total_row=True))
        story.append(t)
    else:
        story.append(Paragraph("Nothing recorded this month.", st["muted"]))

    if income:
        story.append(Paragraph(f"Income entries · {len(income)}", st["h2"]))
        rows = [["Date", "Source", "Note", "Amount"]]
        for i in sorted(income, key=lambda r: (r["date"], r["id"])):
            rows.append([_day(i["date"]), Paragraph(escape(i["source"]), st["cell"]), Paragraph(escape(i["note"] or ""), st["cell"]), m(i["amount"])])
        t = Table(rows, colWidths=[W * 0.11, W * 0.32, W * 0.40, W * 0.17], repeatRows=1)
        t.setStyle(_table_style(regular, bold, len(rows), numeric_cols=(3, 3), total_row=False))
        story.append(KeepTogether(t) if len(rows) < 12 else t)

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(doc.leftMargin, 10 * mm, f"Savetogrow · {s['label']} · generated {generated:%d %b %Y, %H:%M}")
        canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return {"engine": "reportlab", "font": regular, "rupee": rupee}


def _table_style(regular: str, bold: str, nrows: int, numeric_cols=(1, 1), total_row: bool = True):
    cmds = [
        ("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), bold), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(MUTED)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEAD)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.HexColor(GREEN)),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(INK)),
        ("ALIGN", (numeric_cols[0], 0), (numeric_cols[1], -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(GRID)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(ZEBRA)]),
    ]
    if total_row and nrows > 1:
        cmds += [("FONTNAME", (0, -1), (-1, -1), bold), ("LINEABOVE", (0, -1), (-1, -1), 0.9, colors.HexColor(INK)),
                 ("BACKGROUND", (0, -1), (-1, -1), colors.white), ("LINEBELOW", (0, -1), (-1, -1), 0, colors.white)]
    return TableStyle(cmds)


def _day(iso: str) -> str:
    try:
        return dt.date.fromisoformat(iso).strftime("%d %b")
    except ValueError:
        return iso


def self_check(out_path) -> dict:
    """Write a sample report with made-up data (used to verify a build): returns the engine details."""
    import tempfile

    from .analysis import summarize
    from .store import Store

    tmp = Path(tempfile.mkdtemp())
    store = Store(tmp / "check.db")
    job = store.add_source("Acme Corp", 1)
    store.add_source("Freelance Gigs", 20)
    today = dt.date.today()
    month = today.strftime("%Y-%m")
    store.add_income(f"{month}-01", job, 50000, "salary")
    cat = {c["name"]: c["id"] for c in store.categories()}
    samples = [(3, "Rent", 15000, "October rent", "Bank"), (3, "Food", 1250, "DMart groceries", "UPI"), (5, "Travel", 2350, "cab to Pune", "Cash"),
               (6, "Food", 450, "dinner with friends", "UPI"), (8, "Fun", 600, "movie", "Card"), (10, "Savings", 5000, "SIP", "Bank"),
               (12, "Food", 320, "chai & snacks", "UPI"), (13, "Bills", 1299, "Jio recharge", "UPI")]
    for d, c, a, n, meth in samples:
        store.add_expense(f"{month}-{min(d, today.day):02d}", cat[c], a, n, meth)
    s = summarize(store, month)
    info = write_report(out_path, s, store.expenses(month), store.income(month))
    store.close()
    Path(str(out_path) + ".txt").write_text(repr(info), encoding="utf-8")
    return info
