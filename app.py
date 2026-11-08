"""
ClipMaker - server web lokal.
Buka http://127.0.0.1:7860 setelah menjalankan run.bat
"""
from __future__ import annotations

import hashlib
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

from flask import Flask, Response, jsonify, request, send_from_directory, abort

import clipper_core as core

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(APP_DIR, "data")
PROJ = os.path.join(DATA, "projects")
OUTPUT = os.path.join(APP_DIR, "output")
WEB = os.path.join(APP_DIR, "web")  # tampilan siap pakai (hasil build frontend/)
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
        "caption_font": "impact", "caption_base": "putih", "caption_emphasis": False, "cut_pauses": 0,
    },
}
LANGUAGES = {"id", "en", "auto", "ms", "jv"}

app = Flask(__name__, static_folder=None)
lock = threading.RLock()
# Dua antrian terpisah: video panjang yang sedang ditranskrip tidak menahan render clip lain.
analyze_q: "queue.Queue[tuple]" = queue.Queue()
render_q: "queue.Queue[tuple]" = queue.Queue()
projects: dict[str, dict] = {}

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
# Hanya untuk pengembangan tampilan (`npm run dev` di frontend/): izinkan origin server dev Next.js,
# mis. CLIPMAKER_DEV_ORIGINS=localhost:3000. Kosong saat aplikasi dipakai biasa.
DEV_ORIGINS = {o.strip().lower() for o in os.environ.get("CLIPMAKER_DEV_ORIGINS", "").split(",") if o.strip()}


class Cancelled(Exception):
    """Tugas dibatalkan pengguna atau proyeknya dihapus."""


def check_job(pid, obj, token):
    """Setiap tugas membawa token; bila token di proyek/clip berganti, tugas lama berhenti."""
    if pid not in projects or obj.get("job") != token:
        raise Cancelled()


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
        light = {k: v for k, v in p.items() if k not in ("segments", "job")}
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
                if p.get("clips"):  # pencarian ulang terhenti: daftar clip lama masih utuh
                    p["status"], p["stage"] = "siap", "Pencarian ulang terhenti (aplikasi ditutup)."
                else:
                    p["status"], p["stage"] = "gagal", "Terhenti (aplikasi ditutup). Klik Ulangi."
            for c in p.get("clips", []):
                c.pop("job", None)
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


def busy(p):
    return p.get("status") in ("antri", "proses") or any(
        c.get("render_status") in ("antri", "proses") for c in p.get("clips", []))


# --------------------------------------------------------------------------
# Pekerja: satu untuk analisis, satu untuk render
# --------------------------------------------------------------------------
def do_analyze(pid, token):
    p = projects[pid]
    if p.get("job") != token:
        return
    s = load_settings()
    d = pdir(pid)
    lang = p.get("language") or s["language"]
    wav = os.path.join(d, "audio.wav")
    tr = os.path.join(d, "transcript.json")

    def alive():
        check_job(pid, p, token)

    def stage_cb(label):
        def cb(x):
            alive()
            set_stage(p, label, x)
        return cb

    try:
        p["error"], p["warning"] = "", ""
        # 1. sumber
        src = p.get("source")
        if not src or not os.path.exists(os.path.join(d, src)):
            if not p.get("url"):
                raise RuntimeError("Video sumber sudah dihapus dan tidak ada link untuk mengunduh ulang.")
            set_stage(p, "Mengunduh video...", 0, "proses")
            info = core.download_video(p["url"], d, progress=stage_cb("Mengunduh video..."),
                                       cookies_browser=s.get("cookies_browser") or None)
            alive()
            p["source"] = os.path.basename(info["path"])
            p["title"] = info["title"]
            p.pop("source_removed", None)
            save_project(p)
        src_path = os.path.join(d, p["source"])
        vi = core.probe(src_path)
        p["duration"], p["width"], p["height"] = vi.duration, vi.width, vi.height

        # 2. audio + transkrip
        if not os.path.exists(tr):
            alive()
            set_stage(p, "Menyiapkan audio...", 0, "proses")
            core.extract_audio(src_path, wav)
            alive()
            dev = "GPU" if core.transcribe_device() == "cuda" else "CPU"
            set_stage(p, f"Membuat transkrip ({dev}, model {s['whisper_model']})...", 0)
            segs = core.transcribe(wav, s["whisper_model"], lang,
                                   progress=stage_cb(f"Membuat transkrip ({dev})..."))
            alive()
            with open(tr, "w", encoding="utf-8") as f:
                json.dump(segs, f, ensure_ascii=False)
        segs = segments_of(p)

        # 3. momen terbaik (timeline/link/instruksi dari kolom referensi lebih dulu)
        alive()
        set_stage(p, "Mencari momen paling menarik...", 0.5, "proses")
        clips, used_ai, warns = pick_clips(p, segs, s, lang, src_path, wav, alive)
        if warns:
            p["warning"] = " · ".join(warns)[:900]
        alive()
        for c in clips:
            c["id"] = uuid.uuid4().hex[:8]
            c["selected"] = True
            c["render_status"] = None
            c["file"] = None
        with lock:
            alive()
            p["clips"] = clips
            p["used_ai"] = used_ai
            set_stage(p, f"Selesai: {len(clips)} momen ditemukan", 1, "siap")
        save_project(p)
        if p.get("auto_render"):
            for c in clips:
                queue_render(pid, c["id"])
    except Cancelled:
        return
    except Exception as e:
        if pid not in projects or p.get("job") != token:  # dihapus/dibatalkan, bukan kegagalan
            return
        traceback.print_exc()
        msg = str(e)
        if "Sign in to confirm" in msg or re.search(r"\bbot\b", msg, re.I):
            msg += " | Tips: isi 'Ambil cookies dari browser' di Pengaturan (mis. chrome/edge/firefox)."
        p["error"] = msg[:600]
        set_stage(p, "Gagal", None, "gagal")
        save_project(p)
    finally:
        # hemat disk: audio.wav (~2 MB per menit) selalu bisa dibuat ulang dari video
        remove_files(wav)


MAX_REFS = 5  # link clip referensi per proyek


def youtube_id(url):
    m = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/|/live/|/embed/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def url_time(url):
    """Detik dari ?t= / &start= di link YouTube (t=754, t=754s, t=12m34s, t=1h2m3s)."""
    m = re.search(r"[?&#](?:t|start)=([\dhms.]+)", url or "")
    if not m:
        return None
    v = m.group(1)
    if re.fullmatch(r"\d+(?:\.\d+)?s?", v):
        return float(v.rstrip("s"))
    parts = {u: re.search(rf"(\d+){u}", v) for u in "hms"}
    secs = sum(int(x.group(1)) * k for u, k in (("h", 3600), ("m", 60), ("s", 1)) if (x := parts[u]))
    return float(secs) if any(parts.values()) else None


def load_references(p, links, s, lang, alive):
    """Unduh audio clip referensi lalu buat transkripnya. Hasil disimpan di folder refs/ proyek,
    jadi 'Cari ulang momen' tidak perlu mengunduh lagi."""
    d = os.path.join(pdir(p["id"]), "refs")
    os.makedirs(d, exist_ok=True)
    refs, warns = [], []
    for i, url in enumerate(links, 1):
        cache = os.path.join(d, hashlib.sha1(url.encode("utf-8")).hexdigest()[:12] + ".json")
        if os.path.exists(cache):
            try:
                with open(cache, encoding="utf-8") as f:
                    refs.append(json.load(f))
                continue
            except Exception:
                pass
        tmp = os.path.join(d, "tmp")
        label = f"clip referensi {i}/{len(links)}"
        try:
            alive()
            set_stage(p, f"Mengunduh {label}...", 0)
            info = core.download_reference(url, tmp, s.get("cookies_browser") or None)
            alive()
            wav = os.path.join(tmp, "ref.wav")
            core.extract_audio(info["path"], wav)

            def cb(x):
                alive()
                set_stage(p, f"Membuat transkrip {label}...", x)

            segs = core.transcribe(wav, s["whisper_model"], lang, progress=cb)
            ref = {"url": url, "title": info["title"], "segments": segs}
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(ref, f, ensure_ascii=False)
            refs.append(ref)
        except Cancelled:
            raise
        except Exception as e:
            msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
            warns.append(f"Clip referensi {i} gagal diproses ({msg[:140]})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return refs, warns


def pick_clips(p, segs, s, lang, src_path, wav, alive):
    """Pilih momen. Isi kolom 'Referensi & instruksi' didahulukan:
    timeline & link referensi yang cocok -> pasti jadi clip; titik waktu -> momen di sekitarnya;
    instruksi/contoh -> mengarahkan AI (atau kata kunci di mode lokal). Sisa jumlah clip diisi otomatis.
    Hasil: (clips, used_ai, peringatan)."""
    warns = []
    brief = core.parse_brief(p.get("brief") or "")
    dur = p.get("duration") or (segs[-1]["end"] if segs else 0)
    n, mn, mx = int(p.get("n_clips") or s["n_clips"]), int(s["min_len"]), int(s["max_len"])
    fixed, points, examples = [], [], []

    for r in brief["ranges"]:
        a, b = r["start"], min(r["end"], dur)
        if a >= dur or b - a < 1:
            why = "melewati durasi video" if a >= dur else "waktu selesai harus setelah waktu mulai"
            warns.append(f"Timeline {core._fmt(r['start'])} - {core._fmt(r['end'])} dilewati: {why}")
            continue
        a, b = core.snap_range(segs, a, b)
        fixed.append({"start": a, "end": b, "note": r["note"], "ref": "timeline"})
    for pt in brief["points"]:
        if pt["t"] < dur:
            points.append(pt)
        else:
            warns.append(f"Titik {core._fmt(pt['t'])} dilewati: melewati durasi video")

    main_id, others = youtube_id(p.get("url")), []
    for url in brief["links"]:
        if main_id and youtube_id(url) == main_id:  # link video ini sendiri, mis. disalin dengan ?t=
            t = url_time(url)
            if t is not None and t < dur:
                points.append({"t": t, "note": ""})
            continue
        if url != p.get("url"):
            others.append(url)
    if len(others) > MAX_REFS:
        warns.append(f"Hanya {MAX_REFS} link referensi pertama yang dipakai.")
        others = others[:MAX_REFS]
    if others:
        refs, w = load_references(p, others, s, lang, alive)
        warns += w
        for ref in refs:
            m = core.match_reference(segs, ref["segments"])
            if m:
                a, b = core.snap_range(segs, m["start"], m["end"], tol=1.5)
                fixed.append({"start": a, "end": b, "note": "", "ref": "link", "ratio": m["ratio"]})
                continue
            text = " ".join(x["text"] for x in ref["segments"]).strip()
            if text:
                examples.append(text[:1500])
            warns.append(f'Clip referensi "{str(ref.get("title", ""))[:60]}" tidak ditemukan di video ini; '
                         "dipakai sebagai contoh gaya/topik.")

    # timeline & link yang menunjuk momen yang sama cukup dibuat sekali
    uniq = []
    for f in fixed:
        if not any(min(f["end"], u["end"]) - max(f["start"], u["start"])
                   > 0.5 * min(f["end"] - f["start"], u["end"] - u["start"]) for u in uniq):
            uniq.append(f)
    fixed = uniq

    energy_cache = []

    def energy():
        if not energy_cache:
            if not os.path.exists(wav):
                core.extract_audio(src_path, wav)
            energy_cache.append(core.audio_energy(wav))
        return energy_cache[0]

    clips, used_ai = None, False
    if s.get("api_key"):
        set_stage(p, "Claude sedang memilih momen terbaik...", 0.5)
        try:
            clips, note = core.find_highlights_ai(
                segs, s["api_key"], max(n - len(fixed), len(points)), mn, mx, s["ai_model"], p.get("title", ""),
                brief={"instructions": brief["instructions"], "examples": examples, "fixed": fixed, "points": points})
            used_ai = bool(clips)
            if note:
                warns.append(note)
        except Exception as e:
            clips = None
            warns.append(f"AI gagal, memakai deteksi lokal. ({e})"[:300])
    alive()
    if clips:
        missing = [pt for pt in points if not any(c["start"] - 1 <= pt["t"] <= c["end"] for c in clips)]
        if missing:  # AI melewatkan titik riset: tambahkan momen di sekitarnya
            clips += core.find_highlights_heuristic(segs, energy(), 0, mn, mx, points=missing,
                                                    taken=[(c["start"], c["end"]) for c in clips])
    else:
        want, avoid = core.brief_keywords(brief["instructions"])
        if examples:  # tanpa AI: kata yang sering muncul di clip referensi jadi petunjuk topik
            want += [h[1:] for h in core._hashtags(" ".join(examples), 5) if h not in ("#fyp", "#viral")]
        clips = core.find_highlights_heuristic(segs, energy(), max(0, n - len(fixed) - len(points)), mn, mx,
                                               keywords=want, avoid=avoid, points=points, fixed=fixed)
    clips.sort(key=lambda c: c["start"])
    return clips, used_ai, warns


def output_files(rel):
    base = os.path.join(OUTPUT, rel).rsplit(".", 1)[0]
    return [base + ext for ext in (".mp4", ".srt", ".jpg", "_caption.txt")]


def do_render(pid, cid, token):
    p = projects[pid]
    c = next((x for x in p.get("clips", []) if x["id"] == cid), None)
    if not c or c.get("job") != token:
        return
    if not p.get("source"):
        c["render_status"], c["error"] = "gagal", "Video sumber sudah dihapus."
        save_project(p)
        return
    s = load_settings()
    style = {**s["style"], **(p.get("style") or {})}
    out = None
    try:
        c["render_status"], c["render_progress"], c["error"] = "proses", 0, ""
        segs = segments_of(p)
        words = [w for w in all_words(segs) if w["end"] > c["start"] and w["start"] < c["end"]]
        # nama stabil: memakai id clip, bukan nomor urut yang bisa bergeser
        name = f"{safe_name(p.get('title', 'video'), 30)}_{safe_name(c.get('title', ''), 30)}_{c['id'][:4]}"
        out_dir = os.path.join(OUTPUT, safe_name(p.get("title", pid), 50))
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, name + ".mp4")

        def prog(x):
            check_job(pid, c, token)  # hentikan render bila dibatalkan / proyek dihapus
            c["render_progress"] = round(x, 3)

        core.render_clip(os.path.join(pdir(pid), p["source"]), c["start"], c["end"], out, words,
                         style, c.get("title", "") if style.get("title_on", True) else "", progress=prog)
        # waktu subtitle .srt mengikuti video hasil (bisa lebih pendek bila jeda dibuang)
        keep, rel = core.clip_timeline(words, c["start"], c["end"], style)
        core.write_srt(rel, 0, sum(m - k for k, m in keep) / core.OUT_FPS, out.rsplit(".", 1)[0] + ".srt")
        with open(out.rsplit(".", 1)[0] + "_caption.txt", "w", encoding="utf-8") as f:
            f.write((c.get("caption") or c.get("title", "")) + "\n\n" + " ".join(c.get("hashtags", [])))
        rel = os.path.relpath(out, OUTPUT).replace("\\", "/")
        old = c.get("file")
        if old and old != rel:  # judul berubah: buang hasil render lama clip ini
            remove_later(remove_files(*output_files(old)))
        c["file"] = rel
        c.pop("subs_changed", None)
        c["rendered_at"] = int(time.time())  # untuk memuat ulang thumbnail di halaman
        c["render_status"], c["render_progress"] = "selesai", 1
    except Exception as e:
        if out:  # buang file sementara dari render yang tidak selesai
            remove_files(out + ".tmp.mp4", out + ".log")
            try:
                os.rmdir(os.path.dirname(out))  # hanya terhapus bila folder kosong
            except OSError:
                pass
        if pid not in projects or c.get("job") != token:
            return
        traceback.print_exc()
        c["render_status"], c["error"] = "gagal", str(e)[:500]
    save_project(p)


def worker(q, kind):
    while True:
        job = q.get()
        pid = job[0]
        try:
            if pid in projects:
                if kind == "analyze":
                    do_analyze(pid, job[1])
                else:
                    do_render(pid, job[1], job[2])
        except Exception:
            traceback.print_exc()  # jangan sampai pekerja mati dan antrian macet
        finally:
            if pid not in projects:
                # proyek dihapus saat diproses: sekarang file sudah tidak terkunci
                shutil.rmtree(pdir(pid), ignore_errors=True)
            q.task_done()


def queue_analyze(pid):
    p = projects[pid]
    with lock:
        p["job"] = uuid.uuid4().hex
        p["status"], p["stage"], p["progress"], p["error"] = "antri", "Menunggu giliran...", 0, ""
    analyze_q.put((pid, p["job"]))


def queue_render(pid, cid):
    p = projects.get(pid)
    if not p or not p.get("source"):
        return False
    with lock:
        c = next((x for x in p.get("clips", []) if x["id"] == cid), None)
        if not c or c.get("render_status") in ("antri", "proses"):
            return False
        c["job"] = uuid.uuid4().hex
        c["render_status"], c["render_progress"], c["error"] = "antri", 0, ""
    render_q.put((pid, cid, c["job"]))
    return True


BRIEF_LIMIT = 20_000  # karakter kolom "Referensi & instruksi"


def clean_brief(v):
    return str(v or "").strip()[:BRIEF_LIMIT]


def new_project(url=None, source=None, title=None, n_clips=None, auto_render=False, language=None, brief=None):
    pid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    os.makedirs(pdir(pid), exist_ok=True)
    p = {"id": pid, "url": url, "source": source, "title": title or url or "Video",
         "status": "antri", "stage": "Menunggu giliran...", "progress": 0, "clips": [],
         "created": time.time(), "n_clips": n_clips, "auto_render": auto_render, "error": "",
         "language": language if language in LANGUAGES else None, "brief": clean_brief(brief)}
    projects[pid] = p
    save_project(p)
    return p


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(WEB, "index.html", max_age=0)


@app.get("/<path:name>")
def web_file(name):
    """Berkas tampilan hasil `npm run build` di folder frontend/ (Next.js, disalin ke web/)."""
    # nama berkas di _next/static selalu berubah setiap build, jadi aman disimpan lama di cache
    return send_from_directory(WEB, name, max_age=31536000 if name.startswith("_next/static/") else 0)


@app.get("/api/state")
def state():
    for _ in range(5):
        try:
            with lock:
                items = sorted(projects.values(), key=lambda p: -p.get("created", 0))
                body = json.dumps({
                    "projects": [{**p, "size_mb": dir_size_mb(pdir(p["id"]))} for p in items],
                    "queue": analyze_q.qsize() + render_q.qsize(),
                }, ensure_ascii=False)
            return Response(body, mimetype="application/json")
        except RuntimeError:  # pekerja sedang mengubah data clip; coba baca lagi
            time.sleep(0.02)
    return jsonify(error="Server sibuk, coba lagi."), 503


@app.get("/api/settings")
def get_settings():
    s = load_settings()
    s["has_key"] = bool(s.get("api_key"))
    s["api_key"] = ""  # jangan kirim kunci ke halaman
    s["gpu"] = {"device": core.transcribe_device(), "error": core.CUDA_ERROR, "encoder": core.video_encoder()}
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
    for k in ("has_key", "gpu"):
        body.pop(k, None)
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
        p = new_project(url=url, n_clips=body.get("n_clips"), auto_render=body.get("auto_render", False),
                        language=body.get("language"), brief=body.get("brief"))
        queue_analyze(p["id"])
    return jsonify(ok=True, count=len(links))


@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify(error="Tidak ada file."), 400
    title = os.path.splitext(f.filename)[0]
    p = new_project(title=title, n_clips=request.form.get("n_clips", type=int),
                    auto_render=request.form.get("auto_render") == "true",
                    language=request.form.get("language"), brief=request.form.get("brief"))
    ext =os.path.splitext(f.filename)[1].lower() or ".mp4"
    f.save(os.path.join(pdir(p["id"]), "source" + ext))
    p["source"] = "source" + ext
    save_project(p)
    queue_analyze(p["id"])
    return jsonify(ok=True)


@app.post("/api/project/<pid>/retry")
def retry(pid):
    p = projects.get(pid) or abort(404)
    queue_analyze(pid)
    return jsonify(ok=True)


@app.post("/api/project/<pid>/reanalyze")
def reanalyze(pid):
    """Cari ulang momen (transkrip dipakai ulang, cepat)."""
    p = projects.get(pid) or abort(404)
    if busy(p):
        return jsonify(error="Tunggu render selesai atau batalkan dulu."), 409
    body = request.get_json(silent=True) or {}
    if body.get("n_clips"):
        p["n_clips"] = int(body["n_clips"])
    if "brief" in body:
        p["brief"] = clean_brief(body["brief"])
    queue_analyze(pid)
    return jsonify(ok=True)


@app.post("/api/parse-brief")
def parse_brief():
    """Ringkasan isi kolom referensi (dipakai halaman untuk menunjukkan apa yang dikenali)."""
    b = core.parse_brief(clean_brief((request.get_json(silent=True) or {}).get("text")))
    want, avoid = core.brief_keywords(b["instructions"])
    return jsonify({**b, "keywords": want, "avoid": avoid})


@app.post("/api/project/<pid>/cancel")
def cancel(pid):
    """Batalkan analisis dan/atau render. Body {cid} untuk satu clip saja."""
    p = projects.get(pid) or abort(404)
    cid = (request.get_json(silent=True) or {}).get("cid")
    n = 0
    with lock:
        for c in p.get("clips", []):
            if (cid is None or c["id"] == cid) and c.get("render_status") in ("antri", "proses"):
                c["job"] = None
                c["render_status"], c["render_progress"] = None, 0
                n += 1
        if cid is None and p.get("status") in ("antri", "proses"):
            p["job"] = None
            if p.get("clips"):
                p["status"], p["stage"] = "siap", "Pencarian ulang dibatalkan."
            else:
                p["status"], p["stage"] = "gagal", "Dibatalkan. Klik Ulangi untuk memproses lagi."
            n += 1
    save_project(p)
    return jsonify(ok=True, count=n)


@app.post("/api/project/<pid>/drop-source")
def drop_source(pid):
    """Hapus video sumber untuk menghemat disk. Hasil render di folder output tetap aman."""
    p = projects.get(pid) or abort(404)
    with lock:
        if busy(p):
            return jsonify(error="Tunggu proses selesai atau batalkan dulu."), 409
        src = p.get("source")
        p["source"] = None
        p["source_removed"] = True
    paths = [os.path.join(pdir(pid), "audio.wav")] + ([os.path.join(pdir(pid), src)] if src else [])
    remove_later(remove_files(*paths))
    save_project(p)
    return jsonify(ok=True)


@app.delete("/api/project/<pid>")
def delete_project(pid):
    with lock:
        p = projects.pop(pid, None)
        if p:
            # file yang masih dipakai render akan dibersihkan pekerja setelah ia berhenti
            shutil.rmtree(pdir(pid), ignore_errors=True)
            if os.path.exists(pdir(pid)) and not busy(p):
                remove_later([pdir(pid)])  # mis. video masih terbuka di browser
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


@app.get("/api/project/<pid>/clip/<cid>/subtitle")
def get_subtitle(pid, cid):
    """Teks subtitle clip (dari transkrip), untuk dikoreksi."""
    p = projects.get(pid) or abort(404)
    c = next((x for x in p["clips"] if x["id"] == cid), None) or abort(404)
    return jsonify(text=core.clip_words_text(segments_of(p), c["start"], c["end"]))


@app.post("/api/project/<pid>/clip/<cid>/subtitle")
def set_subtitle(pid, cid):
    """Simpan koreksi subtitle ke transkrip proyek (berlaku juga untuk clip lain di bagian yang sama)."""
    p = projects.get(pid) or abort(404)
    text = str((request.get_json(silent=True) or {}).get("text") or "")
    with lock:
        c = next((x for x in p["clips"] if x["id"] == cid), None) or abort(404)
        segs = segments_of(p)
        try:
            changed = core.edit_words(segs, c["start"], c["end"], text)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        if changed:
            with open(os.path.join(pdir(pid), "transcript.json"), "w", encoding="utf-8") as f:
                json.dump(segs, f, ensure_ascii=False)
            for x in p["clips"]:
                x["text"] = " ".join(s["text"] for s in segs if s["end"] > x["start"] and s["start"] < x["end"])
                if x.get("render_status") == "selesai" and x["end"] > c["start"] and x["start"] < c["end"]:
                    x["subs_changed"] = True  # hasil render lama masih memakai teks sebelumnya
    save_project(p)
    return jsonify(ok=True, changed=changed)


@app.delete("/api/project/<pid>/clip/<cid>")
def delete_clip(pid, cid):
    p = projects.get(pid) or abort(404)
    with lock:
        for c in p["clips"]:
            if c["id"] == cid:
                c["job"] = None  # hentikan render clip ini bila sedang berjalan
        p["clips"] = [c for c in p["clips"] if c["id"] != cid]
    save_project(p)
    return jsonify(ok=True)


@app.post("/api/project/<pid>/render")
def render(pid):
    p = projects.get(pid) or abort(404)
    if not p.get("source"):
        return jsonify(error="Video sumber sudah dihapus, clip tidak bisa dirender lagi."), 409
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or [c["id"] for c in p["clips"] if c.get("selected")]
    if body.get("style"):
        p["style"] = body["style"]
    n = sum(1 for cid in ids if queue_render(pid, cid))
    save_project(p)
    return jsonify(ok=True, count=n)


@app.post("/api/render-all")
def render_all():
    n = 0
    for pid, p in list(projects.items()):
        for c in p.get("clips", []):
            if c.get("selected") and c.get("render_status") != "selesai" and queue_render(pid, c["id"]):
                n += 1
    return jsonify(ok=True, count=n)


@app.post("/api/preview-style")
def preview_style():
    """Satu frame contoh dengan gaya saat ini, supaya tidak perlu render ulang hanya untuk mencoba gaya."""
    body = request.get_json(silent=True) or {}
    s = load_settings()
    style = {**s["style"], **(body.get("style") or {})}
    pid = body.get("pid")
    cands = [projects[pid]] if pid in projects else sorted(projects.values(), key=lambda x: -x.get("created", 0))
    p = next((x for x in cands if x.get("status") == "siap" and x.get("source")
              and os.path.exists(os.path.join(pdir(x["id"]), x["source"]))), None)
    try:
        if p:
            clip = (p.get("clips") or [None])[0]
            t = clip["start"] + 1.0 if clip else (p.get("duration") or 10) * 0.3
            words = [w for w in all_words(segments_of(p)) if t - 0.05 <= w["start"] < t + 4]
            title = (clip or {}).get("title") or p.get("title", "")
            jpg = core.render_preview(os.path.join(pdir(p["id"]), p["source"]), t, words, style, title)
        else:
            jpg = core.render_preview(None, 0, [], style, "Contoh judul hook yang menarik")
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"Pratinjau gagal: {e}"[:300]), 500
    return Response(jpg, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/style-from-reference")
def style_from_reference():
    """Tiru gaya dari clip referensi (link atau file), tanpa AI. Hanya mengembalikan gaya yang terdeteksi;
    pengaturan baru disimpan setelah pengguna menekan Terapkan."""
    s = load_settings()
    tmp = os.path.join(DATA, "style_ref", uuid.uuid4().hex[:8])
    try:
        f = request.files.get("file")
        if f:
            os.makedirs(tmp, exist_ok=True)
            path = os.path.join(tmp, "ref" + (os.path.splitext(f.filename or "")[1].lower() or ".mp4"))
            f.save(path)
            title = f.filename or "file"
        else:
            url = str((request.get_json(silent=True) or {}).get("url") or "").strip()
            if not url.startswith("http"):
                return jsonify(error="Tempel link clip referensi atau pilih file video."), 400
            info = core.download_reference(url, tmp, s.get("cookies_browser") or None, video=True)
            path, title = info["path"], info["title"]
        res = core.analyze_reference_style(path)
        return jsonify(ok=True, title=title, style=res["style"], notes=res["notes"], seconds=res["seconds"])
    except Exception as e:
        traceback.print_exc()
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
        return jsonify(error=f"Gagal membaca clip referensi: {msg}"[:400]), 400
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.exists(tmp):
            remove_later([tmp])


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
    threading.Thread(target=worker, args=(analyze_q, "analyze"), daemon=True).start()
    threading.Thread(target=worker, args=(render_q, "render"), daemon=True).start()
    port = int(os.environ.get("PORT", 7860))
    url = f"http://127.0.0.1:{port}"
    print("=" * 56)
    print("  ClipMaker berjalan di", url)
    print("  Biarkan jendela ini terbuka selama memakai aplikasi.")
    print("=" * 56)
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
