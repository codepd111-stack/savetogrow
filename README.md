# Savetogrow Classic

A small, offline expense tracker that looks like a 90s media player. One window, green LCD readout,
bevelled buttons. No server, no account, no internet, no charts: just your numbers and plain-text analysis.

## What it does

- **Income from several jobs.** Each job is a *source*. Book income when it arrives (amounts can differ every month);
  give a source an expected pay day and the app tells you which salary hasn't come in yet.
- **Pre-planned categories.** Every category has a monthly budget: a fixed rupee amount or a percent of that
  month's income. Months reset; nothing carries over.
- **Quick entry.** Type `450 dinner upi` and press Enter: amount, category, method, date and note are filled in
  from simple rules, you confirm, done. `+50000 acme salary` books income the same way.
- **Text analysis.** Spent / limit / left per category, over-budget warnings, biggest category, daily pace and
  projection, what you can still spend per day, income still expected, comparison with last month.
- **PDF report** of any month: summary tiles, income and category tables with colour-coded status, the notes, and
  every entry of the month, set in Arial with proper rupee signs. The data file can be backed up, restored or made
  portable from the DATA button.

## Run it

- **Built app:** `Savetogrow.exe` is one self-contained file (Python and Tk are inside). Double-click it; copy it to
  any 64-bit Windows 10/11 PC and it runs there too, nothing to install. The first run on a new PC may show a
  SmartScreen prompt because the file isn't code-signed: *More info → Run anyway*.
- **From source:** `run.bat`, or `python launcher.py` (Python 3.11+, nothing to install).

## Where the data is

- Normally `%LOCALAPPDATA%\Savetogrow\savetogrow.db`, separate for each Windows user and each PC.
- **Portable mode:** press **DATA → MAKE PORTABLE** and the data moves into a `data` folder next to the exe. From
  then on, wherever that exe + folder pair goes (another laptop, a USB stick), the numbers go with it.
- **DATA → BACK UP / RESTORE** copy the data file out or bring a backup in. `SAVETOGROW_DATA` overrides everything.

## Keys

| Key | Does |
| --- | --- |
| Enter in the bottom box | quick add |
| Ctrl+N / Ctrl+I | new expense / new income |
| F1 / F2 / F3 | Expenses / Income / Analysis tab |
| PgUp / PgDn | previous / next month |
| Double-click, Enter, Delete on a row | edit / edit / delete |
| Ctrl+P | PDF report |
| Ctrl+Q | quit |

## Build the exe

`build\build_exe.bat` installs PyInstaller, draws the icon, builds `dist\Savetogrow.exe` and copies it to the Desktop.

## Layout

```
launcher.py          entry point (also what PyInstaller bundles)
savetogrow/
  app.py             main window and dialogs
  widgets.py         title bar, bevel buttons, LCD panel, dark dialogs
  theme.py           colours and fonts
  store.py           SQLite data layer and validation
  analysis.py        month summary, notes and the text report
  quick.py           rule-based quick entry parser
  report.py          the PDF report (reportlab + system Arial); `--pdf-check` self-test
  pdf.py             tiny dependency-free fallback PDF writer
tests/               pytest suite (python -m pytest)
build/               icon, exe build script, copy-to-desktop script
```
