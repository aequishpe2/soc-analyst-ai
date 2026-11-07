@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0scripts\Stop-Local.ps1"
pause
