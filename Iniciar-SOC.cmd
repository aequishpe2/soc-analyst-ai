@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0scripts\Start-Local.ps1" -WithAI
pause
