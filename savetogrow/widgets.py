"""Skinned Tk widgets: striped title bar, bevelled buttons, LCD panel, dark dialogs."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from . import theme as T


def setup_ttk(root: tk.Misc) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Dark.TCombobox", fieldbackground=T.ENTRY_BG, background=T.BTN, foreground=T.LCD, arrowcolor=T.TEXT,
                    bordercolor=T.BEVEL_DARK, lightcolor=T.BEVEL_LIGHT, darkcolor=T.BEVEL_DARK, insertcolor=T.LCD,
                    selectbackground=T.LIST_SEL, selectforeground=T.LIST_SEL_FG, padding=3)
    style.map("Dark.TCombobox", fieldbackground=[("readonly", T.ENTRY_BG), ("disabled", T.PANEL)],
              foreground=[("readonly", T.LCD)], selectbackground=[("readonly", T.ENTRY_BG)], selectforeground=[("readonly", T.LCD)])
    style.configure("Dark.Vertical.TScrollbar", background=T.BTN, troughcolor=T.BG, arrowcolor=T.TEXT,
                    bordercolor=T.BEVEL_DARK, lightcolor=T.BEVEL_LIGHT, darkcolor=T.BEVEL_DARK)
    style.map("Dark.Vertical.TScrollbar", background=[("active", T.BTN_HOVER)])
    root.option_add("*TCombobox*Listbox.background", T.LIST_BG)
    root.option_add("*TCombobox*Listbox.foreground", T.LIST_FG)
    root.option_add("*TCombobox*Listbox.selectBackground", T.LIST_SEL)
    root.option_add("*TCombobox*Listbox.selectForeground", T.LIST_SEL_FG)
    root.option_add("*TCombobox*Listbox.font", T.FONT_LIST)


class TitleBar(tk.Frame):
    """Winamp-style striped bar: drag to move, tiny minimise/close buttons on the right."""

    def __init__(self, parent, window: tk.Misc, title: str, on_close, on_minimize=None, height: int = 20):
        super().__init__(parent, bg=T.TITLE_B, height=height)
        self.window = window
        self.canvas = tk.Canvas(self, height=height, bg=T.TITLE_B, highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", expand=True, side="left")
        self.title = title
        self.canvas.bind("<Configure>", self._draw)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        box = tk.Frame(self, bg=T.TITLE_B)
        box.pack(side="right", padx=3)
        if on_minimize:
            self._tiny(box, "_", on_minimize)
        self._tiny(box, "×", on_close)

    def _tiny(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg=T.BTN, fg=T.BTN_TEXT, font=("Arial", 8, "bold"), width=2, relief="raised", bd=1, cursor="hand2")
        b.pack(side="left", padx=1, pady=2)
        b.bind("<ButtonPress-1>", lambda e: b.configure(relief="sunken"))
        b.bind("<ButtonRelease-1>", lambda e: (b.configure(relief="raised"), cmd()))

    def _draw(self, _e=None):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        for y in range(2, h - 2, 2):
            c.create_line(4, y, w - 4, y, fill=T.TITLE_A)
        text_w = len(self.title) * 7 + 18
        x0 = (w - text_w) // 2
        c.create_rectangle(x0, 2, x0 + text_w, h - 2, fill=T.TITLE_B, outline=T.TITLE_B)
        c.create_text(w // 2, h // 2, text=self.title, fill=T.TITLE_FG, font=T.FONT_SMALL_B)

    def _press(self, e):
        self._dx, self._dy = e.x_root - self.window.winfo_x(), e.y_root - self.window.winfo_y()

    def _drag(self, e):
        self.window.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")


class BevelButton(tk.Label):
    """A chunky 3D button. Supports an 'active' look for tab-style use."""

    def __init__(self, parent, text: str, command=None, width=None, font=T.FONT_SMALL_B, pady=3, **kw):
        if width is not None:
            kw["width"] = width
        super().__init__(parent, text=text, bg=T.BTN, fg=T.BTN_TEXT, font=font, relief="raised", bd=2, padx=6, pady=pady,
                         cursor="hand2", **kw)
        self.command = command
        self.active = False
        self.bind("<Enter>", lambda e: self.configure(bg=T.BTN_HOVER))
        self.bind("<Leave>", lambda e: self.configure(bg=T.BTN_DOWN if self.active else T.BTN))
        self.bind("<ButtonPress-1>", lambda e: self.configure(relief="sunken"))
        self.bind("<ButtonRelease-1>", self._release)

    def _release(self, e):
        self.configure(relief="sunken" if self.active else "raised")
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        if inside and self.command and str(self["state"]) != "disabled":
            self.command()

    def set_active(self, on: bool) -> None:
        self.active = on
        self.configure(relief="sunken" if on else "raised", fg=T.BTN_ACTIVE_TEXT if on else T.BTN_TEXT,
                       bg=T.BTN_DOWN if on else T.BTN)


class Lcd(tk.Frame):
    """The green display: headline amount, income/spent/budget readouts, month and a status line."""

    def __init__(self, parent):
        super().__init__(parent, bg=T.BEVEL_DARK, bd=2, relief="sunken")
        inner = tk.Frame(self, bg=T.LCD_BG, padx=10, pady=6)
        inner.pack(fill="both", expand=True)
        top = tk.Frame(inner, bg=T.LCD_BG)
        top.pack(fill="x")
        self.caption = tk.Label(top, text="LEFT THIS MONTH", bg=T.LCD_BG, fg=T.LCD_DIM, font=T.FONT_LCD, anchor="w")
        self.caption.pack(side="left")
        self.month = tk.Label(top, text="", bg=T.LCD_BG, fg=T.LCD, font=T.FONT_LCD, anchor="e")
        self.month.pack(side="right")
        self.big = tk.Label(inner, text="₹0", bg=T.LCD_BG, fg=T.LCD, font=T.FONT_LCD_BIG, anchor="w")
        self.big.pack(fill="x")
        row = tk.Frame(inner, bg=T.LCD_BG)
        row.pack(fill="x")
        self.cells = {}
        for key in ("INCOME", "SPENT", "BUDGET"):
            cell = tk.Frame(row, bg=T.LCD_BG)
            cell.pack(side="left", expand=True, fill="x")
            tk.Label(cell, text=key, bg=T.LCD_BG, fg=T.LCD_DIM, font=T.FONT_SMALL_B, anchor="w").pack(anchor="w")
            lab = tk.Label(cell, text="₹0", bg=T.LCD_BG, fg=T.LCD, font=T.FONT_LCD_MID, anchor="w")
            lab.pack(anchor="w")
            self.cells[key] = lab
        self.status = tk.Label(inner, text="", bg=T.LCD_BG, fg=T.LCD_DIM, font=T.FONT_LCD, anchor="w")
        self.status.pack(fill="x", pady=(4, 0))
        self._status_default = ""
        self._flash_job = None

    def set_values(self, caption: str, big: str, big_color: str, income: str, spent: str, budget: str, month: str, status: str) -> None:
        self.caption.configure(text=caption)
        self.big.configure(text=big, fg=big_color)
        self.cells["INCOME"].configure(text=income)
        self.cells["SPENT"].configure(text=spent)
        self.cells["BUDGET"].configure(text=budget)
        self.month.configure(text=month)
        self._status_default = status
        if self._flash_job is None:
            self.status.configure(text=status, fg=T.LCD_DIM)

    def flash(self, text: str, color: str = T.LCD, ms: int = 3500) -> None:
        if self._flash_job:
            self.after_cancel(self._flash_job)
        self.status.configure(text=text, fg=color)
        self._flash_job = self.after(ms, self._unflash)

    def _unflash(self):
        self._flash_job = None
        self.status.configure(text=self._status_default, fg=T.LCD_DIM)


def hwnd_of(widget: tk.Misc) -> int:
    """The real OS window handle of a Tk toplevel (Tk wraps its content in a child window)."""
    import ctypes

    wid = widget.winfo_id()
    return ctypes.windll.user32.GetParent(wid) or wid


def set_owner(window: tk.Misc, owner: tk.Misc) -> bool:
    """Make `window` an owned window of `owner` at the OS level.

    Tk's transient() does nothing for borderless (overrideredirect) toplevels on Windows, so a click on the main
    window could raise it above a modal dialog that still held the input grab: the app looked frozen. An owned
    window always stays above its owner.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        import ctypes.wintypes as w

        user32 = ctypes.windll.user32
        user32.GetParent.restype = w.HWND
        user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        gwlp_hwndparent = -8
        user32.SetWindowLongPtrW(hwnd_of(window), gwlp_hwndparent, hwnd_of(owner))
        return True
    except Exception:
        return False


def dark_entry(parent, textvariable=None, width=22, **kw) -> tk.Entry:
    return tk.Entry(parent, textvariable=textvariable, width=width, bg=T.ENTRY_BG, fg=T.LCD, insertbackground=T.LCD,
                    relief="sunken", bd=2, font=T.FONT_LIST, highlightthickness=0, selectbackground=T.LIST_SEL,
                    selectforeground=T.LIST_SEL_FG, **kw)


def dark_label(parent, text, **kw) -> tk.Label:
    kw.setdefault("bg", T.PANEL)
    kw.setdefault("fg", T.TEXT)
    kw.setdefault("font", T.FONT_SMALL_B)
    return tk.Label(parent, text=text, **kw)


class Dialog(tk.Toplevel):
    """A borderless, skinned, modal dialog with a simple form builder."""

    def __init__(self, app: tk.Misc, title: str, width: int = 400):
        super().__init__(app)
        self.withdraw()  # invisible until show(); a failure while building the form can't strand a window on screen
        self.app = app
        self.result = None
        self._ok = None
        self._grab_tries = 0
        self.overrideredirect(True)
        self.configure(bg=T.BEVEL_DARK)
        self.transient(app)
        self.width = width
        frame = tk.Frame(self, bg=T.PANEL, bd=2, relief="raised")
        frame.pack(fill="both", expand=True)
        TitleBar(frame, self, title, on_close=self.cancel).pack(fill="x")
        self.body = tk.Frame(frame, bg=T.PANEL, padx=12, pady=10)
        self.body.pack(fill="both", expand=True)
        self.body.columnconfigure(1, weight=1)
        self.error_label = tk.Label(frame, text="", bg=T.PANEL, fg=T.LCD_BAD, font=T.FONT_SMALL_B, anchor="w", wraplength=width - 30, justify="left")
        self.error_label.pack(fill="x", padx=12)
        self.btns = tk.Frame(frame, bg=T.PANEL, padx=12, pady=8)
        self.btns.pack(fill="x")
        self._row = 0
        self._first = None
        self.bind("<Escape>", lambda e: self.cancel())
        self.bind("<Return>", self._on_return)

    # ----- form builders -----
    def _label(self, text):
        dark_label(self.body, text, anchor="e").grid(row=self._row, column=0, sticky="e", padx=(0, 8), pady=3)

    def entry(self, label: str, value: str = "", width: int = 26) -> tk.StringVar:
        var = tk.StringVar(value=value)
        self._label(label)
        e = dark_entry(self.body, var, width=width)
        e.grid(row=self._row, column=1, sticky="we", pady=3)
        self._first = self._first or e
        self._row += 1
        return var

    def combo(self, label: str, values: list[str], value: str = "", readonly: bool = True, width: int = 24) -> tk.StringVar:
        var = tk.StringVar(value=value)
        self._label(label)
        cb = ttk.Combobox(self.body, textvariable=var, values=values, style="Dark.TCombobox", width=width,
                          state="readonly" if readonly else "normal", font=T.FONT_LIST)
        cb.grid(row=self._row, column=1, sticky="we", pady=3)
        self._first = self._first or cb
        self._row += 1
        return var

    def check(self, label: str, value: bool = True) -> tk.BooleanVar:
        var = tk.BooleanVar(value=value)
        self._label("")
        cb = tk.Checkbutton(self.body, text=label, variable=var, bg=T.PANEL, fg=T.TEXT, selectcolor=T.ENTRY_BG,
                            activebackground=T.PANEL, activeforeground=T.TEXT, font=T.FONT_SMALL_B, highlightthickness=0)
        cb.grid(row=self._row, column=1, sticky="w", pady=3)
        self._row += 1
        return var

    def hint(self, text: str) -> None:
        tk.Label(self.body, text=text, bg=T.PANEL, fg=T.MUTED, font=T.FONT_SMALL, anchor="w", justify="left",
                 wraplength=self.width - 40).grid(row=self._row, column=0, columnspan=2, sticky="w", pady=(2, 4))
        self._row += 1

    def actions(self, ok_text: str, on_ok, extra: list[tuple[str, object]] | None = None, cancel_text: str = "CANCEL") -> None:
        self._ok = on_ok
        BevelButton(self.btns, cancel_text, self.cancel).pack(side="right", padx=(4, 0))
        BevelButton(self.btns, ok_text, self._run_ok).pack(side="right", padx=(4, 0))
        for text, fn in extra or []:
            BevelButton(self.btns, text, fn).pack(side="left", padx=(0, 4))

    # ----- lifecycle -----
    def show(self):
        self.update_idletasks()  # size it while hidden, then place it over the main window
        w = max(self.width, self.winfo_reqwidth())
        h = self.winfo_reqheight()
        ax, ay = self.app.winfo_rootx(), self.app.winfo_rooty()
        aw, ah = self.app.winfo_width(), self.app.winfo_height()
        self.geometry(f"{w}x{h}+{ax + (aw - w) // 2}+{ay + max(20, (ah - h) // 3)}")
        set_owner(self, self.app)  # keeps the dialog above the main window no matter what gets clicked
        self.deiconify()
        self.lift()
        self._try_grab()  # the window maps on the next loop turn; keep trying until it is viewable
        self.app.active_dialog = self
        try:
            self.app.wait_window(self)
        finally:
            if getattr(self.app, "active_dialog", None) is self:
                self.app.active_dialog = None
        return self.result

    def bring_front(self) -> None:
        if self.winfo_exists():
            self.lift()
            try:
                self.focus_force()
            except tk.TclError:
                pass

    def _try_grab(self):
        if not self.winfo_exists():
            return
        try:
            self.grab_set()
        except tk.TclError:
            self._grab_tries += 1
            if self._grab_tries < 40:
                self.after(25, self._try_grab)
            return
        if self._first is not None:
            self._first.focus_force()
            if isinstance(self._first, tk.Entry):
                self._first.selection_range(0, "end")

    def error(self, text: str) -> None:
        self.error_label.configure(text=text)
        self.bell()

    def _on_return(self, _e=None):
        focus = self.focus_get()
        if isinstance(focus, ttk.Combobox):
            return
        self._run_ok()

    def _run_ok(self):
        if self._ok is None:
            return
        try:
            self._ok()
        except ValueError as e:
            self.error(str(e))

    def close(self, result=True) -> None:
        self.result = result
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        try:
            self.app.focus_force()  # hand keyboard focus back to the main window
        except tk.TclError:
            pass

    def cancel(self) -> None:
        self.close(None)


def message(app, title: str, text: str) -> None:
    d = Dialog(app, title, width=380)
    tk.Label(d.body, text=text, bg=T.PANEL, fg=T.TEXT, font=T.FONT_UI, justify="left", wraplength=340).grid(row=0, column=0, columnspan=2, sticky="w")
    d.actions("OK", lambda: d.close(True), cancel_text="")
    for child in d.btns.winfo_children():
        if child.cget("text") == "":
            child.destroy()
    d.show()


def confirm(app, title: str, text: str, ok_text: str = "YES") -> bool:
    d = Dialog(app, title, width=380)
    tk.Label(d.body, text=text, bg=T.PANEL, fg=T.TEXT, font=T.FONT_UI, justify="left", wraplength=340).grid(row=0, column=0, columnspan=2, sticky="w")
    d.actions(ok_text, lambda: d.close(True), cancel_text="NO")
    return bool(d.show())
