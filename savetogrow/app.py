"""The main window: one small, draggable, Winamp-style panel with everything in it."""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, ttk

from . import __version__, quick
from . import theme as T
from .analysis import month_short, report_lines, rs, summarize
from .store import Store, data_dir, is_portable, looks_like_savetogrow_db, portable_dir, shift_month
from .widgets import BevelButton, Dialog, Lcd, TitleBar, confirm, dark_entry, message, setup_ttk

WIDTH, HEIGHT = 480, 660
METHODS = ("UPI", "Cash", "Card", "Bank", "Wallet")
KIND_LABELS = {"fixed": "Fixed amount", "percent": "% of income"}
LABEL_KINDS = {v: k for k, v in KIND_LABELS.items()}


def short_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return d.strftime("%d %b")


class App(tk.Tk):
    def __init__(self, store: Store | None = None):
        super().__init__()
        self.store = store or Store()
        self.month = dt.date.today().strftime("%Y-%m")
        self.tab = "expenses"
        self.rows: list = []
        self.summary: dict = {}
        self.active_dialog = None  # the modal dialog currently open, if any
        self.title("Savetogrow")
        self.configure(bg=T.BEVEL_DARK)
        self.overrideredirect(True)
        self.resizable(False, False)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{WIDTH}x{HEIGHT}+{max(0, (sw - WIDTH) // 2)}+{max(0, (sh - HEIGHT) // 2 - 20)}")
        setup_ttk(self)
        self._build()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.after(60, self._taskbar_fix)
        # belt and braces: if the main window ever gets focus while a dialog is open, put the dialog back in front
        self.bind("<FocusIn>", lambda e: self.active_dialog and self.after(1, self.active_dialog.bring_front))
        self.refresh()

    # ---------- window plumbing ----------
    def _taskbar_fix(self):
        """Borderless windows vanish from the Windows taskbar; flip the extended style so this one shows."""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            gwl_exstyle, ws_ex_appwindow, ws_ex_toolwindow = -20, 0x00040000, 0x00000080
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
            style = (style & ~ws_ex_toolwindow) | ws_ex_appwindow
            ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, style)
            self.withdraw()
            self.after(10, self.deiconify)
        except Exception:
            pass

    def minimize(self):
        self.overrideredirect(False)
        self.iconify()
        self.bind("<Map>", self._restore)

    def _restore(self, _e=None):
        if self.state() == "normal":
            self.unbind("<Map>")
            self.overrideredirect(True)
            self.after(20, self._taskbar_fix)

    def quit_app(self):
        try:
            self.store.close()
        finally:
            self.destroy()

    def report_callback_exception(self, exc, val, tb):
        """Any error inside a button or key handler: log it, drop half-built dialogs, tell the user, keep running."""
        text = "".join(traceback.format_exception(exc, val, tb))
        log_path = data_dir() / "savetogrow.log"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {__version__}\n{text}")
        except OSError:
            pass
        for child in list(self.winfo_children()):
            if isinstance(child, Dialog) and not child.winfo_viewable():
                child.destroy()
        try:
            self.focus_force()
            message(self, "SOMETHING WENT WRONG", f"{val}\n\nDetails were saved to:\n{log_path}")
        except tk.TclError:
            pass

    # ---------- layout ----------
    def _build(self):
        outer = tk.Frame(self, bg=T.PANEL, bd=2, relief="raised")
        outer.pack(fill="both", expand=True)
        TitleBar(outer, self, f"SAVETOGROW  {__version__}", on_close=self.quit_app, on_minimize=self.minimize).pack(fill="x")

        body = tk.Frame(outer, bg=T.BG, padx=8, pady=8)
        body.pack(fill="both", expand=True)

        self.lcd = Lcd(body)
        self.lcd.pack(fill="x")

        nav = tk.Frame(body, bg=T.BG)
        nav.pack(fill="x", pady=(8, 0))
        BevelButton(nav, "◀", lambda: self.go_month(-1), width=3).pack(side="left")
        self.month_label = tk.Label(nav, text="", bg=T.BG, fg=T.TEXT, font=T.FONT_UI_B)
        self.month_label.pack(side="left", padx=8)
        BevelButton(nav, "▶", lambda: self.go_month(1), width=3).pack(side="left")
        BevelButton(nav, "TODAY", self.go_today).pack(side="left", padx=(8, 0))
        BevelButton(nav, "DATA", self.data_dialog).pack(side="right")
        BevelButton(nav, "PDF", self.export_pdf).pack(side="right", padx=(0, 4))

        grid = tk.Frame(body, bg=T.BG)
        grid.pack(fill="x", pady=(8, 0))
        for i in range(4):
            grid.columnconfigure(i, weight=1, uniform="btn")
        BevelButton(grid, "+ EXPENSE", self.add_expense).grid(row=0, column=0, sticky="we", padx=(0, 4))
        BevelButton(grid, "+ INCOME", self.add_income).grid(row=0, column=1, sticky="we", padx=(0, 4))
        BevelButton(grid, "CATEGORIES", self.manage_categories).grid(row=0, column=2, sticky="we", padx=(0, 4))
        BevelButton(grid, "SOURCES", self.manage_sources).grid(row=0, column=3, sticky="we")

        tabs = tk.Frame(body, bg=T.BG)
        tabs.pack(fill="x", pady=(10, 0))
        self.tab_buttons = {}
        for key, label in (("expenses", "EXPENSES"), ("income", "INCOME"), ("analysis", "ANALYSIS")):
            b = BevelButton(tabs, label, lambda k=key: self.show_tab(k), pady=2)
            b.pack(side="left", padx=(0, 3))
            self.tab_buttons[key] = b
        self.tab_info = tk.Label(tabs, text="", bg=T.BG, fg=T.MUTED, font=T.FONT_SMALL)
        self.tab_info.pack(side="right")

        area = tk.Frame(body, bg=T.BEVEL_DARK, bd=2, relief="sunken")
        area.pack(fill="both", expand=True, pady=(4, 0))
        self.listbox = tk.Listbox(area, bg=T.LIST_BG, fg=T.LIST_FG, font=T.FONT_LIST, selectbackground=T.LIST_SEL,
                                  selectforeground=T.LIST_SEL_FG, activestyle="none", highlightthickness=0, bd=0, exportselection=False)
        self.list_scroll = ttk.Scrollbar(area, orient="vertical", command=self.listbox.yview, style="Dark.Vertical.TScrollbar")
        self.listbox.configure(yscrollcommand=self.list_scroll.set)
        self.listbox.bind("<Double-Button-1>", lambda e: self.edit_selected())
        self.listbox.bind("<Delete>", lambda e: self.delete_selected())
        self.listbox.bind("<Return>", lambda e: self.edit_selected())
        self.text = tk.Text(area, bg=T.LIST_BG, fg=T.LIST_FG, font=T.FONT_LIST, wrap="none", bd=0, highlightthickness=0,
                            padx=6, pady=4, cursor="arrow", state="disabled", selectbackground=T.LIST_SEL)
        self.text_scroll = ttk.Scrollbar(area, orient="vertical", command=self.text.yview, style="Dark.Vertical.TScrollbar")
        self.text.configure(yscrollcommand=self.text_scroll.set)
        self.text.tag_configure("head", foreground=T.LCD, font=T.FONT_LCD)
        self.text.tag_configure("dim", foreground=T.LCD_DIM)
        self.text.tag_configure("bad", foreground=T.LCD_BAD)
        self.text.tag_configure("warn", foreground=T.LCD_WARN)
        self.area = area

        under = tk.Frame(body, bg=T.BG)
        under.pack(fill="x", pady=(4, 0))
        self.edit_btn = BevelButton(under, "EDIT", self.edit_selected, pady=1)
        self.edit_btn.pack(side="left")
        self.del_btn = BevelButton(under, "DELETE", self.delete_selected, pady=1)
        self.del_btn.pack(side="left", padx=(4, 0))
        self.hint = tk.Label(under, text="double-click a row to edit · Del removes it", bg=T.BG, fg=T.MUTED, font=T.FONT_SMALL)
        self.hint.pack(side="right")

        quickbar = tk.Frame(body, bg=T.BG)
        quickbar.pack(fill="x", pady=(8, 0))
        self.quick_var = tk.StringVar()
        self.quick_entry = dark_entry(quickbar, self.quick_var, width=10)
        self.quick_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.quick_entry.bind("<Return>", lambda e: self.quick_add())
        BevelButton(quickbar, "ADD", self.quick_add).pack(side="left", padx=(6, 0))
        tk.Label(body, text='quick add:  "450 dinner upi"   ·   income:  "+50000 acme salary"', bg=T.BG, fg=T.MUTED,
                 font=T.FONT_SMALL, anchor="w").pack(fill="x", pady=(3, 0))

    def _bind_keys(self):
        self.bind("<Control-n>", lambda e: self.add_expense())
        self.bind("<Control-i>", lambda e: self.add_income())
        self.bind("<Control-p>", lambda e: self.export_pdf())
        self.bind("<F1>", lambda e: self.show_tab("expenses"))
        self.bind("<F2>", lambda e: self.show_tab("income"))
        self.bind("<F3>", lambda e: self.show_tab("analysis"))
        self.bind("<Prior>", lambda e: self.go_month(-1))
        self.bind("<Next>", lambda e: self.go_month(1))
        self.bind("<Control-q>", lambda e: self.quit_app())

    # ---------- state ----------
    def go_month(self, n: int):
        self.month = shift_month(self.month, n)
        self.refresh()

    def go_today(self):
        self.month = dt.date.today().strftime("%Y-%m")
        self.refresh()

    def show_tab(self, key: str):
        self.tab = key
        self.refresh()

    def refresh(self):
        s = self.summary = summarize(self.store, self.month)
        self.month_label.configure(text=s["label"].upper())
        if s["phase"] == "current":
            caption, big, color = "LEFT THIS MONTH", rs(s["left"]), (T.LCD_BAD if s["left"] < 0 else T.LCD)
            status = f"DAY {s['day_no']}/{s['days']} · {s['days_left']} LEFT"
        elif s["phase"] == "past":
            caption, big, color = "KEPT THAT MONTH", rs(s["left"]), (T.LCD_BAD if s["left"] < 0 else T.LCD)
            status = "MONTH CLOSED"
        else:
            caption, big, color = "BUDGET FOR THE MONTH", rs(s["budget"]), T.LCD
            status = "NOT STARTED"
        over = [c["name"] for c in s["categories"] if c["status"] == "over"]
        if over:
            status += " · OVER: " + ", ".join(over).upper()
        elif s["pending"]:
            status += " · DUE: " + ", ".join(p["name"] for p in s["pending"]).upper()
        self.lcd.set_values(caption, big, color, rs(s["income"]), rs(s["spent"]), rs(s["budget"]), month_short(s["month"]), status)
        for key, b in self.tab_buttons.items():
            b.set_active(key == self.tab)
        self.listbox.pack_forget(); self.list_scroll.pack_forget()
        self.text.pack_forget(); self.text_scroll.pack_forget()
        if self.tab == "analysis":
            self.text_scroll.pack(side="right", fill="y")
            self.text.pack(fill="both", expand=True)
            self._fill_analysis(s)
            self.tab_info.configure(text="plain-text analysis")
            for b in (self.edit_btn, self.del_btn):
                b.configure(state="disabled", fg=T.MUTED)
            self.hint.configure(text="PDF saves this page as a report")
        else:
            self.list_scroll.pack(side="right", fill="y")
            self.listbox.pack(fill="both", expand=True)
            self._fill_list(s)
            for b in (self.edit_btn, self.del_btn):
                b.configure(state="normal", fg=T.BTN_TEXT)
            self.hint.configure(text="double-click a row to edit · Del removes it")

    def _fill_list(self, s: dict):
        self.listbox.delete(0, "end")
        if self.tab == "expenses":
            self.rows = list(self.store.expenses(self.month))
            total = sum(float(r["amount"]) for r in self.rows)
            self.tab_info.configure(text=f"{len(self.rows)} entries · {rs(total)}")
            for r in self.rows:
                note = r["note"] or ""
                if r["method"]:
                    note = f"{note} ({r['method']})" if note else f"({r['method']})"
                self.listbox.insert("end", f"{short_date(r['date'])}  {r['category'][:12]:<12}{rs(float(r['amount'])):>10}  {note}")
            if not self.rows:
                self.listbox.insert("end", "  no expenses this month - type one below")
        else:
            self.rows = list(self.store.income(self.month))
            total = sum(float(r["amount"]) for r in self.rows)
            self.tab_info.configure(text=f"{len(self.rows)} entries · {rs(total)}")
            for r in self.rows:
                self.listbox.insert("end", f"{short_date(r['date'])}  {r['source'][:14]:<14}{rs(float(r['amount'])):>10}  {r['note'] or ''}")
            for p in s["pending"]:
                self.listbox.insert("end", f"        {p['name'][:14]:<14}{'':>10}  {p['status']}")
                self.listbox.itemconfigure("end", fg=T.LCD_WARN)
            if not self.rows and not s["pending"]:
                self.listbox.insert("end", "  no income this month - press + INCOME or type \"+50000 jobname\"")

    def _fill_analysis(self, s: dict):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for i, line in enumerate(report_lines(s)):
            if i == 0 or line in ("CATEGORIES", "NOTES"):
                tag = "head"
            elif "OVER" in line:
                tag = "bad"
            elif "(near)" in line or "due now" in line or "not received" in line:
                tag = "warn"
            elif line.startswith("  name") or line.startswith("  *"):
                tag = "dim"
            else:
                tag = ""
            self.text.insert("end", line + "\n", tag)
        self.text.configure(state="disabled")

    def selected_row(self):
        if self.tab == "analysis" or not self.rows:
            return None
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.rows):
            return None
        return self.rows[sel[0]]

    # ---------- actions ----------
    def quick_add(self):
        text = self.quick_var.get().strip()
        if not text:
            return
        parsed = quick.parse(text, self.store.categories(), self.store.sources())
        if parsed["kind"] == "income":
            ok = self.add_income(preset=parsed)
        else:
            ok = self.add_expense(preset=parsed)
        if ok:
            self.quick_var.set("")
        self.quick_entry.focus_set()

    def add_expense(self, row=None, preset=None):
        cats = self.store.categories()
        if not cats:
            message(self, "NO CATEGORIES", "Add a category first (CATEGORIES button).")
            return False
        names = [c["name"] for c in cats]
        by_name = {c["name"]: c["id"] for c in cats}
        src = dict(row) if row else dict(preset or {})  # rows come from SQLite, presets from the quick parser
        d = Dialog(self, "EDIT EXPENSE" if row else "NEW EXPENSE")
        cat_id = src.get("category_id")
        fallback = next((n for n in names if n.lower() == "other"), names[0])  # unmatched quick entries land in Other
        cat_name = next((c["name"] for c in cats if c["id"] == cat_id), fallback)
        amount = d.entry("Amount", "" if not src or src.get("amount") in (None, "") else f"{float(src['amount']):g}")
        category = d.combo("Category", names, cat_name)
        methods = list(dict.fromkeys(list(METHODS) + self.store.methods()))
        method = d.combo("Method", methods, src.get("method", "") if src else "", readonly=False)
        date = d.entry("Date", src.get("date") if src and src.get("date") else dt.date.today().isoformat())
        note = d.entry("Note", src.get("note", "") if src else "")
        if preset and not preset.get("matched"):
            d.hint("Couldn't tell the category from the text - pick one.")

        def save():
            cid = by_name[category.get()]
            if row:
                self.store.update_expense(row["id"], date.get(), cid, amount.get(), note.get(), method.get())
            else:
                self.store.add_expense(date.get(), cid, amount.get(), note.get(), method.get())
            d.close(True)
            self.lcd.flash(f"{'SAVED' if row else 'ADDED'} {rs(float(amount.get().replace(',', '')))} · {category.get().upper()}")

        extra = [("DELETE", lambda: self._delete_expense(row, d))] if row else []
        d.actions("SAVE", save, extra)
        done = d.show()
        if done:
            self.show_tab("expenses")
        return bool(done)

    def _delete_expense(self, row, dialog):
        if confirm(self, "DELETE EXPENSE", f"Delete {rs(float(row['amount']))} · {row['category']}?", "DELETE"):
            self.store.delete_expense(row["id"])
            dialog.close(True)
            self.lcd.flash("DELETED")

    def add_income(self, row=None, preset=None):
        sources = self.store.sources()
        if not sources:
            message(self, "NO SOURCES YET", "Add your first income source (a job) and then book the income.")
            if not self._source_form():
                return False
            sources = self.store.sources()
        names = [s["name"] for s in sources]
        by_name = {s["name"]: s["id"] for s in sources}
        src = dict(row) if row else dict(preset or {})
        d = Dialog(self, "EDIT INCOME" if row else "NEW INCOME")
        sid = src.get("source_id")
        sname = next((s["name"] for s in sources if s["id"] == sid), src.get("source") if src and src.get("source") in names else names[0])
        amount = d.entry("Amount", "" if not src or src.get("amount") in (None, "") else f"{float(src['amount']):g}")
        source = d.combo("Source", names, sname)
        date = d.entry("Date", src.get("date") if src and src.get("date") else dt.date.today().isoformat())
        note = d.entry("Note", src.get("note", "") if src else "")
        if preset and not preset.get("matched"):
            d.hint("Couldn't tell the source from the text - pick one.")

        def save():
            sid2 = by_name[source.get()]
            if row:
                self.store.update_income(row["id"], date.get(), sid2, amount.get(), note.get())
            else:
                self.store.add_income(date.get(), sid2, amount.get(), note.get())
            d.close(True)
            self.lcd.flash(f"{'SAVED' if row else 'BOOKED'} {rs(float(amount.get().replace(',', '')))} · {source.get().upper()}")

        extra = [("DELETE", lambda: self._delete_income(row, d))] if row else []
        d.actions("SAVE", save, extra)
        done = d.show()
        if done:
            self.show_tab("income")
        return bool(done)

    def _delete_income(self, row, dialog):
        if confirm(self, "DELETE INCOME", f"Delete {rs(float(row['amount']))} · {row['source']}?", "DELETE"):
            self.store.delete_income(row["id"])
            dialog.close(True)
            self.lcd.flash("DELETED")

    def edit_selected(self):
        row = self.selected_row()
        if not row:
            return
        if self.tab == "expenses":
            self.add_expense(row=row)
        else:
            self.add_income(row=row)

    def delete_selected(self):
        row = self.selected_row()
        if not row:
            return
        if self.tab == "expenses":
            if confirm(self, "DELETE EXPENSE", f"Delete {rs(float(row['amount']))} · {row['category']}?", "DELETE"):
                self.store.delete_expense(row["id"])
                self.lcd.flash("DELETED")
                self.refresh()
        else:
            if confirm(self, "DELETE INCOME", f"Delete {rs(float(row['amount']))} · {row['source']}?", "DELETE"):
                self.store.delete_income(row["id"])
                self.lcd.flash("DELETED")
                self.refresh()

    # ---------- categories ----------
    def manage_categories(self):
        d = Dialog(self, "CATEGORIES", width=430)
        d.hint("Each category gets a monthly budget: a fixed amount or a percent of that month's income. "
               "Hidden categories keep their history but no longer count.")
        lb = tk.Listbox(d.body, bg=T.LIST_BG, fg=T.LIST_FG, font=T.FONT_LIST, selectbackground=T.LIST_SEL, selectforeground=T.LIST_SEL_FG,
                        activestyle="none", highlightthickness=0, bd=2, relief="sunken", height=10, exportselection=False)
        lb.grid(row=d._row, column=0, columnspan=2, sticky="we")
        d._row += 1
        rows: list = []

        def fill():
            lb.delete(0, "end")
            rows.clear()
            for c in self.store.categories(active_only=False):
                rows.append(c)
                rule = rs(float(c["value"])) if c["kind"] == "fixed" else f"{float(c['value']):g}% of income"
                flag = "" if c["active"] else "  (hidden)"
                lb.insert("end", f"{c['name'][:18]:<18}{rule:>18}{flag}")
                if not c["active"]:
                    lb.itemconfigure("end", fg=T.LCD_DIM)
            self.refresh()

        def selected():
            sel = lb.curselection()
            return rows[sel[0]] if sel else None

        def add():
            if self._category_form():
                fill()

        def edit():
            c = selected()
            if c and self._category_form(c):
                fill()

        def remove():
            c = selected()
            if not c:
                return
            if confirm(self, "REMOVE CATEGORY", f"Remove {c['name']}? If it already has expenses it will be hidden instead of deleted.", "REMOVE"):
                result = self.store.delete_category(c["id"])
                self.lcd.flash(f"{c['name'].upper()} {result.upper()}")
                fill()

        def move(n):
            c = selected()
            if c:
                self.store.move_category(c["id"], n)
                fill()
                idx = [r["id"] for r in rows].index(c["id"])
                lb.selection_set(idx)

        lb.bind("<Double-Button-1>", lambda e: edit())
        bar = tk.Frame(d.body, bg=T.PANEL)
        bar.grid(row=d._row, column=0, columnspan=2, sticky="we", pady=(6, 0))
        for text, fn in (("ADD", add), ("EDIT", edit), ("REMOVE", remove), ("▲", lambda: move(-1)), ("▼", lambda: move(1))):
            BevelButton(bar, text, fn, pady=1).pack(side="left", padx=(0, 4))
        d.actions("CLOSE", lambda: d.close(True), cancel_text="")
        for child in d.btns.winfo_children():
            if child.cget("text") == "":
                child.destroy()
        fill()
        d.show()

    def _category_form(self, c=None) -> bool:
        d = Dialog(self, "EDIT CATEGORY" if c else "NEW CATEGORY")
        name = d.entry("Name", c["name"] if c else "")
        kind = d.combo("Budget type", list(KIND_LABELS.values()), KIND_LABELS[c["kind"]] if c else KIND_LABELS["fixed"])
        value = d.entry("Amount / %", f"{float(c['value']):g}" if c else "")
        active = d.check("Active (counts this month)", bool(c["active"]) if c else True)
        d.hint("Fixed: the same rupee amount every month. Percent: a share of that month's income, so it moves with your pay.")

        def save():
            k = LABEL_KINDS[kind.get()]
            if c:
                self.store.update_category(c["id"], name.get(), k, value.get(), active.get())
            else:
                self.store.add_category(name.get(), k, value.get())
            d.close(True)

        d.actions("SAVE", save)
        return bool(d.show())

    # ---------- sources ----------
    def manage_sources(self):
        d = Dialog(self, "INCOME SOURCES", width=430)
        d.hint("One line per job. Set an expected pay day and the app tells you which salary hasn't arrived yet.")
        lb = tk.Listbox(d.body, bg=T.LIST_BG, fg=T.LIST_FG, font=T.FONT_LIST, selectbackground=T.LIST_SEL, selectforeground=T.LIST_SEL_FG,
                        activestyle="none", highlightthickness=0, bd=2, relief="sunken", height=8, exportselection=False)
        lb.grid(row=d._row, column=0, columnspan=2, sticky="we")
        d._row += 1
        rows: list = []

        def fill():
            lb.delete(0, "end")
            rows.clear()
            for s in self.store.sources(active_only=False):
                rows.append(s)
                pay = f"pay day {s['pay_day']}" if s["pay_day"] else "no pay day"
                flag = "" if s["active"] else "  (hidden)"
                lb.insert("end", f"{s['name'][:20]:<20}{pay:>14}{flag}")
                if not s["active"]:
                    lb.itemconfigure("end", fg=T.LCD_DIM)
            self.refresh()

        def selected():
            sel = lb.curselection()
            return rows[sel[0]] if sel else None

        def add():
            if self._source_form():
                fill()

        def edit():
            s = selected()
            if s and self._source_form(s):
                fill()

        def remove():
            s = selected()
            if not s:
                return
            if confirm(self, "REMOVE SOURCE", f"Remove {s['name']}? If it already has income entries it will be hidden instead of deleted.", "REMOVE"):
                result = self.store.delete_source(s["id"])
                self.lcd.flash(f"{s['name'].upper()} {result.upper()}")
                fill()

        lb.bind("<Double-Button-1>", lambda e: edit())
        bar = tk.Frame(d.body, bg=T.PANEL)
        bar.grid(row=d._row, column=0, columnspan=2, sticky="we", pady=(6, 0))
        for text, fn in (("ADD", add), ("EDIT", edit), ("REMOVE", remove)):
            BevelButton(bar, text, fn, pady=1).pack(side="left", padx=(0, 4))
        d.actions("CLOSE", lambda: d.close(True), cancel_text="")
        for child in d.btns.winfo_children():
            if child.cget("text") == "":
                child.destroy()
        fill()
        d.show()

    def _source_form(self, s=None) -> bool:
        d = Dialog(self, "EDIT SOURCE" if s else "NEW INCOME SOURCE")
        name = d.entry("Name", s["name"] if s else "")
        pay_day = d.entry("Expected pay day", str(s["pay_day"]) if s and s["pay_day"] else "", width=8)
        active = d.check("Active", bool(s["active"]) if s else True)
        d.hint("Pay day is optional (1-31). Leave it blank for irregular income like freelance or gifts.")

        def save():
            pd = pay_day.get().strip()
            day = int(pd) if pd else None
            if s:
                self.store.update_source(s["id"], name.get(), day, active.get())
            else:
                self.store.add_source(name.get(), day)
            d.close(True)

        d.actions("SAVE", save)
        return bool(d.show())

    # ---------- files ----------
    def export_pdf(self):
        from .report import write_report

        s = self.summary or summarize(self.store, self.month)
        default_dir = Path.home() / "Documents"
        path = filedialog.asksaveasfilename(parent=self, title="Save PDF report", defaultextension=".pdf",
                                            initialdir=str(default_dir if default_dir.exists() else Path.home()),
                                            initialfile=f"Savetogrow-{self.month}.pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            write_report(path, s, self.store.expenses(self.month), self.store.income(self.month))
        except OSError as e:
            message(self, "COULDN'T SAVE THE PDF", f"{e}\n\nIf that PDF is open in another program, close it and try again.")
            return
        self.lcd.flash("PDF SAVED")
        self.saved_dialog("PDF SAVED", path)

    def saved_dialog(self, title: str, path):
        d = Dialog(self, title, width=420)
        tk.Label(d.body, text="Saved to:", bg=T.PANEL, fg=T.TEXT, font=T.FONT_SMALL_B, anchor="w").grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(d.body, text=str(path), bg=T.PANEL, fg=T.LCD, font=T.FONT_SMALL, anchor="w", wraplength=380, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        def open_it():
            try:
                os.startfile(path)  # noqa: S606 - opens the file with the user's default app
            except OSError as e:
                message(self, "COULDN'T OPEN", str(e))
                return
            d.close(True)

        d.actions("OPEN", open_it, cancel_text="CLOSE")
        d.show()

    def data_dialog(self):
        """Where the data lives, plus back up / restore / portable mode."""
        d = Dialog(self, "YOUR DATA", width=440)
        portable = is_portable(self.store.path)
        where = "portable: in the data folder next to Savetogrow.exe" if portable else "this Windows user's app data"
        tk.Label(d.body, text=f"Data file ({where}):", bg=T.PANEL, fg=T.TEXT, font=T.FONT_SMALL_B, anchor="w").grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(d.body, text=str(self.store.path), bg=T.PANEL, fg=T.LCD, font=T.FONT_SMALL, anchor="w", wraplength=400, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        d._row = 2
        d.hint("BACK UP copies the file anywhere you like. RESTORE replaces everything here with a backup. "
               "MAKE PORTABLE moves the data next to the exe so you can copy Savetogrow.exe and its data folder "
               "together to another laptop.")
        bar = tk.Frame(d.body, bg=T.PANEL)
        bar.grid(row=d._row, column=0, columnspan=2, sticky="we", pady=(6, 0))
        BevelButton(bar, "BACK UP…", lambda: self.backup(d), pady=1).pack(side="left", padx=(0, 4))
        BevelButton(bar, "RESTORE…", lambda: self.restore(d), pady=1).pack(side="left", padx=(0, 4))
        BevelButton(bar, "OPEN FOLDER", lambda: self.open_folder(), pady=1).pack(side="left", padx=(0, 4))
        if not portable:
            BevelButton(bar, "MAKE PORTABLE", lambda: self.make_portable(d), pady=1).pack(side="left")
        d.actions("CLOSE", lambda: d.close(True), cancel_text="")
        for child in d.btns.winfo_children():
            if child.cget("text") == "":
                child.destroy()
        d.show()

    def backup(self, parent_dialog=None):
        path = filedialog.asksaveasfilename(parent=parent_dialog or self, title="Back up data file", defaultextension=".db",
                                            initialfile=f"savetogrow-backup-{dt.date.today().isoformat()}.db", filetypes=[("Savetogrow data", "*.db")])
        if not path:
            return
        self.store.conn.commit()
        try:
            shutil.copyfile(self.store.path, path)
        except OSError as e:
            message(self, "COULDN'T SAVE THE BACKUP", str(e))
            return
        self.lcd.flash("BACKUP SAVED")
        self.saved_dialog("BACKUP SAVED", path)

    def restore(self, parent_dialog=None):
        path = filedialog.askopenfilename(parent=parent_dialog or self, title="Restore a Savetogrow backup", filetypes=[("Savetogrow data", "*.db"), ("All files", "*.*")])
        if not path:
            return
        if not looks_like_savetogrow_db(Path(path)):
            message(self, "NOT A SAVETOGROW FILE", "That file doesn't look like a Savetogrow data file.")
            return
        if not confirm(self, "RESTORE BACKUP", "Replace everything in this Savetogrow with the backup? Current data will be overwritten.", "RESTORE"):
            return
        self.switch_store(Path(path), copy_into=self.store.path)
        if parent_dialog is not None:
            parent_dialog.close(True)
        self.lcd.flash("DATA RESTORED")

    def make_portable(self, parent_dialog=None):
        target_dir = portable_dir()
        if not confirm(self, "MAKE PORTABLE", f"Copy your data to:\n{target_dir}\n\nFrom then on Savetogrow uses that folder whenever it sits next to the exe. "
                                              "To move to another laptop, copy Savetogrow.exe together with the data folder.", "MAKE PORTABLE"):
            return
        target_dir.mkdir(parents=True, exist_ok=True)
        self.switch_store(self.store.path, copy_into=target_dir / "savetogrow.db")
        if parent_dialog is not None:
            parent_dialog.close(True)
        self.lcd.flash("PORTABLE MODE ON")
        message(self, "PORTABLE MODE", f"Your data now lives at:\n{self.store.path}\n\nKeep the exe and the data folder together.")

    def switch_store(self, source: Path, copy_into: Path):
        """Copy `source` over `copy_into` and reopen the store on it (used by restore and make-portable)."""
        self.store.conn.commit()
        self.store.close()
        if Path(source).resolve() != Path(copy_into).resolve():
            shutil.copyfile(source, copy_into)
        self.store = Store(copy_into)
        self.refresh()

    def open_folder(self):
        try:
            os.startfile(self.store.path.parent)  # noqa: S606 - opens Explorer on the data folder
        except OSError as e:
            message(self, "COULDN'T OPEN", str(e))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
