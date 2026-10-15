@echo off
rem Builds dist\Savetogrow.exe (single file, no console) and puts a shortcut on the Desktop.
cd /d "%~dp0\.."
python -m pip install --quiet pyinstaller || goto :fail
python build\make_icon.py || goto :fail
rem reportlab needs Pillow, but not numpy or the other optional extras Pillow drags in (27 MB); leave those out.
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Savetogrow --icon "%~dp0icon.ico" ^
  --exclude-module numpy --exclude-module chardet --exclude-module charset_normalizer ^
  --exclude-module cryptography --exclude-module matplotlib --exclude-module pytest --exclude-module setuptools ^
  --exclude-module pkg_resources --exclude-module pymupdf --exclude-module fitz ^
  --distpath dist --workpath build\work --specpath build launcher.py || goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -File build\install_to_desktop.ps1 || goto :fail
echo.
echo Done. dist\Savetogrow.exe is built and a copy is on your Desktop. That one file runs on any 64-bit Windows PC.
pause
exit /b 0
:fail
echo Build failed. See the messages above.
pause
exit /b 1
