@echo off
chcp 65001 >nul
title Nero - Instalasi
cd /d "%~dp0"
echo ============================================================
echo   Nero - Instalasi (cukup sekali)
echo ============================================================
echo.

REM ---- 1. Python 3.14 (versi yang dipakai requirements-lock.txt) ----
set "PY="
where py >nul 2>nul && py -3.14 -c "pass" >nul 2>nul && set "PY=py -3.14"
if not defined PY (
  where python >nul 2>nul && python -c "import sys; exit(0 if sys.version_info[:2]==(3,14) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [1/4] Python 3.14 belum ada. Menginstal Python 3.14...
  winget install -e --id Python.Python.3.14 --scope user --accept-package-agreements --accept-source-agreements
  echo.
  echo Python selesai diinstal. TUTUP jendela ini lalu jalankan install.bat sekali lagi.
  pause
  exit /b
)
echo [1/4] Python 3.14 ditemukan.

REM ---- 2. Deno (dibutuhkan yt-dlp untuk YouTube) & FFmpeg ----
where deno >nul 2>nul
if errorlevel 1 (
  echo [2/4] Menginstal Deno, dibutuhkan agar unduhan YouTube lancar...
  winget install -e --id DenoLand.Deno --accept-package-agreements --accept-source-agreements
) else (
  echo [2/4] Deno sudah ada.
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo       Menginstal FFmpeg...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
)

REM ---- 3. Lingkungan Python ----
echo [3/4] Menyiapkan lingkungan Python...
REM lingkungan lama dari Python versi sebelumnya dibuat ulang supaya memakai Python 3.14
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; exit(0 if sys.version_info[:2]==(3,14) else 1)" >nul 2>nul || (
    echo       Lingkungan lama memakai Python versi lain, membuat ulang...
    rmdir /s /q ".venv"
  )
)
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
REM python lingkungan dipanggil langsung (tanpa activate.bat) supaya folder aplikasi aman di-rename/dipindah
set "VPY=%~dp0.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip
REM versi yang sudah terbukti jalan; bila tidak cocok dengan versi Python ini, pakai versi fleksibel
"%VPY%" -m pip install -r requirements-lock.txt
if errorlevel 1 (
  echo       Versi terkunci tidak cocok dengan Python ini, memakai versi fleksibel...
  "%VPY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo GAGAL menginstal paket. Periksa koneksi internet lalu jalankan install.bat lagi.
    pause
    exit /b 1
  )
)

REM ---- GPU NVIDIA: transkrip jauh lebih cepat ----
where nvidia-smi >nul 2>nul
if not errorlevel 1 (
  echo       Kartu NVIDIA terdeteksi: memasang pustaka CUDA, sekitar 1 GB...
  "%VPY%" -m pip install -r requirements-gpu.txt
  if errorlevel 1 echo       Pustaka GPU gagal dipasang. Aplikasi tetap jalan memakai CPU.
)

REM ---- 4. Unduh model transkrip sekarang supaya pemakaian pertama cepat ----
echo [4/4] Mengunduh model transkrip (sekitar 500 MB, sekali saja)...
"%VPY%" -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('Model siap.')"
"%VPY%" -c "from features.clip import engine as c; print('FFmpeg:', c.ffmpeg_exe()); print('Transkrip memakai:', 'GPU' if c.transcribe_device() == 'cuda' else 'CPU')"

echo.
echo ============================================================
echo   Instalasi selesai! Klik dua kali run.bat untuk memulai.
echo ============================================================
pause
