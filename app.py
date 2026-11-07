"""
ClipMaker - server web lokal.
Buka http://127.0.0.1:7860 setelah menjalankan run.bat
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory, abort

import clipper_core as core

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(APP_DIR, "data")
PROJ = os.path.join(DATA, "projects")
OUTPUT = os.path.join(APP_DIR, "output")
SETTINGS_PATH = os.path.join(DATA, "settings.json")
os.makedirs(PROJ, exist_ok=True)
os.makedirs(OUTPUT, exist_ok=True)

DEFAULT_SETTINGS = {
    "api_key": "",
    "ai_model": "claude-sonnet-5-5",
    "whisper_model": "small",
    "language": "id",
    "n_clips": 5,
    "min_len": 20,
    "max_len": 60,
    "auto_render": False,
    "cookies_browser": "",
    "style": {
        "layout": "auto", "captions": True, "caption_color": "kuning", "caption_upper": True,
        "caption_size": 86, "caption_pos": 0.68, "caption_words": 3,
        "title_on": True, "title_secs": 0, "title_bg": "putih", "title_size": 64,
        "progress_bar": True, "handle": "", "loudnorm": True,
    },
}

app = Flask(__name__, static_folder=None)
lock = threading.RLock()
jobs: "queue.Queue[tuple]" = queue.Queue()
projects: dict[str, dict] = {}

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Cancelled(Exception):
    """Proyek dihapus saat sedang diproses."""


def ensure_alive(pid):
    if pid not in projects:
        raise Cancelled()


@app.before_request
def only_local_requests():
    # Tolak nama host asing (DNS rebinding) dan permintaan dari situs lain (CSRF).
    host = urlsplit("//" + (request.host or "")).hostname or ""
    if host.lower() not in LOCAL_HOSTS:
        return jsonify(error="Host tidak diizinkan."), 403
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        if origin is not None and urlsplit(origin).netloc.lower() != request.host.lower():
            return jsonify(error="Permintaan dari situs lain ditolak."), 403


# --------------------------------------------------------------------------
def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            style = {**s["style"], **saved.get("style", {})}
            s.update(saved)
            s["style"] = style
        except Exception:
            pass
    return s


def save_settings(s):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def pdir(pid):
    return os.path.join(PROJ, pid)


def save_project(p):
    with lock:
        if p["id"] not in projects:  # sudah dihapus: jangan tulis ulang project.json
            return
        light = {k: v for k, v in p.items() if k != "segments"}
        with open(os.path.join(pdir(p["id"]), "project.json"), "w", encoding="utf-8") as f:
            json.dump(light, f, ensure_ascii=False, indent=1)


def load_projects():
    for pid in os.listdir(PROJ):
        fp = os.path.join(PROJ, pid, "project.json")
        if not os.path.exists(fp):
            # sisa proyek yang dihapus tapi filenya sempat terkunci
            shutil.rmtree(pdir(pid), ignore_errors=True)
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                p = json.load(f)
            if p.get("status") not in ("siap", "gagal"):
                p["status"], p["stage"] = "gagal", "Terhenti (aplikasi ditutup). Klik Ulangi."
            for c in p.get("clips", []):
                if c.get("render_status") in ("antri", "proses"):
                    c["render_status"] = None
            projects[pid] = p
        except Exception:
            pass


def segments_of(p):
    fp = os.path.join(pdir(p["id"]), "transcript.json")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    return []


def all_words(segs):
    return [w for s in segs for w in s["words"]]


def safe_name(s, n=40):
    s = re.sub(r"[^\w\s-]", "", s, flags=re.U).strip()
    return re.sub(r"\s+", "_", s)[:n] or "clip"


def set_stage(p, stage, prog=None, status=None):
    with lock:
        p["stage"] = stage
        if prog is not None:
            p["progress"] = round(prog, 3)
        if status:
            p["status"] = status


# --------------------------------------------------------------------------
# Pekerja (satu per satu supaya komputer tidak berat)
# --------------------------------------------------------------------------
def do_analyze(pid):
    p = projects[pid]
    s = load_settings()
    d = pdir(pid)

    def stage_cb(label):
        def cb(x):
            ensure_alive(pid)  # hentikan pekerjaan bila proyek dihapus
            set_stage(p, label, x)
        return cb

    try:
        p["error"] = ""
        # 1. sumber
        src = p.get("source")
        if not src or not os.path.exists(os.path.join(d, src)):
            set_stage(p, "Mengunduh video...", 0, "proses")
            info = core.download_video(p["url"], d, progress=stage_cb("Mengunduh video..."),
                                       cookies_browser=s.get("cookies_browser") or None)
            p["source"] = os.path.basename(info["path"])
            p["title"] = info["title"]
            save_project(p)
        src_path = os.path.join(d, p["source"])
        vi = core.probe(src_path)
        p["duration"], p["width"], p["height"] = vi.duration, vi.width, vi.height

        # 2. audio + transkrip
        wav = os.path.join(d, "audio.wav")
        tr = os.path.join(d, "transcript.json")
        if not os.path.exists(tr):
            set_stage(p, "Menyiapkan audio...", 0, "proses")
            core.extract_audio(src_path, wav)
            set_stage(p, f"Membuat transkrip (model {s['whisper_model']})... pertama kali akan mengunduh model AI", 0)
            segs = core.transcribe(wav, s["whisper_model"], s["language"],
                                   progress=stage_cb("Membuat transkrip..."))
            with open(tr, "w", encoding="utf-8") as f:
                json.dump(segs, f, ensure_ascii=False)
        segs = segments_of(p)
        if not os.path.exists(wav):
            core.extract_audio(src_path, wav)

        # 3. momen terbaik
        set_stage(p, "Mencari momen paling menarik...", 0.5, "proses")
        n, mn, mx = int(p.get("n_clips") or s["n_clips"]), int(s["min_len"]), int(s["max_len"])
        clips, used_ai = None, False
        if s.get("api_key"):
            try:
                clips = core.find_highlights_ai(segs, s["api_key"], n, mn, mx, s["ai_model"], p.get("title", ""))
                used_ai = True
            except Exception as e:
                p["warning"] = f"AI gagal, memakai deteksi lokal. ({e})"[:300]
        if not clips:
            clips = core.find_highlights_heuristic(segs, core.audio_energy(wav), n, mn, mx)
        for i, c in enumerate(clips):
            c["id"] = uuid.uuid4().hex[:8]
            c["selected"] = True
            c["render_status"] = None
            c["file"] = None
        p["clips"] = clips
        p["used_ai"] = used_ai
        set_stage(p, f"Selesai: {len(clips)} momen ditemukan", 1, "siap")
        save_project(p)
        if p.get("auto_render"):
            for c in clips:
                queue_render(pid, c["id"])
    except Exception as e:
        if pid not in projects:  # dihapus di tengah jalan, bukan kegagalan
            return
        traceback.print_exc()
        msg = str(e)
        if "Sign in to confirm" in msg or re.search(r"\bbot\b", msg, re.I):
            msg += " | Tips: isi 'Ambil cookies dari browser' di Pengaturan (mis. chrome/edge/firefox)."
        p["error"] = msg[:600]
        set_stage(p, "Gagal", None, "gagal")
        save_project(p)


def do_render(pid, cid):
    p = projects[pid]
    c = next((x for x in p.get("clips", []) if x["id"] == cid), None)
    if not c:
        return
    s = load_settings()
    style = {**s["style"], **(p.get("style") or {})}
    out = None
    try:
        c["render_status"], c["render_progress"], c["error"] = "proses", 0, ""
        segs = segments_of(p)
        words = [w for w in all_words(segs) if w["end"] > c["start"] and w["start"] < c["end"]]
        idx = p["clips"].index(c) + 1
        name = f"{safe_name(p.get('title', 'video'), 30)}_{idx:02d}_{safe_name(c.get('title', ''), 30)}"
        out_dir = os.path.join(OUTPUT, safe_name(p.get("title", pid), 50))
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, name + ".mp4")

        def prog(x):
            ensure_alive(pid)  # hentikan render bila proyek dihapus
            c["render_progress"] = round(x, 3)

        core.render_clip(os.path.join(pdir(pid), p["source"]), c["start"], c["end"], out, words,
                         style, c.get("title", "") if style.get("title_on", True) else "", progress=prog)
        core.write_srt(words, c["start"], c["end"], out.rsplit(".", 1)[0] + ".srt")
        with open(out.rsplit(".", 1)[0] + "_caption.txt", "w", encoding="utf-8") as f:
            f.write((c.get("caption") or c.get("title", "")) + "\n\n" + " ".join(c.get("hashtags", [])))
        c["file"] = os.path.relpath(out, OUTPUT).replace("\\", "/")
        c["render_status"], c["render_progress"] = "selesai", 1
    except Exception as e:
        if out:  # buang file sementara dari render yang tidak selesai
            for leftover in (out + ".tmp.mp4", out + ".log"):
                try:
                    os.remove(leftover)
                except OSError:
                    pass
            try:
                os.rmdir(os.path.dirname(out))  # hanya terhapus bila folder kosong
            except OSError:
                pass
        if pid not in projects:
            return
        traceback.print_exc()
        c["render_status"], c["error"] = "gagal", str(e)[:500]
    save_project(p)


def worker():
    while True:
        kind, pid, cid = jobs.get()
        try:
            if pid not in projects:
                continue
            if kind == "analyze":
                do_analyze(pid)
            elif kind == "render":
                do_render(pid, cid)
        except Exception:
            traceback.print_exc()  # jangan sampai pekerja mati dan antrian macet
        finally:
            if pid not in projects:
                # proyek dihapus saat diproses: sekarang file sudah tidak terkunci
                shutil.rmtree(pdir(pid), ignore_errors=True)
            jobs.task_done()


def queue_render(pid, cid):
    p = projects[pid]
    c = next((x for x in p["clips"] if x["id"] == cid), None)
    if c and c.get("render_status") not in ("antri", "proses"):
        c["render_status"], c["render_progress"] = "antri", 0
        jobs.put(("render", pid, cid))


def new_project(url=None, source=None, title=None, n_clips=None, auto_render=False):
    pid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    os.makedirs(pdir(pid), exist_ok=True)
    p = {"id": pid, "url": url, "source": source, "title": title or url or "Video",
         "status": "antri", "stage": "Menunggu giliran...", "progress": 0, "clips": [],
         "created": time.time(), "n_clips": n_clips, "auto_render": auto_render, "error": ""}
    projects[pid] = p
    save_project(p)
    return p


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(os.path.join(APP_DIR, "web"), "index.html")


@app.get("/api/state")
def state():
    with lock:
        items = sorted(projects.values(), key=lambda p: -p.get("created", 0))
        return jsonify({"projects": items, "queue": jobs.qsize()})


@app.get("/api/settings")
def get_settings():
    s = load_settings()
    s["has_key"] = bool(s.get("api_key"))
    s["api_key"] = ""  # jangan kirim kunci ke halaman
    return jsonify(s)


@app.post("/api/settings")
def post_settings():
    s = load_settings()
    body = request.get_json(force=True)
    key = body.pop("api_key", None)
    if key is not None and key != "":
        s["api_key"] = key.strip()
    if body.pop("clear_key", False):
        s["api_key"] = ""
    style = body.pop("style", None)
    body.pop("has_key", None)
    s.update(body)
    if style:
        s["style"].update(style)
    save_settings(s)
    return jsonify(ok=True)


@app.post("/api/add")
def add_links():
    body = request.get_json(force=True)
    links = [l.strip() for l in re.split(r"[\s,]+", body.get("links", "")) if l.strip().startswith("http")]
    if not links:
        return jsonify(error="Tidak ada link yang valid."), 400
    for url in links:
        p = new_project(url=url, n_clips=body.get("n_clips"), auto_render=body.get("auto_render", False))
        jobs.put(("analyze", p["id"], None))
    return jsonify(ok=True, count=len(links))


@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify(error="Tidak ada file."), 400
    title = os.path.splitext(f.filename)[0]
    p = new_project(title=title, n_clips=request.form.get("n_clips", type=int),
                    auto_render=request.form.get("auto_render") == "true")
    ext = os.path.splitext(f.filename)[1].lower() or ".mp4"
    f.save(os.path.join(pdir(p["id"]), "source" + ext))
    p["source"] = "source" + ext
    save_project(p)
    jobs.put(("analyze", p["id"], None))
    return jsonify(ok=True)


@app.post("/api/project/<pid>/retry")
def retry(pid):
    p = projects.get(pid) or abort(404)
    p["status"], p["stage"], p["error"] = "antri", "Menunggu giliran...", ""
    jobs.put(("analyze", pid, None))
    return jsonify(ok=True)


@app.post("/api/project/<pid>/reanalyze")
def reanalyze(pid):
    """Cari ulang momen (transkrip dipakai ulang, cepat)."""
    p = projects.get(pid) or abort(404)
    body = request.get_json(silent=True) or {}
    if body.get("n_clips"):
        p["n_clips"] = int(body["n_clips"])
    p["status"], p["stage"] = "antri", "Menunggu giliran..."
    jobs.put(("analyze", pid, None))
    return jsonify(ok=True)


@app.delete("/api/project/<pid>")
def delete_project(pid):
    with lock:
        p = projects.pop(pid, None)
        if p:
            # file yang masih dipakai render akan dibersihkan pekerja setelah ia berhenti
            shutil.rmtree(pdir(pid), ignore_errors=True)
    return jsonify(ok=True)


@app.get("/api/project/<pid>/transcript")
def transcript(pid):
    p = projects.get(pid) or abort(404)
    segs = segments_of(p)
    return jsonify([{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segs])


@app.post("/api/project/<pid>/clip")
def upsert_clip(pid):
    p = projects.get(pid) or abort(404)
    body = request.get_json(force=True)
    with lock:
        c = next((x for x in p["clips"] if x["id"] == body.get("id")), None)
        is_new = c is None
        if is_new:
            c = {"id": uuid.uuid4().hex[:8], "selected": True, "render_status": None, "file": None,
                 "score": 0, "reason": "dibuat manual", "hashtags": [], "caption": ""}
        patch = {k: body[k] for k in ("start", "end", "title", "caption", "selected", "hashtags") if k in body}
        try:
            start = max(0.0, float(patch.get("start", c.get("start", 0))))
            end = float(patch.get("end", c.get("end", 0)))
        except (TypeError, ValueError):
            return jsonify(error="Format waktu tidak valid."), 400
        # periksa dulu sebelum mengubah apa pun, supaya nilai salah tidak tersimpan
        if end <= start:
            return jsonify(error="Waktu selesai harus setelah waktu mulai."), 400
        c.update(patch)
        c["start"], c["end"] = start, end
        if is_new:
            p["clips"].append(c)
        segs = segments_of(p)
        c["text"] = " ".join(s["text"] for s in segs if s["end"] > c["start"] and s["start"] < c["end"])
        p["clips"].sort(key=lambda x: x["start"])
    save_project(p)
    return jsonify(ok=True, clip=c)


@app.delete("/api/project/<pid>/clip/<cid>")
def delete_clip(pid, cid):
    p = projects.get(pid) or abort(404)
    p["clips"] = [c for c in p["clips"] if c["id"] != cid]
    save_project(p)
    return jsonify(ok=True)


@app.post("/api/project/<pid>/render")
def render(pid):
    p = projects.get(pid) or abort(404)
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or [c["id"] for c in p["clips"] if c.get("selected")]
    if body.get("style"):
        p["style"] = body["style"]
    for cid in ids:
        queue_render(pid, cid)
    save_project(p)
    return jsonify(ok=True, count=len(ids))


@app.post("/api/render-all")
def render_all():
    n = 0
    for pid, p in projects.items():
        for c in p.get("clips", []):
            if c.get("selected") and c.get("render_status") != "selesai":
                queue_render(pid, c["id"])
                n += 1
    return jsonify(ok=True, count=n)


@app.get("/media/<pid>/<path:name>")
def media(pid, name):
    if pid not in projects:  # cegah pid seperti ".." membuka folder data/
        abort(404)
    return send_from_directory(pdir(pid), name, conditional=True)


@app.get("/out/<path:name>")
def out_file(name):
    return send_from_directory(OUTPUT, name, conditional=True,
                               as_attachment=request.args.get("dl") == "1")


@app.post("/api/open-folder")
def open_folder():
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
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(ok=True)


if __name__ == "__main__":
    load_projects()
    threading.Thread(target=worker, daemon=True).start()
    port = int(os.environ.get("PORT", 7860))
    url = f"http://127.0.0.1:{port}"
    print("=" * 56)
    print("  ClipMaker berjalan di", url)
    print("  Biarkan jendela ini terbuka selama memakai aplikasi.")
    print("=" * 56)
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
