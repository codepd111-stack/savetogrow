@echo off
rem Run Savetogrow from source (needs Python 3.11+). The built exe in dist\ doesn't need this.
cd /d "%~dp0"
start "" pythonw launcher.py
