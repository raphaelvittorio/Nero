@echo off
chcp 65001 >nul
title ClipMaker
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Aplikasi belum diinstal. Jalankan install.bat terlebih dahulu.
  pause
  exit /b
)
REM tambahkan lokasi Deno & FFmpeg dari winget ke PATH sesi ini (jika baru diinstal)
set "PATH=%PATH%;%USERPROFILE%\.deno\bin;%LOCALAPPDATA%\Microsoft\WinGet\Links"
call ".venv\Scripts\activate.bat"
python app.py
pause
