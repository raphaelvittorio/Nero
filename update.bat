@echo off
chcp 65001 >nul
title ClipMaker - Update pengunduh
cd /d "%~dp0"
REM YouTube & TikTok sering berubah. Jalankan ini bila unduhan tiba-tiba gagal.
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade "yt-dlp[default]"
echo.
echo Selesai. Jalankan run.bat lagi.
pause
