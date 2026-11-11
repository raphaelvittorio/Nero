"""
Nero - bagian bersama semua fitur: lokasi folder, pengaturan, dan bantuan berkas.

Setiap fitur menyimpan datanya di data/<id fitur>/ dan hasilnya di output/<id fitur>/.
Pengaturan ada di satu berkas data/settings.json:
  - kunci umum (API key Claude, model AI, cookies browser) dipakai bersama semua fitur
  - pengaturan khusus fitur ada di bagiannya sendiri, mis. {"clip": {...}}
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time

APP_NAME = "Nero"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
# NERO_DATA / NERO_OUTPUT hanya untuk pengembangan & uji coba: menjalankan Nero kedua dengan data terpisah
DATA = os.path.abspath(os.environ.get("NERO_DATA") or os.path.join(APP_DIR, "data"))
OUTPUT = os.path.abspath(os.environ.get("NERO_OUTPUT") or os.path.join(APP_DIR, "output"))
WEB = os.path.join(APP_DIR, "web")  # tampilan siap pakai (hasil build frontend/)
SETTINGS_PATH = os.path.join(DATA, "settings.json")
os.makedirs(DATA, exist_ok=True)
os.makedirs(OUTPUT, exist_ok=True)


def data_dir(fid: str) -> str:
    """Folder data milik satu fitur (proyek, cache, berkas sementara)."""
    path = os.path.join(DATA, fid)
    os.makedirs(path, exist_ok=True)
    return path


def output_dir(fid: str) -> str:
    """Folder hasil milik satu fitur (yang dibuka tombol "Folder hasil")."""
    path = os.path.join(OUTPUT, fid)
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------
# Pengaturan
# --------------------------------------------------------------------------
GLOBAL_DEFAULTS = {
    "api_key": "",
    "ai_model": "claude-sonnet-5-5",
    "cookies_browser": "",
    # AI lokal gratis (Ollama / LM Studio), lihat local_ai.py. Model kosong = pilih otomatis.
    "local_ai_url": "http://127.0.0.1:11434",
    "local_ai_model": "",
    "local_ai_on": True,
    # kunci untuk server bergaya OpenAI di internet (mis. OpenRouter, Groq); kosong untuk Ollama/LM Studio
    "local_ai_key": "",
    # AI untuk meniru gaya: "lokal" (Ollama, offline) atau "gemini" (Google, gratis online, lihat gemini_ai.py)
    "ai_provider": "lokal",
    "gemini_key": "",
    "gemini_model": "gemini-3.8-flash",
}
SECRET_KEYS = ("api_key", "gemini_key", "local_ai_key")   # tidak pernah dikirim ke halaman
_feature_defaults: dict[str, dict] = {}
_settings_lock = threading.RLock()


def register_settings(fid: str, defaults: dict) -> None:
    """Dipanggil app.py untuk setiap fitur: nilai bawaan bagian pengaturan fitur itu."""
    _feature_defaults[fid] = defaults


def registered_features() -> list[str]:
    return list(_feature_defaults)


def _copy(x):
    return json.loads(json.dumps(x))


def _merge(defaults: dict, saved: dict) -> dict:
    """Nilai tersimpan menimpa nilai bawaan; kamus di dalamnya (mis. style) digabung satu tingkat."""
    out = _copy(defaults)
    for k, v in saved.items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def read_settings_file() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            return saved if isinstance(saved, dict) else {}
        except Exception:
            pass
    return {}


def write_settings_file(s: dict) -> None:
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS_PATH)  # tidak pernah meninggalkan berkas setengah jadi


def load_settings() -> dict:
    """Semua pengaturan: kunci umum + satu bagian per fitur, sudah dilengkapi nilai bawaan."""
    with _settings_lock:
        saved = read_settings_file()
    s = {**saved}  # bagian fitur yang tidak dikenal (mis. fitur yang dimatikan) tetap disimpan
    for k, v in GLOBAL_DEFAULTS.items():
        s.setdefault(k, v)
    for fid, defaults in _feature_defaults.items():
        sec = saved.get(fid)
        s[fid] = _merge(defaults, sec if isinstance(sec, dict) else {})
    return s


def feature_settings(fid: str) -> dict:
    """Pengaturan untuk dipakai satu fitur: kunci umum + bagian fitur itu dalam satu kamus datar."""
    s = load_settings()
    return {**{k: s[k] for k in GLOBAL_DEFAULTS}, **s[fid]}


def update_settings(patch: dict, fid: str | None = None) -> None:
    """Simpan perubahan. Hanya kunci yang dikenal yang diterima; kamus (mis. style) digabung."""
    with _settings_lock:
        s = load_settings()
        allowed = GLOBAL_DEFAULTS if fid is None else _feature_defaults[fid]
        target = s if fid is None else s[fid]
        for k, v in patch.items():
            if k not in allowed:
                continue
            if isinstance(target.get(k), dict) and isinstance(v, dict):
                target[k].update(v)
            else:
                target[k] = v
        write_settings_file(s)


# --------------------------------------------------------------------------
# Berkas
# --------------------------------------------------------------------------
def safe_name(s, n=40):
    s = re.sub(r"[^\w\s-]", "", s, flags=re.U).strip()
    return re.sub(r"\s+", "_", s)[:n] or "clip"


def remove_files(*paths):
    """Hapus file; kembalikan daftar yang gagal (biasanya karena masih dibuka di Windows)."""
    failed = []
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            failed.append(path)
    return failed


def remove_later(paths, tries=30, delay=2.0):
    """Coba hapus lagi di latar belakang (mis. video masih diputar di browser)."""
    def run():
        left = list(paths)
        for _ in range(tries):
            nxt = []
            for path in left:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                    if os.path.exists(path):
                        nxt.append(path)
                else:
                    nxt += remove_files(path)
            left = nxt
            if not left:
                return
            time.sleep(delay)
    if paths:
        threading.Thread(target=run, daemon=True).start()


def dir_size_mb(path):
    total = 0
    try:
        for e in os.scandir(path):
            if e.is_file(follow_symlinks=False):
                total += e.stat().st_size
    except OSError:
        pass
    return round(total / 1e6, 1)


def move_children(src, dst, skip=()):
    """Pindahkan isi folder src ke dst satu per satu. Kembalikan nama yang gagal dipindah
    (mis. berkasnya sedang dibuka program lain); bisa dicoba lagi lain kali."""
    failed = []
    if not os.path.isdir(src):
        return failed
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in skip:
            continue
        target = os.path.join(dst, name)
        if os.path.exists(target):
            failed.append(name)
            continue
        try:
            os.replace(os.path.join(src, name), target)
        except OSError:
            failed.append(name)
    return failed


def open_in_explorer(path):
    """Buka folder di File Explorer (atau Finder / pengelola berkas)."""
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')
