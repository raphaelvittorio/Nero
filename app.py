"""
Nero - server web lokal.

Satu aplikasi berisi banyak fitur untuk membantu menghasilkan uang dari internet. Setiap fitur ada
di folder features/ (lihat features/__init__.py); berkas ini hanya mengurus hal yang dipakai bersama:
keamanan, tampilan, pengaturan umum, dan folder hasil.

Buka lewat ikon Nero di Desktop (tanpa jendela hitam, lihat desktop.py) atau run.bat (dengan jendela
berisi pesan), lalu http://127.0.0.1:7860 terbuka di browser.
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from urllib.parse import urlsplit

import common
import desktop
from common import OUTPUT, WEB

PORT = int(os.environ.get("PORT", 7860))
URL = f"http://127.0.0.1:{PORT}"
BACKGROUND = desktop.BACKGROUND_ARG in sys.argv[1:]  # dibuka otomatis saat Windows menyala

if __name__ == "__main__":
    # Dicek sebelum memuat fitur (lama): bila Nero sudah berjalan, cukup buka halamannya.
    if desktop.nero_running(URL):
        print(f"{common.APP_NAME} sudah berjalan di {URL}")
        if not BACKGROUND:
            webbrowser.open(URL)
        sys.exit(0)
    if desktop.WINDOWLESS:
        desktop.log_to_file()  # sebelum memuat fitur, supaya galat saat memuat pun tercatat

from flask import Flask, abort, jsonify, request, send_from_directory  # noqa: E402

from features import FEATURES  # noqa: E402

app = Flask(__name__, static_folder=None)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
# Hanya untuk pengembangan tampilan (`npm run dev` di frontend/): izinkan origin server dev Next.js,
# mis. NERO_DEV_ORIGINS=localhost:3000. Kosong saat aplikasi dipakai biasa.
DEV_ORIGINS = {o.strip().lower() for o in os.environ.get("NERO_DEV_ORIGINS", "").split(",") if o.strip()}

for feature in FEATURES:
    common.register_settings(feature.ID, feature.SETTINGS)
    app.register_blueprint(feature.bp, url_prefix=f"/api/{feature.ID}")


@app.before_request
def only_local_requests():
    # Tolak nama host asing (DNS rebinding) dan permintaan dari situs lain (CSRF).
    host = urlsplit("//" + (request.host or "")).hostname or ""
    if host.lower() not in LOCAL_HOSTS:
        return jsonify(error="Host tidak diizinkan."), 403
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        if origin is not None and urlsplit(origin).netloc.lower() not in {request.host.lower(), *DEV_ORIGINS}:
            return jsonify(error="Permintaan dari situs lain ditolak."), 403


# --------------------------------------------------------------------------
# API umum
# --------------------------------------------------------------------------
@app.get("/api/settings")
def get_settings():
    """Pengaturan umum yang dipakai semua fitur. API key tidak pernah dikirim ke halaman."""
    s = common.load_settings()
    return jsonify(has_key=bool(s["api_key"]), ai_model=s["ai_model"], cookies_browser=s["cookies_browser"],
                   desktop=desktop.status())


@app.post("/api/settings")
def post_settings():
    body = request.get_json(force=True) or {}
    patch = {}
    key = body.get("api_key")
    if isinstance(key, str) and key.strip():  # kosong = tetap memakai kunci lama
        patch["api_key"] = key.strip()
    if body.get("clear_key"):
        patch["api_key"] = ""
    for k in ("ai_model", "cookies_browser"):
        if k in body:
            patch[k] = str(body[k] or "").strip()
    if patch.get("ai_model") == "":
        patch.pop("ai_model")
    common.update_settings(patch)
    if "autostart" in body and desktop.SUPPORTED:
        try:
            desktop.set_autostart(bool(body["autostart"]))
        except Exception as e:
            return jsonify(error=f"Pengaturan disimpan, tetapi buka otomatis belum bisa diatur: {e}"), 500
    return jsonify(ok=True)


@app.post("/api/shortcut")
def make_shortcut():
    """Ikon Nero di Desktop & Start Menu."""
    if not desktop.SUPPORTED:
        return jsonify(error="Ikon hanya tersedia di Windows."), 400
    try:
        desktop.create_shortcuts()
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(ok=True)


@app.get("/api/ping")
def ping():
    """Dipakai ikon Nero untuk mengetahui apakah Nero sudah berjalan."""
    return jsonify(app=common.APP_NAME)


@app.post("/api/shutdown")
def shutdown():
    """Tombol "Matikan Nero". Tugas yang sedang berjalan ikut berhenti."""
    threading.Timer(0.5, lambda: os._exit(0)).start()  # beri waktu jawaban ini sampai ke browser
    return jsonify(ok=True)


@app.get("/api/overview")
def overview():
    """Ringkasan setiap fitur untuk Beranda."""
    return jsonify(features={f.ID: f.summary() for f in FEATURES})


@app.get("/out/<path:name>")
def out_file(name):
    return send_from_directory(OUTPUT, name, conditional=True,
                               as_attachment=request.args.get("dl") == "1")


@app.post("/api/open-folder")
def open_folder():
    """Buka folder hasil (atau folder berisi berkas hasil) di File Explorer."""
    sub = (request.get_json(silent=True) or {}).get("path", "")
    path = os.path.normpath(os.path.join(OUTPUT, sub))
    try:
        inside = os.path.commonpath([path, OUTPUT]) == OUTPUT
    except ValueError:  # beda drive di Windows
        inside = False
    if not inside:
        abort(400)
    if os.path.isfile(path):
        path = os.path.dirname(path)
    os.makedirs(path, exist_ok=True)
    try:
        common.open_in_explorer(path)
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(ok=True)


# --------------------------------------------------------------------------
# Tampilan (hasil `npm run build` di folder frontend/, disalin ke web/)
# --------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(WEB, "index.html", max_age=0)


@app.get("/<path:name>")
def web_file(name):
    if not os.path.isfile(os.path.join(WEB, name)):
        name = web_alias(name)
    # nama berkas di _next/static selalu berubah setiap build, jadi aman disimpan lama di cache
    return send_from_directory(WEB, name, max_age=31536000 if name.startswith("_next/static/") else 0)


def web_alias(name):
    """Nama berkas sebenarnya di web/ untuk alamat yang tidak ada persis di sana."""
    page = name.rstrip("/") + ".html"
    if os.path.isfile(os.path.join(WEB, page)):
        return page  # halaman fitur, mis. /clip -> clip.html
    head, _, tail = name.rpartition("/")
    if tail.startswith("__next.") and tail.endswith(".txt"):
        # data navigasi Next.js: /clip/__next.clip.__PAGE__.txt disimpan sebagai clip/__next.clip/__PAGE__.txt
        nested = "__next." + tail[len("__next."):-len(".txt")].replace(".", "/") + ".txt"
        return f"{head}/{nested}" if head else nested
    return name


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith(("/api/", "/out/")) or not os.path.isfile(os.path.join(WEB, "404.html")):
        return e
    return send_from_directory(WEB, "404.html", max_age=0), 404


if __name__ == "__main__":
    for feature in FEATURES:
        feature.start()
    desktop.refresh_if_moved_later()
    print("=" * 56)
    print(f"  {common.APP_NAME} berjalan di", URL)
    print("  Fitur:", ", ".join(f.NAME for f in FEATURES))
    if not desktop.WINDOWLESS:
        print("  Biarkan jendela ini terbuka selama memakai aplikasi.")
    print("=" * 56)
    if os.environ.get("NO_BROWSER") != "1" and not BACKGROUND:
        threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False)
