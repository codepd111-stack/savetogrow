"""Entry point for `python launcher.py` and for the PyInstaller build.

`Savetogrow.exe --pdf-check out.pdf` writes a sample report without opening the window (used to verify builds).
"""
import sys

if "--pdf-check" in sys.argv:
    from savetogrow.report import self_check

    self_check(sys.argv[sys.argv.index("--pdf-check") + 1])
else:
    from savetogrow.app import main

    if __name__ == "__main__":
        main()
