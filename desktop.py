"""
Nero - membuka Nero tanpa terminal (Windows).

  - Ikon "Nero" di Desktop & Start Menu: klik dua kali untuk membuka Nero tanpa jendela hitam.
    Bila Nero sudah berjalan, ikon cukup membuka halamannya di browser.
  - Buka otomatis saat Windows menyala (opsional, diatur di Pengaturan): Nero berjalan di latar
    belakang tanpa membuka browser.

Ikon menjalankan app.py memakai pythonw.exe (tanpa jendela). Pesan yang biasanya tampil di jendela
run.bat ditulis ke data/nero.log.

Dari baris perintah (dipakai install.bat):  python desktop.py   -> buat ikon di Desktop & Start Menu
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import traceback
import urllib.request

from common import APP_DIR, APP_NAME, DATA

SUPPORTED = os.name == "nt"
WINDOWLESS = sys.stdout is None  # dibuka lewat ikon (pythonw.exe): tidak ada jendela hitam
BACKGROUND_ARG = "--background"  # dipakai ikon buka otomatis: jangan buka browser

LNK_NAME = f"{APP_NAME}.lnk"
APP_PY = os.path.join(APP_DIR, "app.py")
ICON_PATH = os.path.join(DATA, "nero.ico")
LOG_PATH = os.path.join(DATA, "nero.log")
STATE_PATH = os.path.join(DATA, "desktop.json")  # lokasi folder aplikasi saat ikon terakhir dibuat

# CSIDL: folder Windows milik pengguna (ikut benar bila Desktop dipindah ke OneDrive)
_DESKTOP, _PROGRAMS, _STARTUP = 0x10, 0x02, 0x07
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


# --------------------------------------------------------------------------
# Satu Nero saja
# --------------------------------------------------------------------------
def nero_running(url: str) -> bool:
    """True bila Nero sudah berjalan di alamat ini (mis. dibuka lewat ikon lalu run.bat)."""
    try:
        with urllib.request.urlopen(url + "/api/ping", timeout=3) as r:
            return json.load(r).get("app") == APP_NAME
    except Exception:
        return False


# --------------------------------------------------------------------------
# Tanpa jendela hitam
# --------------------------------------------------------------------------
def log_to_file() -> None:
    """Pesan & galat ke data/nero.log (log sebelumnya disimpan sebagai nero-sebelumnya.log).
    Galat yang membuat Nero gagal dibuka juga muncul sebagai kotak pesan."""
    import logging

    try:
        os.replace(LOG_PATH, os.path.join(DATA, "nero-sebelumnya.log"))
    except OSError:
        pass
    f = open(LOG_PATH, "w", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = sys.stderr = f
    # tampilan menanyakan status setiap beberapa detik: jangan catat setiap permintaan
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    def on_crash(kind, err, tb):
        traceback.print_exception(kind, err, tb)
        if not issubclass(kind, KeyboardInterrupt):
            message_box(f"{APP_NAME} gagal dibuka:\n{err}\n\nRincian: {LOG_PATH}")

    sys.excepthook = on_crash


def message_box(text: str) -> None:
    if SUPPORTED:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)  # MB_ICONERROR


# --------------------------------------------------------------------------
# Ikon di Desktop, Start Menu, dan Startup (buka otomatis)
# --------------------------------------------------------------------------
def _folder(csidl: int) -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) != 0:
        raise OSError("Folder Windows tidak ditemukan.")
    return buf.value


def _lnk(csidl: int) -> str:
    return os.path.join(_folder(csidl), LNK_NAME)


def status() -> dict | None:
    """Untuk Pengaturan: apakah ikon & buka otomatis sudah ada. None bila bukan Windows."""
    if not SUPPORTED:
        return None
    try:
        return {"shortcut": os.path.isfile(_lnk(_DESKTOP)), "autostart": os.path.isfile(_lnk(_STARTUP))}
    except OSError:
        return None


def create_shortcuts() -> None:
    """Ikon Nero di Desktop & Start Menu."""
    for csidl in (_DESKTOP, _PROGRAMS):
        _write_lnk(_lnk(csidl), f'"{APP_PY}"', "Buka Nero")
    _remember_location()


def set_autostart(on: bool) -> None:
    """Buka Nero otomatis (di latar belakang) setiap kali Windows menyala."""
    path = _lnk(_STARTUP)
    if on:
        _write_lnk(path, f'"{APP_PY}" {BACKGROUND_ARG}', "Nero berjalan di latar belakang")
        _remember_location()
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def refresh_if_moved() -> None:
    """Folder aplikasi dipindah / di-rename: ikon yang sudah ada diarahkan ke lokasi baru.
    Dijalankan setiap kali Nero dibuka (mis. lewat run.bat setelah folder dipindah)."""
    if not SUPPORTED:
        return
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            old = json.load(f).get("app_dir")
    except (OSError, ValueError):
        return  # ikon belum pernah dibuat
    if not old or os.path.normcase(old) == os.path.normcase(APP_DIR):
        return
    try:
        if os.path.isfile(_lnk(_DESKTOP)) or os.path.isfile(_lnk(_PROGRAMS)):
            create_shortcuts()
        if os.path.isfile(_lnk(_STARTUP)):
            set_autostart(True)
        _remember_location()
        print("  Ikon Nero diperbarui ke lokasi folder yang baru.")
    except Exception as e:
        print("  Ikon Nero belum bisa diperbarui:", e)


def refresh_if_moved_later() -> None:
    threading.Thread(target=refresh_if_moved, daemon=True).start()


def _remember_location() -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump({"app_dir": APP_DIR}, f)


# Dibuat lewat PowerShell (selalu ada di Windows 10/11). Nilai dikirim lewat variabel lingkungan
# supaya nama folder berisi spasi, tanda kutip, atau huruf non-Latin tetap aman.
_PS_SHORTCUT = (
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:NERO_LNK);"
    "$s.TargetPath = $env:NERO_TARGET; $s.Arguments = $env:NERO_ARGS;"
    "$s.WorkingDirectory = $env:NERO_DIR; $s.IconLocation = $env:NERO_ICON;"
    "$s.Description = $env:NERO_DESC; $s.Save()"
)


def _pythonw() -> str:
    """pythonw.exe milik lingkungan Python Nero (.venv), di sebelah python.exe yang sedang dipakai."""
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(exe):
        raise RuntimeError("pythonw.exe tidak ditemukan. Jalankan install.bat lagi.")
    return exe


def _write_lnk(path: str, args: str, desc: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    env = {**os.environ, "NERO_LNK": path, "NERO_TARGET": _pythonw(), "NERO_ARGS": args,
           "NERO_DIR": APP_DIR, "NERO_ICON": ensure_icon() + ",0", "NERO_DESC": desc}
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      r"System32\WindowsPowerShell\v1.0\powershell.exe")
    r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", _PS_SHORTCUT],
                       env=env, capture_output=True, text=True, errors="replace",
                       timeout=60, creationflags=_NO_WINDOW)
    if r.returncode != 0 or not os.path.isfile(path):
        raise RuntimeError("Ikon gagal dibuat: " + (r.stderr or r.stdout or "").strip()[-300:])


def ensure_icon() -> str:
    """data/nero.ico: logo Nero (sama dengan ikon tab browser), dibuat sekali."""
    if os.path.isfile(ICON_PATH):
        return ICON_PATH
    from PIL import Image, ImageDraw

    big = 1024
    k = big / 32  # logo digambar di kotak 32x32 (lihat frontend/src/app/icon.svg)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # kotak gelap + garis tepi terang 35% (sudah dicampur dengan warna kotak)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=8 * k, fill=(10, 10, 10, 255),
                        outline=(92, 92, 92, 255), width=round(1.5 * k))
    n = [(9, 23), (9, 9), (11.7, 9), (20.3, 18.9), (20.3, 9), (23, 9),
         (23, 23), (20.3, 23), (11.7, 13.1), (11.7, 23)]
    d.polygon([(x * k, y * k) for x, y in n], fill=(245, 245, 245, 255))
    img = img.resize((256, 256), Image.Resampling.LANCZOS)
    img.save(ICON_PATH, format="ICO",
             sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ICON_PATH


if __name__ == "__main__":
    if not SUPPORTED:
        sys.exit("Ikon Nero hanya untuk Windows. Jalankan: python app.py")
    try:
        create_shortcuts()
    except Exception as e:
        print("Ikon Nero belum bisa dibuat:", e)
        print("Nero tetap bisa dibuka lewat run.bat.")
        sys.exit(1)
    print("Ikon Nero dibuat di Desktop & Start Menu.")
