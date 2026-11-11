@echo off
chcp 65001 >nul
title Nero
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Aplikasi belum diinstal. Jalankan install.bat terlebih dahulu.
  pause
  exit /b
)
REM tambahkan lokasi Deno & FFmpeg dari winget ke PATH sesi ini (jika baru diinstal)
set "PATH=%PATH%;%USERPROFILE%\.deno\bin;%LOCALAPPDATA%\Microsoft\WinGet\Links"
REM python lingkungan dipanggil langsung (tanpa activate.bat) supaya folder aplikasi aman di-rename/dipindah
".venv\Scripts\python.exe" app.py
pause
