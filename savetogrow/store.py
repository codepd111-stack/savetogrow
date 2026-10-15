"""Local data store: one SQLite file in %LOCALAPPDATA%\\Savetogrow (override with SAVETOGROW_DATA)."""
from __future__ import annotations

import calendar
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

APP_NAME = "Savetogrow"
KINDS = ("fixed", "percent")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    pay_day INTEGER,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    amount REAL NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('fixed','percent')),
    value REAL NOT NULL DEFAULT 0,
    sort INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    amount REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_income_date ON income(date);
"""

# name, kind, value - a starting point; edit freely in the app
SAMPLE_CATEGORIES = (
    ("Rent", "fixed", 15000),
    ("Food", "fixed", 6000),
    ("Travel", "fixed", 2000),
    ("Bills", "fixed", 2500),
    ("Savings", "percent", 20),
    ("Fun", "fixed", 1500),
    ("Other", "fixed", 1000),
)


def app_dir() -> Path:
    """Folder holding Savetogrow.exe (or the project root when running from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def portable_dir() -> Path:
    """A `data` folder next to the exe. If it exists, Savetogrow keeps everything there, so exe + folder can travel together."""
    return app_dir() / "data"


def user_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME


def data_dir() -> Path:
    """Where the data file lives: SAVETOGROW_DATA, else a portable `data` folder next to the exe, else this Windows user's app data."""
    override = os.environ.get("SAVETOGROW_DATA")
    if override:
        base = Path(override)
    elif portable_dir().is_dir():
        base = portable_dir()
    else:
        base = user_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base


def is_portable(path: Path) -> bool:
    try:
        return Path(path).resolve().parent == portable_dir().resolve()
    except OSError:
        return False


def looks_like_savetogrow_db(path: Path) -> bool:
    """True if the file is a SQLite database with Savetogrow's tables (used before restoring a backup)."""
    try:
        conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return {"categories", "expenses", "income", "sources"} <= names


def month_of(date_str: str) -> str:
    return date_str[:7]


def shift_month(month: str, n: int) -> str:
    y, m = map(int, month.split("-"))
    t = y * 12 + (m - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def days_in(month: str) -> int:
    y, m = map(int, month.split("-"))
    return calendar.monthrange(y, m)[1]


def parse_date(text: str) -> str:
    """Accept YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD/MM, DD-MM (current year). Returns ISO."""
    text = text.strip()
    today = dt.date.today()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):  # day/month only: assume the current year
        try:
            return dt.datetime.strptime(f"{text}{fmt[5]}{today.year}", fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Date must be like 2026-10-14 or 14/10/2026")


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else data_dir() / "savetogrow.db"
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        if not self.conn.execute("SELECT 1 FROM categories LIMIT 1").fetchone():
            for i, (name, kind, value) in enumerate(SAMPLE_CATEGORIES):
                self.conn.execute("INSERT INTO categories(name, kind, value, sort) VALUES (?,?,?,?)", (name, kind, value, i))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- sources (jobs) ----------
    def sources(self, active_only: bool = True) -> list[sqlite3.Row]:
        q = "SELECT * FROM sources" + (" WHERE active=1" if active_only else "") + " ORDER BY name"
        return self.conn.execute(q).fetchall()

    def source_by_name(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM sources WHERE lower(name)=lower(?)", (name.strip(),)).fetchone()

    def add_source(self, name: str, pay_day: int | None = None) -> int:
        name = _required(name, "Source name")
        _check_day(pay_day)
        if self.source_by_name(name):
            raise ValueError(f"A source called {name} already exists")
        cur = self.conn.execute("INSERT INTO sources(name, pay_day) VALUES (?,?)", (name, pay_day))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def update_source(self, sid: int, name: str, pay_day: int | None, active: bool = True) -> None:
        name = _required(name, "Source name")
        _check_day(pay_day)
        clash = self.source_by_name(name)
        if clash and clash["id"] != sid:
            raise ValueError(f"A source called {name} already exists")
        self.conn.execute("UPDATE sources SET name=?, pay_day=?, active=? WHERE id=?", (name, pay_day, 1 if active else 0, sid))
        self.conn.commit()

    def delete_source(self, sid: int) -> str:
        """Delete if unused, otherwise hide it. Returns 'deleted' or 'hidden'."""
        used = self.conn.execute("SELECT 1 FROM income WHERE source_id=? LIMIT 1", (sid,)).fetchone()
        if used:
            self.conn.execute("UPDATE sources SET active=0 WHERE id=?", (sid,))
            self.conn.commit()
            return "hidden"
        self.conn.execute("DELETE FROM sources WHERE id=?", (sid,))
        self.conn.commit()
        return "deleted"

    # ---------- income ----------
    def income(self, month: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT i.*, s.name AS source FROM income i JOIN sources s ON s.id=i.source_id "
            "WHERE substr(i.date,1,7)=? ORDER BY i.date DESC, i.id DESC", (month,)).fetchall()

    def add_income(self, date: str, source_id: int, amount: float, note: str = "") -> int:
        cur = self.conn.execute("INSERT INTO income(date, source_id, amount, note) VALUES (?,?,?,?)",
                                (_date(date), source_id, _amount(amount), note.strip()))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def update_income(self, iid: int, date: str, source_id: int, amount: float, note: str = "") -> None:
        self.conn.execute("UPDATE income SET date=?, source_id=?, amount=?, note=? WHERE id=?",
                          (_date(date), source_id, _amount(amount), note.strip(), iid))
        self.conn.commit()

    def delete_income(self, iid: int) -> None:
        self.conn.execute("DELETE FROM income WHERE id=?", (iid,))
        self.conn.commit()

    # ---------- categories ----------
    def categories(self, active_only: bool = True) -> list[sqlite3.Row]:
        q = "SELECT * FROM categories" + (" WHERE active=1" if active_only else "") + " ORDER BY sort, id"
        return self.conn.execute(q).fetchall()

    def category_by_name(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM categories WHERE lower(name)=lower(?)", (name.strip(),)).fetchone()

    def add_category(self, name: str, kind: str, value: float) -> int:
        name = _required(name, "Category name")
        kind, value = _kind_value(kind, value)
        if self.category_by_name(name):
            raise ValueError(f"A category called {name} already exists")
        sort = (self.conn.execute("SELECT COALESCE(MAX(sort),0) FROM categories").fetchone()[0] or 0) + 1
        cur = self.conn.execute("INSERT INTO categories(name, kind, value, sort) VALUES (?,?,?,?)", (name, kind, value, sort))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def update_category(self, cid: int, name: str, kind: str, value: float, active: bool = True) -> None:
        name = _required(name, "Category name")
        kind, value = _kind_value(kind, value)
        clash = self.category_by_name(name)
        if clash and clash["id"] != cid:
            raise ValueError(f"A category called {name} already exists")
        self.conn.execute("UPDATE categories SET name=?, kind=?, value=?, active=? WHERE id=?",
                          (name, kind, value, 1 if active else 0, cid))
        self.conn.commit()

    def move_category(self, cid: int, direction: int) -> None:
        rows = self.categories(active_only=False)
        ids = [r["id"] for r in rows]
        if cid not in ids:
            return
        i = ids.index(cid)
        j = i + direction
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            for sort, x in enumerate(ids):
                self.conn.execute("UPDATE categories SET sort=? WHERE id=?", (sort, x))
            self.conn.commit()

    def delete_category(self, cid: int) -> str:
        used = self.conn.execute("SELECT 1 FROM expenses WHERE category_id=? LIMIT 1", (cid,)).fetchone()
        if used:
            self.conn.execute("UPDATE categories SET active=0 WHERE id=?", (cid,))
            self.conn.commit()
            return "hidden"
        self.conn.execute("DELETE FROM categories WHERE id=?", (cid,))
        self.conn.commit()
        return "deleted"

    # ---------- expenses ----------
    def expenses(self, month: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT e.*, c.name AS category FROM expenses e JOIN categories c ON c.id=e.category_id "
            "WHERE substr(e.date,1,7)=? ORDER BY e.date DESC, e.id DESC", (month,)).fetchall()

    def add_expense(self, date: str, category_id: int, amount: float, note: str = "", method: str = "") -> int:
        cur = self.conn.execute("INSERT INTO expenses(date, category_id, amount, note, method) VALUES (?,?,?,?,?)",
                                (_date(date), category_id, _amount(amount), note.strip(), method.strip()))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def update_expense(self, eid: int, date: str, category_id: int, amount: float, note: str = "", method: str = "") -> None:
        self.conn.execute("UPDATE expenses SET date=?, category_id=?, amount=?, note=?, method=? WHERE id=?",
                          (_date(date), category_id, _amount(amount), note.strip(), method.strip(), eid))
        self.conn.commit()

    def delete_expense(self, eid: int) -> None:
        self.conn.execute("DELETE FROM expenses WHERE id=?", (eid,))
        self.conn.commit()

    # ---------- aggregates ----------
    def spent_by_category(self, month: str) -> dict[int, float]:
        rows = self.conn.execute("SELECT category_id, SUM(amount) s FROM expenses WHERE substr(date,1,7)=? GROUP BY category_id", (month,))
        return {r["category_id"]: float(r["s"]) for r in rows}

    def income_by_source(self, month: str) -> dict[int, float]:
        rows = self.conn.execute("SELECT source_id, SUM(amount) s FROM income WHERE substr(date,1,7)=? GROUP BY source_id", (month,))
        return {r["source_id"]: float(r["s"]) for r in rows}

    def months_with_data(self) -> list[str]:
        rows = self.conn.execute("SELECT substr(date,1,7) m FROM expenses UNION SELECT substr(date,1,7) FROM income ORDER BY 1 DESC")
        return [r["m"] for r in rows]

    def methods(self) -> list[str]:
        rows = self.conn.execute("SELECT method, COUNT(*) n FROM expenses WHERE method<>'' GROUP BY method ORDER BY n DESC LIMIT 6")
        return [r["method"] for r in rows]


# ---------- validation ----------
def _required(value: str, what: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{what} is required")
    return value[:60]


def _amount(value) -> float:
    try:
        amount = float(str(value).replace(",", "").replace("₹", "").strip())
    except ValueError:
        raise ValueError("Amount must be a number") from None
    if amount <= 0:
        raise ValueError("Amount must be more than 0")
    return round(amount, 2)


def _date(value: str) -> str:
    return parse_date(value)


def _check_day(day) -> None:
    if day is not None and not 1 <= int(day) <= 31:
        raise ValueError("Pay day must be between 1 and 31")


def _kind_value(kind: str, value) -> tuple[str, float]:
    if kind not in KINDS:
        raise ValueError("Type must be fixed or percent")
    try:
        value = float(str(value).replace(",", "").strip())
    except ValueError:
        raise ValueError("Value must be a number") from None
    if value < 0 or (kind == "percent" and value > 100):
        raise ValueError("Percent must be between 0 and 100" if kind == "percent" else "Amount can't be negative")
    return kind, round(value, 2)
