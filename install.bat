@echo off
chcp 65001 >nul
title ClipMaker - Instalasi
cd /d "%~dp0"
echo ============================================================
echo   ClipMaker - Instalasi (cukup sekali)
echo ============================================================
echo.

REM ---- 1. Python ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if defined PY (
  %PY% -c "import sys; exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul || set "PY="
)
if not defined PY (
  echo [1/4] Python belum ada. Menginstal Python 3.12...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  echo.
  echo Python selesai diinstal. TUTUP jendela ini lalu jalankan install.bat sekali lagi.
  pause
  exit /b
)
echo [1/4] Python ditemukan.

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
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
REM versi yang sudah terbukti jalan; bila tidak cocok dengan versi Python ini, pakai versi fleksibel
python -m pip install -r requirements-lock.txt
if errorlevel 1 (
  echo       Versi terkunci tidak cocok dengan Python ini, memakai versi fleksibel...
  python -m pip install -r requirements.txt
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
  python -m pip install -r requirements-gpu.txt
  if errorlevel 1 echo       Pustaka GPU gagal dipasang. Aplikasi tetap jalan memakai CPU.
)

REM ---- 4. Unduh model transkrip sekarang supaya pemakaian pertama cepat ----
echo [4/4] Mengunduh model transkrip (sekitar 500 MB, sekali saja)...
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('Model siap.')"
python -c "import clipper_core as c; print('FFmpeg:', c.ffmpeg_exe()); print('Transkrip memakai:', 'GPU' if c.transcribe_device() == 'cuda' else 'CPU')"

echo.
echo ============================================================
echo   Instalasi selesai! Klik dua kali run.bat untuk memulai.
echo ============================================================
pause
