import datetime as dt

import pytest

from savetogrow import pdf, quick
from savetogrow.analysis import notes, report_lines, rs, summarize
from savetogrow.store import Store, parse_date, shift_month


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def test_sample_categories_seeded(store):
    names = [c["name"] for c in store.categories()]
    assert names[:3] == ["Rent", "Food", "Travel"] and "Savings" in names


def test_rupee_formatting():
    assert rs(0) == "₹0"
    assert rs(450) == "₹450"
    assert rs(12345.5) == "₹12,345.50"
    assert rs(1234567) == "₹12,34,567"
    assert rs(-2500, "Rs ") == "-Rs 2,500"


def test_dates_and_months():
    assert parse_date("2026-10-14") == "2026-10-14"
    assert parse_date("14/10/2026") == "2026-10-14"
    assert parse_date("14/10").endswith("-10-14")
    with pytest.raises(ValueError):
        parse_date("yesterday")
    assert shift_month("2026-12", 1) == "2027-01"
    assert shift_month("2026-01", -1) == "2025-12"


def test_sources_income_and_pending(store):
    job = store.add_source("Acme Corp", 1)
    classes = store.add_source("Classes", 20)
    store.add_income("2026-10-01", job, 50000, "salary")
    s = summarize(store, "2026-10", today=dt.date(2026, 10, 14))
    assert s["income"] == 50000
    assert [p["name"] for p in s["pending"]] == ["Classes"] and s["pending"][0]["status"] == "expected on 20"
    s2 = summarize(store, "2026-10", today=dt.date(2026, 10, 25))
    assert s2["pending"][0]["status"] == "due now"
    s3 = summarize(store, "2026-09", today=dt.date(2026, 10, 25))
    assert {p["status"] for p in s3["pending"]} == {"not received"}
    assert store.delete_source(classes) == "deleted"
    assert store.delete_source(job) == "hidden"  # has income, so it is hidden instead
    assert [x["name"] for x in store.sources()] == []
    with pytest.raises(ValueError):
        store.add_source("", 1)
    with pytest.raises(ValueError):
        store.add_source("Nope", 40)


def test_budget_maths_fixed_and_percent(store):
    job = store.add_source("Job", None)
    store.add_income("2026-10-02", job, 50000)
    food = store.category_by_name("Food")["id"]
    savings = store.category_by_name("Savings")["id"]
    travel = store.category_by_name("Travel")["id"]
    store.add_expense("2026-10-03", food, 4200, "groceries", "UPI")
    store.add_expense("2026-10-04", travel, 2350, "cab", "Cash")
    store.add_expense("2026-10-05", savings, 5000, "SIP", "Bank")
    s = summarize(store, "2026-10", today=dt.date(2026, 10, 14))
    by = {c["name"]: c for c in s["categories"]}
    assert by["Savings"]["limit"] == 10000 and by["Savings"]["rule"] == "20% of income"
    assert by["Food"]["left"] == 1800 and by["Food"]["status"] == "ok"
    assert by["Travel"]["status"] == "over" and by["Travel"]["left"] == -350
    assert s["spent"] == 11550 and s["left"] == 50000 - 11550
    assert s["budget"] == 15000 + 6000 + 2000 + 2500 + 10000 + 1500 + 1000
    text = "\n".join(report_lines(s))
    assert "OVER by ₹350" in text and "Travel" in text and "NOTES" in text
    ns = notes(s)
    assert any("Over budget: Travel by ₹350" in n for n in ns)
    assert any("Biggest category: Savings" in n for n in ns)
    assert any("Pace:" in n for n in ns)


def test_category_edit_hide_and_order(store):
    fun = store.category_by_name("Fun")["id"]
    store.update_category(fun, "Fun & games", "fixed", 2000)
    assert store.category_by_name("Fun & games")["value"] == 2000
    with pytest.raises(ValueError):
        store.add_category("Food", "fixed", 1)
    with pytest.raises(ValueError):
        store.add_category("Weird", "percent", 150)
    store.add_expense("2026-10-03", fun, 100, "", "")
    assert store.delete_category(fun) == "hidden"
    assert store.delete_category(store.add_category("Temp", "fixed", 5)) == "deleted"
    first = store.categories()[0]["id"]
    store.move_category(first, 1)
    assert store.categories()[1]["id"] == first
    s = summarize(store, "2026-10", today=dt.date(2026, 10, 14))
    hidden = next(c for c in s["categories"] if c["name"] == "Fun & games")
    assert hidden["active"] is False and hidden["spent"] == 100


def test_expense_validation(store):
    food = store.category_by_name("Food")["id"]
    with pytest.raises(ValueError):
        store.add_expense("2026-10-03", food, 0)
    with pytest.raises(ValueError):
        store.add_expense("bad date", food, 10)
    eid = store.add_expense("2026-10-03", food, "1,250.50", "x", "UPI")
    assert store.expenses("2026-10")[0]["amount"] == 1250.5
    store.update_expense(eid, "2026-10-04", food, 99, "y", "")
    assert store.expenses("2026-10")[0]["note"] == "y"
    store.delete_expense(eid)
    assert store.expenses("2026-10") == []


def test_quick_parse(store):
    cats, srcs = store.categories(), []
    job = store.add_source("Acme Corp", 1)
    srcs = store.sources()
    today = dt.date(2026, 10, 14)
    p = quick.parse("450 dinner upi", cats, srcs, today)
    assert p["kind"] == "expense" and p["amount"] == 450 and p["method"] == "UPI" and p["matched"] is False
    p = quick.parse("2.5k food groceries yesterday", cats, srcs, today)
    assert p["amount"] == 2500 and p["category_id"] == store.category_by_name("Food")["id"]
    assert p["note"] == "groceries" and p["date"] == "2026-10-13"
    p = quick.parse("+50000 acme salary 1/10", cats, srcs, today)
    assert p["kind"] == "income" and p["source_id"] == job and p["note"] == "salary" and p["date"] == "2026-10-01"
    p = quick.parse("travel 120 cash", cats, srcs, today)
    assert p["category_id"] == store.category_by_name("Travel")["id"] and p["method"] == "Cash" and p["note"] == ""
    assert quick.parse("just words", cats, srcs, today)["amount"] is None


def test_data_dir_precedence(tmp_path, monkeypatch):
    from savetogrow import store as st

    monkeypatch.delenv("SAVETOGROW_DATA", raising=False)
    monkeypatch.setattr(st, "app_dir", lambda: tmp_path / "exe")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert st.data_dir() == tmp_path / "local" / "Savetogrow"
    (tmp_path / "exe" / "data").mkdir(parents=True)
    assert st.data_dir() == tmp_path / "exe" / "data"  # portable folder wins once it exists
    assert st.is_portable(tmp_path / "exe" / "data" / "savetogrow.db")
    monkeypatch.setenv("SAVETOGROW_DATA", str(tmp_path / "override"))
    assert st.data_dir() == tmp_path / "override"  # explicit override wins over both
    db = Store(tmp_path / "x.db")
    db.close()
    assert st.looks_like_savetogrow_db(tmp_path / "x.db")
    (tmp_path / "junk.db").write_bytes(b"not a database")
    assert not st.looks_like_savetogrow_db(tmp_path / "junk.db")


def test_notes_honour_currency_symbol(store):
    job = store.add_source("Job", None)
    store.add_income("2026-10-02", job, 50000)
    store.add_expense("2026-10-03", store.category_by_name("Travel")["id"], 2350, "cab", "Cash")
    s = summarize(store, "2026-10", today=dt.date(2026, 10, 14))
    plain = "\n".join(report_lines(s, sym="Rs "))
    assert "₹" not in plain and "Rs 2,350" in plain  # the fallback PDF has no rupee glyph


def test_report_pdf(store, tmp_path):
    from savetogrow import report

    job = store.add_source("Acme Corp", 1)
    store.add_source("Classes", 20)
    store.add_income("2026-10-01", job, 50000, "salary")
    cats = {c["name"]: c["id"] for c in store.categories()}
    store.add_expense("2026-10-03", cats["Rent"], 15000, "rent", "Bank")
    store.add_expense("2026-10-05", cats["Travel"], 2350, "cab & <train>", "Cash")
    s = summarize(store, "2026-10", today=dt.date(2026, 10, 14))
    out = tmp_path / "report.pdf"
    info = report.write_report(out, s, store.expenses("2026-10"), store.income("2026-10"), generated=dt.datetime(2026, 10, 14, 21, 30))
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and b"/Type /Page" in data
    assert info["engine"] in ("reportlab", "basic")
    if info["engine"] == "reportlab":
        assert info["font"] == "Report"  # a system TrueType font was embedded
    # an empty month still produces a document
    empty = summarize(store, "2026-01", today=dt.date(2026, 10, 14))
    report.write_report(tmp_path / "empty.pdf", empty, [], [])
    assert (tmp_path / "empty.pdf").stat().st_size > 500


def test_pdf_written(tmp_path):
    out = pdf.write_pdf(tmp_path / "r.pdf", "Savetogrow report - October 2026", [f"line {i} (₹) \\ test" for i in range(130)])
    data = out.read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert data.count(b"/Type /Page ") == 3  # 130 lines at 56 per page
