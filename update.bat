@echo off
chcp 65001 >nul
title Nero - Update pengunduh
cd /d "%~dp0"
REM YouTube & TikTok sering berubah. Jalankan ini bila unduhan tiba-tiba gagal.
REM python lingkungan dipanggil langsung (tanpa activate.bat) supaya folder aplikasi aman di-rename/dipindah
".venv\Scripts\python.exe" -m pip install --upgrade "yt-dlp[default]"
REM yt-dlp memakai Deno untuk YouTube; Deno yang terlalu lama juga bisa membuat unduhan gagal
where deno >nul 2>nul && winget upgrade -e --id DenoLand.Deno --accept-package-agreements --accept-source-agreements
echo.
echo Selesai. Jalankan run.bat lagi.
pause
